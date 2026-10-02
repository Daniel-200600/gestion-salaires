"""
Modèles de bulletin de solde : modèles standard, import, activation.

Modèles disponibles
-------------------
- « Bulletin officiel — Word » (standard_docx) : templates/bulletin_template.docx,
  reproduction exacte du bulletin officiel de l'établissement ;
- « Bulletin officiel — PDF » (standard_pdf) : le même bulletin au format PDF
  (templates/bulletin_modele_standard.pdf + zones .json) ;
- les modèles importés par l'administrateur (Word .docx ou PDF), stockés
  dans data/modeles_bulletin/ et référencés dans la table modeles_bulletin.

Un seul modèle est actif à la fois (parametres_paie, clé
`modele_bulletin_actif`) ; les bulletins sont produits dans le format
du modèle actif. Tant qu'aucun choix n'a été fait : modèle Word standard
(comportement historique de l'application).

Importer un modèle
------------------
Deux possibilités, pour Word comme pour PDF :
1. un modèle à balises ({{NOM}}, {{NET_A_PAYER}}... voir
   utils/balises_bulletin.py) ;
2. un bulletin déjà rempli (par exemple un bulletin de l'an dernier) :
   l'application repère les champs (utils/detection_bulletin.py) et
   propose des correspondances que l'administrateur valide ou corrige.

Avant tout enregistrement, un bulletin d'essai est produit avec des
valeurs d'exemple : un modèle qui ne permet pas de produire un bulletin
complet n'est jamais enregistré.

Les contrôles d'autorisation (ADMIN) sont appliqués par la façade
services/administration_service.py.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from config.settings import MODELES_BULLETIN_DIR, chemin_modele_standard
from database.repositories import audit_log_repository, modele_bulletin_repository, parametres_paie_repository
from exports import pdf_export, word_export
from models.audit_log import AuditLog
from models.enums import TypeActionAudit
from utils.balises_bulletin import controler_balises, valeurs_exemple
from utils.detection_bulletin import Segment, suggerer_correspondances

logger = logging.getLogger("salaires_app.modele_bulletin_service")

DbPath = Optional[Union[str, Path]]

CLE_MODELE_ACTIF = "modele_bulletin_actif"
CLE_STANDARD_WORD = "standard_docx"
CLE_STANDARD_PDF = "standard_pdf"
PREFIXE_IMPORTE = "importe_"

TAILLE_MAX_OCTETS = 10 * 1024 * 1024
FORMATS = {".docx": "docx", ".pdf": "pdf"}
LIBELLES_FORMAT = {"docx": "Word (.docx)", "pdf": "PDF"}

CHEMIN_STANDARD_PDF = chemin_modele_standard("bulletin_modele_standard.pdf")
CHEMIN_ZONES_STANDARD_PDF = chemin_modele_standard("bulletin_modele_standard.json")


class ModeleBulletinError(ValueError):
    """Modèle refusé (format, contenu, balises) ou opération impossible."""


@dataclass
class ModeleBulletin:
    cle: str
    nom: str
    format: str                      # "docx" ou "pdf"
    chemin: Path
    standard: bool
    zones: List[pdf_export.ZonePdf] = field(default_factory=list)
    id: Optional[int] = None
    nom_fichier_origine: str = ""
    empreinte: str = ""
    date_import: str = ""
    utilisateur: Optional[str] = None

    @property
    def extension(self) -> str:
        return f".{self.format}"

    @property
    def libelle(self) -> str:
        return f"{self.nom} ({LIBELLES_FORMAT[self.format]})"

    def contenu(self) -> bytes:
        return self.chemin.read_bytes()


@dataclass
class AnalyseModele:
    """Résultat de l'analyse d'un fichier envoyé, avant import."""

    format: str
    mode: str                                       # "balises" ou "correspondances"
    balises: List[str] = field(default_factory=list)
    inconnues: List[str] = field(default_factory=list)
    manquantes: List[str] = field(default_factory=list)
    recommandees_manquantes: List[str] = field(default_factory=list)
    erreurs: List[str] = field(default_factory=list)
    segments: List[Segment] = field(default_factory=list)
    propositions: Dict[str, str] = field(default_factory=dict)
    zones: List[pdf_export.ZonePdf] = field(default_factory=list)

    @property
    def valide(self) -> bool:
        return not self.erreurs


# ---------------------------------------------------------------------
# Modèles disponibles
# ---------------------------------------------------------------------

def _dossier_modeles() -> Path:
    return MODELES_BULLETIN_DIR


def modele_standard_word() -> ModeleBulletin:
    return ModeleBulletin(cle=CLE_STANDARD_WORD, nom="Bulletin officiel", format="docx",
                          chemin=word_export.TEMPLATE_PATH, standard=True)


def modele_standard_pdf() -> ModeleBulletin:
    zones = []
    if CHEMIN_ZONES_STANDARD_PDF.exists():
        zones = [pdf_export.ZonePdf.from_dict(z) for z in json.loads(CHEMIN_ZONES_STANDARD_PDF.read_text(encoding="utf-8"))]
    return ModeleBulletin(cle=CLE_STANDARD_PDF, nom="Bulletin officiel", format="pdf",
                          chemin=CHEMIN_STANDARD_PDF, standard=True, zones=zones)


def _depuis_ligne(ligne) -> ModeleBulletin:
    zones = []
    if ligne["format"] == "pdf":
        zones = [pdf_export.ZonePdf.from_dict(z) for z in json.loads(ligne["correspondances"] or "[]")]
    return ModeleBulletin(
        cle=f"{PREFIXE_IMPORTE}{ligne['id']}", nom=ligne["nom"], format=ligne["format"],
        chemin=_dossier_modeles() / ligne["nom_fichier"], standard=False, zones=zones, id=ligne["id"],
        nom_fichier_origine=ligne["nom_fichier_origine"], empreinte=ligne["empreinte"],
        date_import=ligne["date_import"], utilisateur=ligne["utilisateur"],
    )


def lister_modeles(db_path: DbPath = None) -> List[ModeleBulletin]:
    """Modèles standard puis modèles importés (du plus récent au plus ancien)."""
    return [modele_standard_word(), modele_standard_pdf()] + [
        _depuis_ligne(ligne) for ligne in modele_bulletin_repository.lister(db_path=db_path)
    ]


def obtenir_modele(cle: str, db_path: DbPath = None) -> ModeleBulletin:
    if cle == CLE_STANDARD_WORD:
        return modele_standard_word()
    if cle == CLE_STANDARD_PDF:
        return modele_standard_pdf()
    if cle.startswith(PREFIXE_IMPORTE) and cle[len(PREFIXE_IMPORTE):].isdigit():
        ligne = modele_bulletin_repository.obtenir(int(cle[len(PREFIXE_IMPORTE):]), db_path=db_path)
        if ligne is not None:
            return _depuis_ligne(ligne)
    raise ModeleBulletinError("Modèle de bulletin introuvable.")


def cle_modele_actif(db_path: DbPath = None) -> str:
    return parametres_paie_repository.lire(CLE_MODELE_ACTIF, db_path=db_path) or CLE_STANDARD_WORD


def probleme_modele_actif(db_path: DbPath = None) -> Optional[str]:
    """
    Message à afficher à l'écran si le modèle choisi par l'administrateur
    ne peut pas être utilisé — les bulletins sont alors produits avec le
    modèle Word standard. None si le modèle choisi est utilisable.
    """
    cle = cle_modele_actif(db_path=db_path)
    remede = "Choisissez ou réimportez un modèle dans Administration › Modèles de bulletin."
    try:
        modele = obtenir_modele(cle, db_path=db_path)
    except ModeleBulletinError:
        return ("Le modèle de bulletin choisi n'existe plus : les bulletins sont produits avec le "
                f"modèle Word standard. {remede}")
    if not modele.chemin.exists():
        return (f"Le fichier du modèle de bulletin « {modele.nom} » est introuvable sur cet ordinateur "
                "(par exemple après une restauration ou un changement de poste) : les bulletins sont "
                f"produits avec le modèle Word standard. {remede}")
    if modele.format == "pdf" and not modele.zones:
        return (f"Le modèle PDF « {modele.nom} » est incomplet (zones à remplir absentes) : les bulletins "
                f"sont produits avec le modèle Word standard. {remede}")
    return None


def obtenir_modele_actif(db_path: DbPath = None) -> ModeleBulletin:
    """
    Modèle utilisé pour produire les bulletins. Si le modèle choisi n'est
    plus disponible (voir `probleme_modele_actif`, affiché à l'écran par
    les pages Bulletins, Automatisation et Administration), le modèle Word
    standard est utilisé — un bulletin n'est jamais bloqué pour cette
    raison.
    """
    probleme = probleme_modele_actif(db_path=db_path)
    if probleme is not None:
        logger.warning(probleme)
        return modele_standard_word()
    return obtenir_modele(cle_modele_actif(db_path=db_path), db_path=db_path)


# ---------------------------------------------------------------------
# Analyse d'un fichier envoyé
# ---------------------------------------------------------------------

def format_du_fichier(nom_fichier: str, contenu: bytes) -> str:
    extension = Path(nom_fichier or "").suffix.lower()
    if extension not in FORMATS:
        raise ModeleBulletinError("Format non accepté : envoyez un fichier Word (.docx) ou PDF (.pdf).")
    format_ = FORMATS[extension]
    signature_attendue = b"%PDF" if format_ == "pdf" else b"PK"
    if not bytes(contenu[:1024]).lstrip().startswith(signature_attendue) and not (
        format_ == "pdf" and b"%PDF" in bytes(contenu[:1024])
    ):
        raise ModeleBulletinError(f"Le contenu du fichier ne correspond pas à un fichier {LIBELLES_FORMAT[format_]}.")
    return format_


def analyser_modele(contenu: bytes, nom_fichier: str) -> AnalyseModele:
    """
    Analyse un fichier envoyé : format, balises présentes, ou à défaut
    segments de texte et correspondances proposées. Ne modifie rien.
    """
    if not contenu:
        raise ModeleBulletinError("Le fichier est vide.")
    if len(contenu) > TAILLE_MAX_OCTETS:
        raise ModeleBulletinError("Le fichier dépasse 10 Mo.")
    format_ = format_du_fichier(nom_fichier, contenu)

    try:
        if format_ == "docx":
            document = word_export.ouvrir_document(contenu)
            balises = word_export.extraire_balises_document(document)
            zones: List[pdf_export.ZonePdf] = []
            erreurs: List[str] = []
        else:
            analyse_pdf = pdf_export.zones_depuis_balises(contenu)
            balises, zones, erreurs = analyse_pdf.balises, analyse_pdf.zones, list(analyse_pdf.erreurs)
    except (word_export.WordExportError, pdf_export.PdfExportError) as erreur:
        raise ModeleBulletinError(str(erreur)) from erreur

    if balises or erreurs:
        inconnues, manquantes, recommandees = controler_balises(balises)
        if inconnues:
            erreurs.append("Balise(s) inconnue(s) : " + ", ".join("{{" + n + "}}" for n in inconnues) + ".")
        if manquantes:
            erreurs.append("Balise(s) obligatoire(s) absente(s) : " + ", ".join(manquantes) + ".")
        return AnalyseModele(format=format_, mode="balises", balises=balises, inconnues=inconnues,
                             manquantes=manquantes, recommandees_manquantes=recommandees, erreurs=erreurs, zones=zones)

    try:
        segments = word_export.segments_docx(contenu) if format_ == "docx" else pdf_export.segments_pdf(contenu)
    except (word_export.WordExportError, pdf_export.PdfExportError) as erreur:
        raise ModeleBulletinError(str(erreur)) from erreur
    if not segments:
        raise ModeleBulletinError("Le document ne contient aucun texte.")
    return AnalyseModele(format=format_, mode="correspondances", segments=segments,
                         propositions=suggerer_correspondances(segments))


def controler_correspondances(correspondances: Dict[str, str]) -> List[str]:
    """Erreurs bloquantes d'un jeu de correspondances (balises obligatoires, balises inconnues)."""
    inconnues, manquantes, _ = controler_balises(list(correspondances.values()))
    erreurs = []
    if not correspondances:
        erreurs.append("Aucun champ n'a été associé : indiquez au moins le nom et le net à payer.")
    if inconnues:
        erreurs.append("Champ(s) inconnu(s) : " + ", ".join(inconnues) + ".")
    if manquantes:
        erreurs.append("Champ(s) obligatoire(s) non associé(s) : " + ", ".join(manquantes) + ".")
    return erreurs


