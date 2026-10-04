"""
Service bulletin (module 07).

Prépare les données consommées par le générateur de bulletins — Word
(exports/word_export.py) ou PDF (exports/pdf_export.py) selon le modèle
actif (services/modele_bulletin_service.py) — exclusivement à partir des résultats déjà
calculés par le moteur de paie (services/paie_service.py).

RÈGLE ABSOLUE : ce service ne recalcule JAMAIS gain_heures, taxe_5 ou
net_a_percevoir. Le seul « calcul » effectué ici est un total
d'affichage dérivé de deux valeurs déjà finales du moteur de paie
(base_taxable - net_a_percevoir = taxe + retenue amicale + dette),
nécessaire pour la ligne « Total » du modèle officiel — ce n'est pas
une réimplémentation d'une formule de paie, seulement une soustraction
entre deux résultats déjà produits par paie_service.

Aucune dépendance à Streamlit.

PROTECTION DE L'HISTORIQUE
----------------------------
- Période CLOTUREE + bulletin déjà généré sur disque pour cet
  enseignant -> régénération REFUSÉE (le fichier existant est protégé).
- Toute autre période : le fichier n'est jamais écrasé silencieusement
  (nom versionné automatiquement via
  exports.excel_export.chemin_sortie_disponible, déjà utilisé au
  module 06 — pas de duplication de cette logique).
"""

import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from docx import Document

from database.repositories import bulletin_repository
from exports.excel_export import chemin_sortie_disponible
from exports.pdf_export import PdfExportError, texte_pdf
from exports.word_export import (
    EXPORT_DIR_BULLETINS,
    generer_document_bulletin,
    generer_nom_fichier_bulletin,
    sauvegarder_document,
    texte_document,
)
from models.bulletin_paie import BulletinPaie
from models.enums import StatutPeriode
from models.periode_paie import PeriodePaie
from models.resultat_paie import ResultatPaie
from services.paie_service import CalculPaieError, calculer_paie_enseignant
from utils.formatters import libelle_periode_anglais, libelle_statut, nettoyer_nom_fichier
from utils.montant_en_lettres import montant_en_lettres

DbPath = Optional[Union[str, Path]]

# Un bulletin est produit au format du modèle actif (services/modele_bulletin_service.py).
EXTENSIONS_BULLETIN = (".docx", ".pdf")


class BulletinServiceError(Exception):
    """
    Levée pour toute impossibilité de générer un bulletin : erreur du
    moteur de paie (période/enseignant introuvable, période BROUILLON),
    ou régénération refusée pour une période clôturée dont le bulletin
    existe déjà.
    """


@dataclass
class BulletinGenere:
    """Résultat de la génération d'UN bulletin."""

    enseignant_id: int
    chemin: Path
    resultat: ResultatPaie


@dataclass
class BulletinsGeneres:
    """
    Résultat d'une génération groupée : les bulletins produits avec
    succès d'un côté, les échecs individuels (par enseignant_id) de
    l'autre. Un échec sur un enseignant n'empêche jamais la génération
    des autres (même philosophie que paie_service.calculer_paie_groupe).
    """

    bulletins: List[BulletinGenere] = field(default_factory=list)
    erreurs: Dict[int, str] = field(default_factory=dict)


def _dossier_periode(libelle_periode: str) -> Path:
    """data/exports/bulletins/[periode]/ — créé automatiquement si besoin."""
    return EXPORT_DIR_BULLETINS / nettoyer_nom_fichier(libelle_periode)


def _formater_heures(valeur: float) -> str:
    """Affiche un nombre d'heures sans décimale inutile (12 plutôt que 12.0)."""
    return f"{valeur:g}"


