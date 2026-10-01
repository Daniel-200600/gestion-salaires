"""
Service bulletin (module 07).

Prépare les données consommées par le générateur Word
(exports/word_export.py), exclusivement à partir des résultats déjà
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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from docx import Document

from database.repositories import bulletin_repository
from exports.excel_export import chemin_sortie_disponible
from exports.word_export import (
    EXPORT_DIR_BULLETINS,
    generer_document_bulletin,
    generer_nom_fichier_bulletin,
    sauvegarder_document,
)
from models.bulletin_paie import BulletinPaie
from models.enums import StatutPeriode
from models.resultat_paie import ResultatPaie
from services.paie_service import CalculPaieError, calculer_paie_enseignant
from utils.formatters import nettoyer_nom_fichier
from utils.montant_en_lettres import montant_en_lettres

DbPath = Optional[Union[str, Path]]


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


def _preparer_valeurs_placeholder(resultat: ResultatPaie, libelle_periode: str) -> Dict[str, str]:
    """
    Construit le dict {placeholder: valeur texte} à partir d'un
    ResultatPaie déjà calculé par paie_service — aucune formule de
    paie n'est recalculée ici, uniquement de la mise en forme texte.
    """
    # Total affiché sur la ligne "Total" du modèle : dérivé de deux
    # valeurs déjà finales (base_taxable, net_a_percevoir), pas une
    # formule de paie recalculée.
    total_gains = resultat.base_taxable
    total_retenues = resultat.base_taxable - resultat.net_a_percevoir

    return {
        "{{NOM}}": resultat.nom.upper(),
        "{{PRENOM}}": resultat.prenom.upper(),
        "{{STATUT}}": resultat.statut.value,  # déjà 'V'/'P' en base, aucune conversion de valeur
        "{{PERIODE}}": libelle_periode.upper(),
        "{{TOTAL_HEURES}}": _formater_heures(resultat.total_heures),
        "{{TAUX_HORAIRE}}": str(resultat.taux_horaire),
        "{{GAIN_HEURES}}": str(resultat.gain_heures),
        "{{PRIME_AP_PP}}": str(resultat.prime_ap_pp),
        "{{SURVEILLANCE_SECRETARIAT}}": str(resultat.surveillance_secretariat),
        "{{INDEMNITE_SUGGESTION_ADMIN}}": str(resultat.indemnite_suggestion_admin),
        "{{TAXE_5}}": str(resultat.taxe_5),
        "{{RETENUE_AMICALE}}": str(resultat.retenue_amicale),
        "{{DETTE}}": str(resultat.dette),
        "{{TOTAL_GAINS}}": str(total_gains),
        "{{TOTAL_RETENUES}}": str(total_retenues),
        "{{NET_A_PERÇEVOIR}}": str(resultat.net_a_percevoir),
        "{{NET_EN_LETTRES}}": montant_en_lettres(resultat.net_a_percevoir),
        "{{DATE_GENERATION}}": datetime.now().strftime("%d/%m/%Y"),
    }


def _bulletin_existe_deja(resultat: ResultatPaie, libelle_periode: str) -> Optional[Path]:
    """Vérifie si un bulletin a déjà été généré (nom de base, sans suffixe de version) pour cet enseignant/période."""
    nom_fichier = generer_nom_fichier_bulletin(resultat.nom, resultat.prenom, libelle_periode)
    chemin = _dossier_periode(libelle_periode) / nom_fichier
    return chemin if chemin.exists() else None


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

    if not resultat.nom or not resultat.nom.strip():
        _echec("le nom de l'enseignant est manquant.")
    if not resultat.prenom or not resultat.prenom.strip():
        _echec("le prénom de l'enseignant est manquant.")
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

    try:
        document_verification = Document(chemin)
    except Exception as erreur:  # noqa: BLE001 — toute erreur d'ouverture invalide le contrôle 9
        _echec(f"le fichier .docx généré n'est pas un document valide ({erreur}).")
        return

    textes = [p.text for p in document_verification.paragraphs]
    for table in document_verification.tables:
        for ligne in table.rows:
            for cellule in ligne.cells:
                textes.extend(p.text for p in cellule.paragraphs)
    contenu = " ".join(textes)
    if "{{" in contenu or "}}" in contenu:
        _echec("un placeholder non remplacé subsiste dans le document.")

    if resultat.nom.upper() not in chemin.name.upper():
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

    bulletin_existant = _bulletin_existe_deja(resultat, periode.libelle)
    if periode.statut == StatutPeriode.CLOTUREE and bulletin_existant is not None:
        raise BulletinServiceError(
            f"Un bulletin existe déjà pour {resultat.nom} {resultat.prenom} sur cette période clôturée "
            f"({bulletin_existant.name}). Il est conservé intact : la régénération est refusée pour une "
            "période clôturée."
        )

    valeurs = _preparer_valeurs_placeholder(resultat, periode.libelle)
    document = generer_document_bulletin(valeurs)

    nom_fichier = generer_nom_fichier_bulletin(resultat.nom, resultat.prenom, periode.libelle)
    dossier = _dossier_periode(periode.libelle)
    # Jamais d'écrasement silencieux (hors période clôturée déjà bloquée ci-dessus) : versionné automatiquement.
    chemin = chemin_sortie_disponible(nom_fichier, dossier=dossier)
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
                details=f"{resultat.nom} {resultat.prenom} — {periode.libelle} — {chemin.name}",
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
    """Liste les fichiers .docx déjà présents pour une période (lecture seule du dossier d'export)."""
    dossier = _dossier_periode(libelle_periode)
    if not dossier.exists():
        return []
    return sorted(dossier.glob("Bulletin_*.docx"))


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