def construire_modele(
    contenu: bytes, analyse: AnalyseModele,
    correspondances: Optional[Dict[str, str]] = None, alignements: Optional[Dict[str, str]] = None,
):
    """
    Produit le fichier modèle définitif et ses zones :
    - Word à balises : fichier inchangé ;
    - Word rempli : bulletin converti en modèle à balises (les valeurs
      reconnues sont remplacées par des balises) ;
    - PDF (balises ou rempli) : zones repérées, puis textes de ces zones
      effacés du fichier enregistré — aucune donnée de l'enseignant du
      bulletin d'origine n'est conservée dans le modèle.
    Retourne (contenu_modele, zones).
    """
    if analyse.mode == "balises":
        if not analyse.valide:
            raise ModeleBulletinError(" ".join(analyse.erreurs))
        if analyse.format == "pdf":
            return _pdf_nettoye(contenu, analyse.zones), analyse.zones
        return contenu, analyse.zones

    correspondances = {cle: balise for cle, balise in (correspondances or {}).items() if balise}
    erreurs = controler_correspondances(correspondances)
    if erreurs:
        raise ModeleBulletinError(" ".join(erreurs))
    segments = {s.id: s for s in analyse.segments}
    if any(cle not in segments for cle in correspondances):
        raise ModeleBulletinError("Correspondance vers un texte introuvable : relancez l'analyse du modèle.")

    if analyse.format == "docx":
        try:
            return word_export.convertir_en_modele(contenu, correspondances), []
        except word_export.WordExportError as erreur:
            raise ModeleBulletinError(str(erreur)) from erreur

    alignements = alignements or {}
    zones = [
        pdf_export.zone_depuis_segment(segments[cle], balise, alignements.get(cle) or "centre")
        for cle, balise in correspondances.items()
    ]
    zones.sort(key=lambda z: (z.page, z.rect[1], z.rect[0]))
    return _pdf_nettoye(contenu, zones), zones