def _preparer_valeurs_placeholder(resultat: ResultatPaie, periode: Union[PeriodePaie, str]) -> Dict[str, str]:
    """
    Construit le dict {balise: valeur texte} à partir d'un ResultatPaie
    déjà calculé par paie_service — aucune formule de paie n'est
    recalculée ici, uniquement de la mise en forme texte (montants sans
    séparateur de milliers, comme sur le bulletin officiel).

    Toutes les balises de utils/balises_bulletin.py sont fournies, ainsi
    que les noms historiques (TAXE_5, NET_A_PERÇEVOIR, DATE_GENERATION),
    afin que tout modèle — standard ou importé — soit rempli.
    """
    # Total affiché sur la ligne "Total" du modèle : dérivé de deux
    # valeurs déjà finales (base_taxable, net_a_percevoir), pas une
    # formule de paie recalculée.
    total_gains = resultat.base_taxable
    total_retenues = resultat.base_taxable - resultat.net_a_percevoir

    if isinstance(periode, PeriodePaie):
        libelle_fr = periode.libelle.upper()
        libelle_en = libelle_periode_anglais(periode.mois, periode.annee)
    else:  # compatibilité : simple libellé
        libelle_fr = libelle_en = str(periode).upper()

    from services.parametres_paie_service import formater_taux  # import local : évite un cycle

    valeurs = {
        "NOM": resultat.nom.upper(),
        "PRENOM": resultat.prenom.upper(),
        "NOM_COMPLET": f"{resultat.nom.upper()} {resultat.prenom.upper()}",
        "STATUT": resultat.statut.value,  # déjà 'V'/'P' en base, aucune conversion de valeur
        "STATUT_LIBELLE": libelle_statut(resultat.statut),
        # Le bulletin officiel (bilingue) affiche le mois en anglais : « JULY 2026 ».
        "PERIODE": libelle_en,
        "PERIODE_FR": libelle_fr,
        "DATE": datetime.now().strftime("%d/%m/%Y"),
        "TOTAL_HEURES": _formater_heures(resultat.total_heures),
        "SEMAINE_1": _formater_heures(resultat.semaine_1),
        "SEMAINE_2": _formater_heures(resultat.semaine_2),
        "SEMAINE_3": _formater_heures(resultat.semaine_3),
        "SEMAINE_4": _formater_heures(resultat.semaine_4),
        "SEMAINE_5": _formater_heures(resultat.semaine_5),
        # Permanent au salaire fixe : pas de taux horaire, le gain est le salaire du mois.
        "TAUX_HORAIRE": "" if resultat.salaire_fixe is not None else str(resultat.taux_horaire),
        "GAIN_HEURES": str(resultat.gain_heures),
        "PRIME_AP_PP": str(resultat.prime_ap_pp),
        "SURVEILLANCE_SECRETARIAT": str(resultat.surveillance_secretariat),
        "INDEMNITE_SUGGESTION_ADMIN": str(resultat.indemnite_suggestion_admin),
        "TOTAL_GAINS": str(total_gains),
        "BASE_TAXABLE": str(resultat.base_taxable),
        "TAXE": str(resultat.taxe_5),
        "TAXE_TAUX": formater_taux(resultat.taux_taxe),
        "RETENUE_AMICALE": str(resultat.retenue_amicale),
        "DETTE": str(resultat.dette),
        "TOTAL_RETENUES": str(total_retenues),
        "NET_A_PAYER": str(resultat.net_a_percevoir),
        "NET_EN_LETTRES": montant_en_lettres(resultat.net_a_percevoir),
    }
    valeurs["TAXE_5"] = valeurs["TAXE"]
    valeurs["NET_A_PERÇEVOIR"] = valeurs["NET_A_PAYER"]
    valeurs["NET_A_PERCEVOIR"] = valeurs["NET_A_PAYER"]
    valeurs["DATE_GENERATION"] = valeurs["DATE"]
    return {"{{" + cle + "}}": valeur for cle, valeur in valeurs.items()}


def _statut_fige(resultat: ResultatPaie, periode: PeriodePaie, db_path: DbPath) -> ResultatPaie:
    """
    Pour une période validée ou clôturée dont le bulletin a déjà été
    enregistré (instantané bulletins_paie), le statut affiché reste celui
    de l'instantané : un changement de statut de l'enseignant (Vacataire
    -> Permanent, par exemple) ne modifie jamais un bulletin déjà émis.
    """
    if periode.statut not in (StatutPeriode.VALIDEE, StatutPeriode.CLOTUREE):
        return resultat
    for instantane in bulletin_repository.lister_par_periode(periode.id, db_path=db_path):
        if instantane.enseignant_id == resultat.enseignant_id and instantane.statut_snapshot != resultat.statut:
            return replace(resultat, statut=instantane.statut_snapshot)
    return resultat


def _bulletin_existe_deja(resultat: ResultatPaie, libelle_periode: str) -> Optional[Path]:
    """Vérifie si un bulletin (Word ou PDF) a déjà été généré (nom de base, sans suffixe de version) pour cet enseignant/période."""
    for extension in EXTENSIONS_BULLETIN:
        nom_fichier = generer_nom_fichier_bulletin(resultat.nom, resultat.prenom, libelle_periode, extension)
        chemin = _dossier_periode(libelle_periode) / nom_fichier
        if chemin.exists():
            return chemin
    return None


