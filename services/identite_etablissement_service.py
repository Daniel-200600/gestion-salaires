"""
Identité de l'établissement sur le bulletin de solde : en-tête bilingue,
logo, lieu de signature et titre du signataire.

Réglée par l'administrateur (Administration › Paramètres) et enregistrée
dans la table `parametres_paie` : elle fait donc partie de chaque
sauvegarde et revient avec la base lors d'une restauration.

Les modèles standard de l'établissement en sont dérivés — le modèle Word
toujours, le modèle PDF lorsque LibreOffice est installé sur le poste — et
écrits dans le dossier de données (`modeles_etablissement`), où
l'application les utilise à la place des modèles neutres livrés avec elle
(config.settings.chemin_modele_standard). S'ils manquent (restauration sur
un autre ordinateur, par exemple), `assurer_modeles_etablissement` les
reconstruit.

Les contrôles d'autorisation (ADMIN) sont appliqués par la façade
services/administration_service.py.
"""

import base64
import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Union

from config import settings
from database.repositories import audit_log_repository, parametres_paie_repository
from models.audit_log import AuditLog
from models.enums import TypeActionAudit
from templates import build_template
from templates.build_template import IDENTITE_NEUTRE, IdentiteEtablissement

logger = logging.getLogger("salaires_app.identite_etablissement_service")

DbPath = Optional[Union[str, Path]]

CLE_IDENTITE = "identite_etablissement"
CLE_LOGO = "logo_etablissement"

NB_LIGNES_MAX = 8
LONGUEUR_LIGNE_MAX = 90
LONGUEUR_CHAMP_MAX = 60
TAILLE_LOGO_MAX = 2 * 1024 * 1024
_SIGNATURES_IMAGE = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")


class IdentiteEtablissementError(ValueError):
    """Valeurs refusées (en-tête vide ou trop long, logo invalide...)."""


@dataclass
class RapportGeneration:
    """Modèles produits pour l'établissement."""

    modele_word: Path
    modele_pdf: Optional[Path]
    avertissement_pdf: Optional[str] = None


# ---------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------

def obtenir_identite(db_path: DbPath = None) -> Optional[IdentiteEtablissement]:
    """Identité réglée par l'administrateur, ou None si elle ne l'a jamais été."""
    brut = parametres_paie_repository.lire(CLE_IDENTITE, db_path=db_path)
    if not brut:
        return None
    try:
        donnees = json.loads(brut)
    except json.JSONDecodeError:
        logger.warning("Identité de l'établissement illisible : en-tête neutre utilisé.")
        return None
    logo = parametres_paie_repository.lire(CLE_LOGO, db_path=db_path)
    return IdentiteEtablissement(
        entete_fr=tuple(donnees.get("entete_fr", IDENTITE_NEUTRE.entete_fr)),
        entete_en=tuple(donnees.get("entete_en", IDENTITE_NEUTRE.entete_en)),
        logo=base64.b64decode(logo) if logo else None,
        lieu_signature=donnees.get("lieu_signature", IDENTITE_NEUTRE.lieu_signature),
        titre_signataire_fr=donnees.get("titre_signataire_fr", IDENTITE_NEUTRE.titre_signataire_fr),
        titre_signataire_en=donnees.get("titre_signataire_en", IDENTITE_NEUTRE.titre_signataire_en),
    )


def identite_ou_neutre(db_path: DbPath = None) -> IdentiteEtablissement:
    return obtenir_identite(db_path=db_path) or IDENTITE_NEUTRE


# ---------------------------------------------------------------------
# Contrôles
# ---------------------------------------------------------------------