def _pdf_nettoye(contenu: bytes, zones: List[pdf_export.ZonePdf]) -> bytes:
    """Le modèle PDF enregistré ne garde ni les valeurs du bulletin d'origine ni les balises."""
    try:
        return pdf_export.effacer_zones(contenu, zones)
    except pdf_export.PdfExportError as erreur:
        raise ModeleBulletinError(str(erreur)) from erreur


# ---------------------------------------------------------------------
# Production d'un bulletin à partir d'un modèle
# ---------------------------------------------------------------------

def produire(format_: str, contenu_modele: bytes, zones: List[pdf_export.ZonePdf], valeurs: Dict[str, str]) -> bytes:
    """Bulletin (octets) au format du modèle. Lève ModeleBulletinError si un champ reste vide."""
    try:
        if format_ == "pdf":
            resultat = pdf_export.generer_pdf(contenu_modele, zones, valeurs)
            if "{{" in pdf_export.texte_pdf(resultat):
                raise ModeleBulletinError("Une balise n'a pas été remplacée dans le bulletin PDF.")
            return resultat
        document = word_export.ouvrir_document(contenu_modele)
        word_export._remplacer_dans_document(document, valeurs)
        word_export.verifier_aucun_placeholder_restant(document)
        return word_export.document_en_octets(document)
    except (word_export.WordExportError, pdf_export.PdfExportError) as erreur:
        raise ModeleBulletinError(str(erreur)) from erreur