def _valider_bulletin_genere(chemin: Path, resultat: ResultatPaie, libelle_periode: str) -> None:
    """
    Contrôles de validité appliqués APRÈS génération, avant qu'un
    bulletin soit considéré comme valide et proposable au
    téléchargement. Si un contrôle échoue, le fichier généré est
    supprimé (jamais de livraison silencieuse d'un bulletin incomplet)
    et BulletinServiceError est levée avec un message explicite.

    1. Nom présent            6. Montants présents (7 champs)
    2. Prénom présent         7. Net présent
    3. Période présente       8. Aucun placeholder restant
    4. Statut présent         9. Le fichier .docx est valide (ouvrable)
    5. Total heures présent   10. Le nom du fichier correspond à l'enseignant
    """
    def _echec(message: str) -> None:
        chemin.unlink(missing_ok=True)
        raise BulletinServiceError(f"Contrôle de validité échoué : {message}")

    # Nom ou prénom manquant : signalé par le contrôle de paie, jamais bloquant ici.
    if not libelle_periode or not libelle_periode.strip():
        _echec("le libellé de la période est manquant.")
    if resultat.statut is None:
        _echec("le statut de l'enseignant est manquant.")
    if resultat.total_heures is None:
        _echec("le total des heures est manquant.")

    champs_montants = {
        "gain_heures": resultat.gain_heures,
        "prime_ap_pp": resultat.prime_ap_pp,
        "surveillance_secretariat": resultat.surveillance_secretariat,
        "indemnite_suggestion_admin": resultat.indemnite_suggestion_admin,
        "taxe_5": resultat.taxe_5,
        "retenue_amicale": resultat.retenue_amicale,
        "dette": resultat.dette,
    }
    for nom_champ, valeur in champs_montants.items():
        if valeur is None:
            _echec(f"le montant '{nom_champ}' est manquant.")

    if resultat.net_a_percevoir is None:
        _echec("le net à percevoir est manquant.")
    if resultat.net_a_percevoir < 0:
        _echec("le net à payer est négatif (les retenues dépassent les gains) : corrigez les données de paie.")

    if chemin.suffix.lower() == ".pdf":
        try:
            contenu = texte_pdf(chemin.read_bytes())
        except PdfExportError as erreur:
            _echec(f"le fichier PDF généré n'est pas un document valide ({erreur}).")
            return
        if str(resultat.net_a_percevoir) not in contenu:
            _echec("le net à payer n'apparaît pas dans le bulletin PDF.")
    else:
        try:
            document_verification = Document(chemin)
        except Exception as erreur:  # noqa: BLE001 — toute erreur d'ouverture invalide le contrôle 9
            _echec(f"le fichier .docx généré n'est pas un document valide ({erreur}).")
            return
        contenu = texte_document(document_verification)
    if "{{" in contenu or "}}" in contenu:
        _echec("un placeholder non remplacé subsiste dans le document.")

    # Comparaison sur le nom tel qu'il est écrit dans le nom de fichier (espaces et caractères interdits
    # remplacés par « _ ») : un nom composé ou avec apostrophe ne fait jamais échouer le bulletin.
    nom_dans_fichier = nettoyer_nom_fichier((resultat.nom or "").upper())
    if (resultat.nom or "").strip() and nom_dans_fichier.upper() not in chemin.name.upper():
        _echec("le nom du fichier ne correspond pas à l'enseignant du bulletin.")