def _lignes(lignes: Sequence[str], langue: str) -> List[str]:
    propres = [ligne.strip() for ligne in lignes if ligne and ligne.strip()]
    if not propres:
        raise IdentiteEtablissementError(f"L'en-tête {langue} doit contenir au moins une ligne.")
    if len(propres) > NB_LIGNES_MAX:
        raise IdentiteEtablissementError(f"L'en-tête {langue} ne doit pas dépasser {NB_LIGNES_MAX} lignes.")
    trop_longues = [ligne for ligne in propres if len(ligne) > LONGUEUR_LIGNE_MAX]
    if trop_longues:
        raise IdentiteEtablissementError(
            f"Ligne trop longue dans l'en-tête {langue} ({LONGUEUR_LIGNE_MAX} caractères au plus) : "
            f"« {trop_longues[0][:40]}… »."
        )
    return propres


def _champ(valeur: str, libelle: str) -> str:
    valeur = (valeur or "").strip()
    if not valeur:
        raise IdentiteEtablissementError(f"Indiquez {libelle}.")
    if len(valeur) > LONGUEUR_CHAMP_MAX:
        raise IdentiteEtablissementError(f"{libelle.capitalize()} : {LONGUEUR_CHAMP_MAX} caractères au plus.")
    return valeur


def verifier_logo(contenu: bytes) -> bytes:
    """Le logo doit être une vraie image PNG ou JPEG de 2 Mo au plus."""
    if not contenu:
        raise IdentiteEtablissementError("Le fichier du logo est vide.")
    if len(contenu) > TAILLE_LOGO_MAX:
        raise IdentiteEtablissementError("Le logo dépasse 2 Mo : choisissez une image plus légère.")
    if not contenu.startswith(_SIGNATURES_IMAGE):
        raise IdentiteEtablissementError("Le logo doit être une image PNG ou JPEG.")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(contenu)) as image:
            image.verify()
    except Exception as erreur:  # noqa: BLE001 — toute image illisible est refusée
        raise IdentiteEtablissementError("Le fichier du logo est endommagé ou n'est pas une image.") from erreur
    return contenu


# ---------------------------------------------------------------------
# Production des modèles
# ---------------------------------------------------------------------

def generer_modeles(identite: IdentiteEtablissement) -> RapportGeneration:
    """
    Produit les modèles standard de l'établissement dans le dossier
    `modeles_etablissement`. Le modèle PDF exige LibreOffice : s'il est
    absent, un ancien modèle PDF de l'établissement est retiré (il porterait
    un en-tête périmé) et le modèle PDF neutre reste utilisé.
    """
    dossier = settings.MODELES_ETABLISSEMENT_DIR
    word = build_template.construire_template(dossier / build_template.CHEMIN_TEMPLATE.name, identite)
    chemin_pdf = dossier / build_template.CHEMIN_MODELE_PDF.name
    chemin_zones = dossier / build_template.CHEMIN_ZONES_PDF.name

    avertissement = None
    if build_template.trouver_libreoffice() is None:
        avertissement = ("LibreOffice n'est pas installé sur cet ordinateur : le modèle PDF standard garde "
                         "l'en-tête neutre. Utilisez le modèle Word standard, ou importez votre propre modèle PDF.")
    else:
        try:
            return RapportGeneration(word, build_template.construire_modele_pdf(chemin_pdf, chemin_zones, identite))
        except Exception as erreur:  # noqa: BLE001 — le modèle Word reste utilisable
            logger.error("Modèle PDF de l'établissement non produit : %s", erreur)
            avertissement = ("Le modèle PDF standard n'a pas pu être produit : il garde l'en-tête neutre. "
                             "Le modèle Word standard est à jour.")
    chemin_pdf.unlink(missing_ok=True)
    chemin_zones.unlink(missing_ok=True)
    return RapportGeneration(word, None, avertissement)