def apercu(format_: str, contenu_modele: bytes, zones: List[pdf_export.ZonePdf]) -> bytes:
    """Bulletin d'essai rempli avec les valeurs d'exemple (celles du bulletin officiel)."""
    return produire(format_, contenu_modele, zones, valeurs_exemple())


def apercu_modele(modele: ModeleBulletin) -> bytes:
    return apercu(modele.format, modele.contenu(), modele.zones)


# ---------------------------------------------------------------------
# Import, activation, suppression
# ---------------------------------------------------------------------

def _journaliser(type_action: TypeActionAudit, modele_id: Optional[int], utilisateur: Optional[str],
                 details: str, db_path: DbPath) -> None:
    audit_log_repository.enregistrer(
        AuditLog(type_action=type_action, entite="modele_bulletin", entite_id=modele_id,
                 utilisateur=utilisateur, details=details),
        db_path=db_path,
    )


def importer_modele(
    nom: str, contenu: bytes, nom_fichier: str,
    correspondances: Optional[Dict[str, str]] = None, alignements: Optional[Dict[str, str]] = None,
    utilisateur: Optional[str] = None, activer: bool = False, db_path: DbPath = None,
) -> ModeleBulletin:
    """
    Analyse, construit, ESSAIE (bulletin d'essai complet) puis enregistre
    un modèle. Rien n'est enregistré si une étape échoue.
    """
    nom = (nom or "").strip()
    if not nom:
        raise ModeleBulletinError("Donnez un nom au modèle.")
    if len(nom) > 80:
        raise ModeleBulletinError("Le nom du modèle ne doit pas dépasser 80 caractères.")

    analyse = analyser_modele(contenu, nom_fichier)
    contenu_modele, zones = construire_modele(contenu, analyse, correspondances, alignements)
    apercu(analyse.format, contenu_modele, zones)  # lève si le modèle ne produit pas un bulletin complet

    dossier = _dossier_modeles()
    dossier.mkdir(parents=True, exist_ok=True)
    nom_stocke = f"modele_{uuid.uuid4().hex}.{analyse.format}"
    chemin = dossier / nom_stocke
    chemin.write_bytes(contenu_modele)
    try:
        modele_id = modele_bulletin_repository.creer(
            nom=nom, format_=analyse.format, nom_fichier=nom_stocke,
            nom_fichier_origine=Path(nom_fichier).name[:255],
            empreinte=hashlib.sha256(contenu_modele).hexdigest(),
            correspondances=json.dumps([z.to_dict() for z in zones], ensure_ascii=False),
            utilisateur=utilisateur, db_path=db_path,
        )
    except Exception:
        chemin.unlink(missing_ok=True)
        raise
    _journaliser(TypeActionAudit.MODELE_BULLETIN_IMPORTE, modele_id, utilisateur,
                 f"{nom} — {LIBELLES_FORMAT[analyse.format]} — fichier {Path(nom_fichier).name} "
                 f"({'balises' if analyse.mode == 'balises' else 'correspondances validées'})", db_path)
    modele = obtenir_modele(f"{PREFIXE_IMPORTE}{modele_id}", db_path=db_path)
    if activer:
        activer_modele(modele.cle, utilisateur=utilisateur, db_path=db_path)
    return modele