def generer_bulletin_enseignant(
    periode_id: int, enseignant_id: int, db_path: DbPath = None, utilisateur: Optional[str] = None
) -> BulletinGenere:
    """
    Génère le bulletin Word d'UN enseignant pour UNE période, à partir
    exclusivement des résultats de services/paie_service.py.

    `enseignant_id` et `periode_id` sont systématiquement propagés
    ensemble jusqu'au résultat de calcul : il n'est jamais possible de
    mélanger les données d'un enseignant avec le nom d'un autre, ni les
    données d'une période avec le libellé d'une autre (le résultat et
    le libellé de période utilisés proviennent tous deux du même appel).

    `utilisateur` (optionnel, nom d'utilisateur du module 11) est
    reporté dans l'instantané immuable de traçabilité (module 12,
    section 13) lorsque la période est VALIDEE ou CLOTUREE. Le fichier
    Word, lui, est produit dans tous les cas comme depuis le module 07 —
    l'instantané en base est un renforcement de traçabilité, pas une
    condition de génération.
    """
    try:
        resultat = calculer_paie_enseignant(periode_id, enseignant_id, db_path=db_path)
    except CalculPaieError as erreur:
        raise BulletinServiceError(str(erreur)) from erreur

    from database.repositories import periode_repository  # import local : évite un cycle au chargement du module
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)

    resultat = _statut_fige(resultat, periode, db_path)

    bulletin_existant = _bulletin_existe_deja(resultat, periode.libelle)
    if periode.statut == StatutPeriode.CLOTUREE and bulletin_existant is not None:
        raise BulletinServiceError(
            f"Un bulletin existe déjà pour {resultat.nom} {resultat.prenom} sur cette période clôturée "
            f"({bulletin_existant.name}). Il est conservé intact : la régénération est refusée pour une "
            "période clôturée."
        )

    valeurs = _preparer_valeurs_placeholder(resultat, periode)
    from services import modele_bulletin_service  # import local : évite un cycle au chargement du module
    modele = modele_bulletin_service.obtenir_modele_actif(db_path=db_path)

    nom_fichier = generer_nom_fichier_bulletin(resultat.nom, resultat.prenom, periode.libelle, modele.extension)
    dossier = _dossier_periode(periode.libelle)
    # Jamais d'écrasement silencieux (hors période clôturée déjà bloquée ci-dessus) : versionné automatiquement.
    chemin = chemin_sortie_disponible(nom_fichier, dossier=dossier)
    if modele.format == "pdf":
        try:
            contenu = modele_bulletin_service.produire("pdf", modele.contenu(), modele.zones, valeurs)
        except modele_bulletin_service.ModeleBulletinError as erreur:
            raise BulletinServiceError(f"Modèle « {modele.nom} » : {erreur}") from erreur
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)
    else:
        document = generer_document_bulletin(valeurs, template_path=modele.chemin)
        sauvegarder_document(document, chemin)

    _valider_bulletin_genere(chemin, resultat, periode.libelle)

    # Instantané immuable de traçabilité (module 12) : silencieusement
    # ignoré si la période n'est pas encore VALIDEE (trigger SQL) ou si
    # un instantané existe déjà pour ce couple enseignant/période (le
    # premier fait foi) — jamais d'exception, jamais de doublon.
    snapshot = BulletinPaie(
        enseignant_id=enseignant_id, periode_id=periode_id,
        nom_snapshot=resultat.nom, prenom_snapshot=resultat.prenom,
        sexe_snapshot=resultat.sexe, statut_snapshot=resultat.statut,
        total_heures=resultat.total_heures, taux_horaire=resultat.taux_horaire, gain_heures=resultat.gain_heures,
        prime_ap_pp=resultat.prime_ap_pp, surveillance_secretariat=resultat.surveillance_secretariat,
        indemnite_suggestion_admin=resultat.indemnite_suggestion_admin,
        base_taxable=resultat.base_taxable, taxe_5pct=resultat.taxe_5,
        retenue_amicale=resultat.retenue_amicale, dette=resultat.dette, net_a_payer=resultat.net_a_percevoir,
        utilisateur_generation=utilisateur,
    )
    bulletin_repository.enregistrer_snapshot(snapshot, db_path=db_path)

    # Registre documentaire (module 14) : best-effort, jamais bloquant
    # pour la génération du bulletin elle-même, déjà réussie à ce stade.
    from models.enums import TypeActionAudit, TypeDocument as _TypeDocument
    from services.document_service import enregistrer_document

    enregistrer_document(
        _TypeDocument.BULLETIN, chemin, periode_id=periode_id, enseignant_id=enseignant_id,
        utilisateur=utilisateur, db_path=db_path,
    )
    try:
        from database.repositories import audit_log_repository
        from models.audit_log import AuditLog
        audit_log_repository.enregistrer(
            AuditLog(
                type_action=TypeActionAudit.GENERATION_BULLETIN, entite="bulletin",
                entite_id=enseignant_id, utilisateur=utilisateur,
                details=f"{resultat.nom} {resultat.prenom} — {periode.libelle} — {chemin.name} — modèle : {modele.libelle}",
            ),
            db_path=db_path,
        )
    except Exception:  # noqa: BLE001 — l'audit ne doit jamais faire échouer une génération déjà réussie
        pass

    return BulletinGenere(enseignant_id=enseignant_id, chemin=chemin, resultat=resultat)