def assurer_modeles_etablissement(db_path: DbPath = None) -> Optional[RapportGeneration]:
    """
    Reconstruit les modèles de l'établissement s'ils manquent alors qu'une
    identité est réglée (base restaurée sur un autre poste, dossier de
    données effacé...). Ne lève jamais d'exception.
    """
    try:
        identite = obtenir_identite(db_path=db_path)
        modele_word = settings.MODELES_ETABLISSEMENT_DIR / build_template.CHEMIN_TEMPLATE.name
        if identite is None or modele_word.exists():
            return None
        logger.info("Modèles de l'établissement absents : reconstruction.")
        return generer_modeles(identite)
    except Exception as erreur:  # noqa: BLE001 — jamais bloquant au démarrage
        logger.error("Reconstruction des modèles de l'établissement impossible : %s", erreur)
        return None


# ---------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------

def enregistrer_identite(
    entete_fr: Sequence[str],
    entete_en: Sequence[str],
    lieu_signature: str,
    titre_signataire_fr: str,
    titre_signataire_en: str,
    logo: Optional[bytes] = None,
    retirer_logo: bool = False,
    utilisateur: Optional[str] = None,
    db_path: DbPath = None,
) -> RapportGeneration:
    """
    Contrôle puis enregistre l'identité de l'établissement, et produit ses
    modèles de bulletin. Sans nouveau logo, le logo déjà enregistré est
    conservé (sauf `retirer_logo`).
    """
    lignes_fr = _lignes(entete_fr, "français")
    lignes_en = _lignes(entete_en, "anglais")
    lieu = _champ(lieu_signature, "le lieu de signature")
    titre_fr = _champ(titre_signataire_fr, "le titre du signataire (français)")
    titre_en = _champ(titre_signataire_en, "le titre du signataire (anglais)")
    if logo is not None:
        logo = verifier_logo(logo)
    elif not retirer_logo:
        actuelle = obtenir_identite(db_path=db_path)
        logo = actuelle.logo if actuelle else None

    identite = IdentiteEtablissement(
        entete_fr=tuple(lignes_fr), entete_en=tuple(lignes_en), logo=logo,
        lieu_signature=lieu, titre_signataire_fr=titre_fr, titre_signataire_en=titre_en,
    )
    donnees = {
        "entete_fr": lignes_fr, "entete_en": lignes_en, "lieu_signature": lieu,
        "titre_signataire_fr": titre_fr, "titre_signataire_en": titre_en,
    }
    parametres_paie_repository.ecrire(CLE_IDENTITE, json.dumps(donnees, ensure_ascii=False),
                                      utilisateur=utilisateur, db_path=db_path)
    parametres_paie_repository.ecrire(CLE_LOGO, base64.b64encode(logo).decode("ascii") if logo else "",
                                      utilisateur=utilisateur, db_path=db_path)
    audit_log_repository.enregistrer(
        AuditLog(type_action=TypeActionAudit.PARAMETRE_PAIE_MODIFIE, entite="identite_etablissement",
                 entite_id=None, utilisateur=utilisateur,
                 details=f"En-tête du bulletin : {lignes_fr[-1]} — logo {'présent' if logo else 'absent'}"),
        db_path=db_path,
    )
    return generer_modeles(identite)


def revenir_a_l_entete_neutre(utilisateur: Optional[str] = None, db_path: DbPath = None) -> None:
    """Efface l'identité de l'établissement et ses modèles : les modèles neutres reprennent la main."""
    parametres_paie_repository.ecrire(CLE_IDENTITE, "", utilisateur=utilisateur, db_path=db_path)
    parametres_paie_repository.ecrire(CLE_LOGO, "", utilisateur=utilisateur, db_path=db_path)
    for chemin in (build_template.CHEMIN_TEMPLATE, build_template.CHEMIN_MODELE_PDF, build_template.CHEMIN_ZONES_PDF):
        (settings.MODELES_ETABLISSEMENT_DIR / chemin.name).unlink(missing_ok=True)
    audit_log_repository.enregistrer(
        AuditLog(type_action=TypeActionAudit.PARAMETRE_PAIE_MODIFIE, entite="identite_etablissement",
                 entite_id=None, utilisateur=utilisateur, details="Retour à l'en-tête neutre du bulletin"),
        db_path=db_path,
    )