def activer_modele(cle: str, utilisateur: Optional[str] = None, db_path: DbPath = None) -> ModeleBulletin:
    modele = obtenir_modele(cle, db_path=db_path)
    if not modele.chemin.exists():
        raise ModeleBulletinError(f"Le fichier du modèle « {modele.nom} » est introuvable sur le disque.")
    apercu_modele(modele)  # le modèle doit toujours produire un bulletin complet
    parametres_paie_repository.ecrire(CLE_MODELE_ACTIF, modele.cle, utilisateur=utilisateur, db_path=db_path)
    _journaliser(TypeActionAudit.MODELE_BULLETIN_ACTIVE, modele.id, utilisateur, modele.libelle, db_path)
    return modele


def supprimer_modele(cle: str, utilisateur: Optional[str] = None, db_path: DbPath = None) -> None:
    modele = obtenir_modele(cle, db_path=db_path)
    if modele.standard:
        raise ModeleBulletinError("Les modèles standard ne peuvent pas être supprimés.")
    if cle_modele_actif(db_path=db_path) == modele.cle:
        raise ModeleBulletinError("Ce modèle est actif : activez d'abord un autre modèle.")
    modele_bulletin_repository.supprimer(modele.id, db_path=db_path)
    modele.chemin.unlink(missing_ok=True)
    _journaliser(TypeActionAudit.MODELE_BULLETIN_SUPPRIME, modele.id, utilisateur, modele.libelle, db_path)