def generer_bulletins_groupe(
    periode_id: int, enseignant_ids: List[int], db_path: DbPath = None, utilisateur: Optional[str] = None
) -> BulletinsGeneres:
    """
    Génère un bulletin Word individuel pour chaque enseignant de la
    liste. Un échec sur un enseignant (collecté dans `erreurs`) ne
    bloque jamais la génération des autres.
    """
    resultat = BulletinsGeneres()
    for enseignant_id in enseignant_ids:
        try:
            resultat.bulletins.append(
                generer_bulletin_enseignant(periode_id, enseignant_id, db_path=db_path, utilisateur=utilisateur)
            )
        except BulletinServiceError as erreur:
            resultat.erreurs[enseignant_id] = str(erreur)
    return resultat


def creer_archive_zip(bulletins: List[BulletinGenere], libelle_periode: str) -> Path:
    """
    Regroupe plusieurs bulletins déjà générés dans une archive ZIP
    unique (data/exports/bulletins/[periode]/Bulletins_[periode].zip).
    Ne régénère aucun document : se contente d'archiver les fichiers
    .docx déjà produits par `generer_bulletin_enseignant`.
    """
    if not bulletins:
        raise BulletinServiceError("Aucun bulletin à archiver.")

    dossier = _dossier_periode(libelle_periode)
    nom_zip = f"Bulletins_{nettoyer_nom_fichier(libelle_periode.upper())}.zip"
    chemin_zip = chemin_sortie_disponible(nom_zip, dossier=dossier)

    with zipfile.ZipFile(chemin_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for bulletin in bulletins:
            archive.write(bulletin.chemin, arcname=bulletin.chemin.name)

    return chemin_zip


# ---------------------------------------------------------------------
# Consultation en lecture seule du système de bulletins existant
# (utilisé par le module 08 — tableau de bord / historique). Ne génère
# jamais de nouveau bulletin : relit uniquement le dossier d'export déjà
# alimenté par generer_bulletin_enseignant / generer_bulletins_groupe.
# ---------------------------------------------------------------------

def lister_bulletins_existants(libelle_periode: str) -> List[Path]:
    """Liste les bulletins (.docx et .pdf) déjà présents pour une période (lecture seule du dossier d'export)."""
    dossier = _dossier_periode(libelle_periode)
    if not dossier.exists():
        return []
    return sorted(p for extension in EXTENSIONS_BULLETIN for p in dossier.glob(f"Bulletin_*{extension}"))


def bulletin_deja_genere(nom: str, prenom: str, libelle_periode: str) -> bool:
    """
    Indique si au moins un bulletin a déjà été généré pour cet
    enseignant sur cette période, en relisant les noms de fichiers du
    dossier d'export (aucune génération, aucun accès base).
    """
    nom_nettoye = nettoyer_nom_fichier(nom.upper())
    prenom_nettoye = nettoyer_nom_fichier(prenom.upper())
    for chemin in lister_bulletins_existants(libelle_periode):
        nom_fichier = chemin.stem.upper()
        if nom_nettoye in nom_fichier and prenom_nettoye in nom_fichier:
            return True
    return False


def periode_a_des_bulletins(libelle_periode: str) -> bool:
    """
    Vrai si au moins un bulletin (tout enseignant confondu) a déjà été
    généré pour cette période. Utilisé par
    services/periode_service.supprimer_periode_definitivement pour
    protéger l'historique — un bulletin est une trace définitive,
    jamais supprimée par cascade.
    """
    return len(lister_bulletins_existants(libelle_periode)) > 0


def enseignant_a_des_bulletins(nom: str, prenom: str, db_path: DbPath = None) -> bool:
    """
    Vrai si au moins un bulletin a déjà été généré pour cet enseignant,
    toutes périodes confondues. Contrairement à `bulletin_deja_genere`
    (limité à une période), cette fonction parcourt l'ensemble des
    périodes existantes — nécessaire pour la protection de la
    suppression définitive d'un enseignant
    (services/enseignant_service.supprimer_enseignant_definitivement),
    qui doit être bloquée dès qu'UN SEUL bulletin existe, quelle que
    soit la période.
    """
    from database.repositories import periode_repository  # import local : évite un cycle au chargement du module

    for periode in periode_repository.lister(db_path=db_path):
        if bulletin_deja_genere(nom, prenom, periode.libelle):
            return True
    return False
