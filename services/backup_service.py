"""
Service de sauvegarde et de restauration sécurisée de la base SQLite
(module 10).

Utilise l'API native `sqlite3.Connection.backup()` plutôt qu'une copie
de fichier brute : cette API produit une copie cohérente de la base
même si une écriture est en cours, ce qu'une copie de fichier naïve ne
garantit pas.

Aucune formule de paie, aucune règle métier ici : ce module ne
manipule que le FICHIER de base de données dans son ensemble.
"""

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config.settings import BACKUP_DIR, DB_PATH
from database.initialization import get_table_names
from models.audit_log import AuditLog
from models.enums import TypeActionAudit

logger = logging.getLogger("salaires_app.backup_service")

PREFIXE_SAUVEGARDE = "backup_"
SUFFIXE_SAUVEGARDE = ".db"
PREFIXE_SAUVEGARDE_SECURITE = "avant_restauration_"

# Signature de fichier attendue en tête d'une base SQLite valide.
_ENTETE_SQLITE = b"SQLite format 3\x00"


class BackupServiceError(Exception):
    """Erreur de sauvegarde ou de restauration — toujours un message compréhensible, jamais un traceback brut."""


@dataclass
class InfoSauvegarde:
    """Métadonnées d'une sauvegarde existante, prêtes à afficher côté interface."""

    nom: str
    chemin: Path
    date_creation: datetime
    taille_octets: int

    @property
    def taille_lisible(self) -> str:
        taille = float(self.taille_octets)
        for unite in ("o", "Ko", "Mo", "Go"):
            if taille < 1024:
                return f"{taille:.1f} {unite}"
            taille /= 1024
        return f"{taille:.1f} To"


@dataclass
class ResultatIntegrite:
    """Résultat de la vérification d'intégrité d'un fichier de base."""

    valide: bool
    message: str


@dataclass
class RapportRestauration:
    """Résultat complet d'une opération de restauration."""

    reussie: bool
    message: str
    sauvegarde_securite: Optional[Path] = None


def _horodatage() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _nom_sauvegarde_disponible(dossier: Path, prefixe: str = PREFIXE_SAUVEGARDE) -> Path:
    """
    Construit un nom de sauvegarde horodaté à la seconde ; en cas de
    collision improbable (deux sauvegardes lancées à la même seconde),
    ajoute un suffixe numérique plutôt que d'écraser silencieusement
    une sauvegarde existante.
    """
    base = f"{prefixe}{_horodatage()}"
    candidat = dossier / f"{base}{SUFFIXE_SAUVEGARDE}"
    compteur = 1
    while candidat.exists():
        candidat = dossier / f"{base}_{compteur}{SUFFIXE_SAUVEGARDE}"
        compteur += 1
    return candidat


def verifier_integrite(chemin_base: Path) -> ResultatIntegrite:
    """
    Vérifie qu'un fichier est une base SQLite valide et intègre.

    Contrôles, dans l'ordre :
    1. le fichier existe et n'est pas vide ;
    2. son en-tête correspond à la signature SQLite officielle ;
    3. `PRAGMA integrity_check` répond `ok`.

    Ne lève jamais d'exception : toute anomalie est retournée sous
    forme de ResultatIntegrite(valide=False, message=<explication>).
    """
    if not chemin_base.exists():
        return ResultatIntegrite(False, "Le fichier n'existe pas.")

    if chemin_base.stat().st_size == 0:
        return ResultatIntegrite(False, "Le fichier est vide.")

    try:
        with open(chemin_base, "rb") as fichier:
            entete = fichier.read(16)
    except OSError as erreur:
        return ResultatIntegrite(False, f"Fichier illisible : {erreur}")

    if entete != _ENTETE_SQLITE:
        return ResultatIntegrite(False, "Le fichier n'est pas une base SQLite valide (en-tête incorrect).")

    try:
        conn = sqlite3.connect(f"file:{chemin_base}?mode=ro", uri=True)
        try:
            resultat = conn.execute("PRAGMA integrity_check;").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as erreur:
        return ResultatIntegrite(False, f"Base corrompue ou illisible : {erreur}")

    if resultat is None or resultat[0] != "ok":
        detail = resultat[0] if resultat else "réponse vide"
        return ResultatIntegrite(False, f"Intégrité SQLite échouée : {detail}")

    return ResultatIntegrite(True, "Base valide.")


def creer_sauvegarde(
    db_path: Optional[Path] = None, backup_dir: Optional[Path] = None, prefixe: str = PREFIXE_SAUVEGARDE
) -> Path:
    """
    Crée une copie cohérente de la base via l'API native SQLite
    `Connection.backup()` (jamais une simple copie de fichier, qui
    pourrait capturer un état incohérent si une écriture est en cours).

    Crée automatiquement le dossier de destination s'il n'existe pas.
    Le nom du fichier est horodaté (ex : backup_2026-09-14_165500.db) ;
    une collision de nom (même seconde) ne provoque jamais un
    écrasement silencieux.
    """
    source = Path(db_path) if db_path is not None else DB_PATH
    dossier = Path(backup_dir) if backup_dir is not None else BACKUP_DIR
    dossier.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        raise BackupServiceError(f"Impossible de sauvegarder : la base source est introuvable ({source}).")

    destination = _nom_sauvegarde_disponible(dossier, prefixe=prefixe)

    try:
        conn_source = sqlite3.connect(source)
        try:
            conn_destination = sqlite3.connect(destination)
            try:
                conn_source.backup(conn_destination)
            finally:
                conn_destination.close()
        finally:
            conn_source.close()
    except sqlite3.Error as erreur:
        destination.unlink(missing_ok=True)  # jamais de sauvegarde partielle sur disque
        logger.error("Échec de la sauvegarde de %s : %s", source, erreur)
        raise BackupServiceError(f"La sauvegarde a échoué : {erreur}") from erreur

    logger.info("Sauvegarde créée : %s", destination.name)
    return destination


def lister_sauvegardes(backup_dir: Optional[Path] = None) -> List[InfoSauvegarde]:
    """Liste les sauvegardes disponibles, les plus récentes en premier. Ne lève jamais si le dossier est absent."""
    dossier = Path(backup_dir) if backup_dir is not None else BACKUP_DIR
    if not dossier.exists():
        return []

    sauvegardes = []
    for chemin in dossier.glob(f"*{SUFFIXE_SAUVEGARDE}"):
        try:
            stat = chemin.stat()
        except OSError:
            continue
        sauvegardes.append(InfoSauvegarde(
            nom=chemin.name,
            chemin=chemin,
            date_creation=datetime.fromtimestamp(stat.st_mtime),
            taille_octets=stat.st_size,
        ))

    return sorted(sauvegardes, key=lambda s: s.date_creation, reverse=True)


def restaurer_sauvegarde(
    chemin_sauvegarde: Path,
    confirmation: bool = False,
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> RapportRestauration:
    """
    Restaure une sauvegarde vers la base active, avec toutes les
    protections requises :

    1. exige une confirmation explicite ;
    2. vérifie que le fichier de sauvegarde est une base SQLite valide
       et intègre (`verifier_integrite`) — refuse sinon ;
    3. crée automatiquement une SAUVEGARDE DE SÉCURITÉ de la base
       actuelle avant tout remplacement (jamais d'écrasement direct) ;
    4. effectue la restauration via l'API native SQLite `backup()` ;
    5. vérifie la nouvelle base (intégrité + tables attendues) ;
    6. en cas d'échec à cette dernière étape, restaure automatiquement
       la sauvegarde de sécurité prise à l'étape 3 (rollback complet :
       la base active n'est jamais laissée dans un état pire qu'avant
       la tentative) ;
    7. journalise l'opération dans les logs techniques ET dans l'audit
       métier (TypeActionAudit.RESTAURATION_SAUVEGARDE), qu'elle
       réussisse ou échoue.
    """
    cible = Path(db_path) if db_path is not None else DB_PATH
    dossier_sauvegardes = Path(backup_dir) if backup_dir is not None else BACKUP_DIR

    if not confirmation:
        raise BackupServiceError("La restauration nécessite une confirmation explicite.")

    resultat_integrite = verifier_integrite(chemin_sauvegarde)
    if not resultat_integrite.valide:
        message = f"Restauration refusée : {resultat_integrite.message}"
        logger.warning(message)
        _journaliser_audit(cible, "Refusé (fichier invalide) — " + resultat_integrite.message)
        return RapportRestauration(reussie=False, message=message)

    # Sauvegarde de sécurité de l'état actuel, AVANT tout remplacement.
    sauvegarde_securite: Optional[Path] = None
    if cible.exists():
        try:
            sauvegarde_securite = creer_sauvegarde(
                db_path=cible, backup_dir=dossier_sauvegardes, prefixe=PREFIXE_SAUVEGARDE_SECURITE
            )
        except BackupServiceError as erreur:
            message = f"Restauration annulée : impossible de créer la sauvegarde de sécurité préalable ({erreur})."
            logger.error(message)
            _journaliser_audit(cible, "Refusé (échec sauvegarde de sécurité)")
            return RapportRestauration(reussie=False, message=message)

    # Restauration proprement dite (API native SQLite, pas une copie brute).
    try:
        conn_source = sqlite3.connect(chemin_sauvegarde)
        try:
            conn_destination = sqlite3.connect(cible)
            try:
                conn_source.backup(conn_destination)
            finally:
                conn_destination.close()
        finally:
            conn_source.close()
    except sqlite3.Error as erreur:
        message = f"La restauration a échoué pendant la copie : {erreur}"
        logger.error(message)
        if sauvegarde_securite is not None:
            _restaurer_fichier_brut(sauvegarde_securite, cible)
            message += " La base précédente a été restaurée automatiquement."
        _journaliser_audit(cible, "Échec pendant la copie — état précédent restauré")
        return RapportRestauration(reussie=False, message=message, sauvegarde_securite=sauvegarde_securite)

    # Vérification post-restauration : intégrité + tables attendues.
    resultat_post = verifier_integrite(cible)
    tables_presentes = set(get_table_names(cible)) if resultat_post.valide else set()
    tables_attendues = {"enseignants", "periodes_paie", "audit_log"}  # cœur minimal attendu

    if not resultat_post.valide or not tables_attendues.issubset(tables_presentes):
        message = "La base restaurée est invalide ou incomplète."
        logger.error(message)
        if sauvegarde_securite is not None:
            _restaurer_fichier_brut(sauvegarde_securite, cible)
            message += " L'état précédent a été restauré automatiquement."
        _journaliser_audit(cible, "Échec post-vérification — état précédent restauré")
        return RapportRestauration(reussie=False, message=message, sauvegarde_securite=sauvegarde_securite)

    logger.info("Restauration réussie depuis %s", chemin_sauvegarde.name)
    _journaliser_audit(cible, f"Succès depuis {chemin_sauvegarde.name}")
    return RapportRestauration(
        reussie=True,
        message="Restauration effectuée avec succès.",
        sauvegarde_securite=sauvegarde_securite,
    )


def _restaurer_fichier_brut(source: Path, destination: Path) -> None:
    """Copie de secours en dernier recours (rollback), utilisée uniquement après l'échec d'une restauration."""
    try:
        shutil.copy2(source, destination)
    except OSError as erreur:
        logger.critical(
            "ÉCHEC CRITIQUE : impossible de restaurer automatiquement la sauvegarde de sécurité %s vers %s (%s). "
            "Une intervention manuelle est nécessaire.",
            source, destination, erreur,
        )


def _journaliser_audit(cible: Path, resultat: str) -> None:
    """Journalise la tentative de restauration dans l'audit métier (jamais dans les logs techniques uniquement)."""
    try:
        from database.repositories import audit_log_repository

        entree = AuditLog(
            type_action=TypeActionAudit.RESTAURATION_SAUVEGARDE,
            entite="base_de_donnees",
            entite_id=None,
            details=resultat,
        )
        audit_log_repository.enregistrer(entree, db_path=cible)
    except Exception as erreur:  # noqa: BLE001 — l'audit ne doit jamais faire planter la restauration elle-même
        logger.warning("Impossible d'écrire l'entrée d'audit de restauration : %s", erreur)


# ---------------------------------------------------------------------
# Sauvegarde complète (base + documents) — module 14, section 36
# ---------------------------------------------------------------------
# IMPORTANT : `creer_sauvegarde()` ci-dessus ne sauvegarde QUE la base
# SQLite, exactement comme depuis le module 10 — ce comportement reste
# strictement inchangé (tous les tests existants continuent de le
# vérifier). Les documents (bulletins, exports) vivent sur le système
# de fichiers, hors de la base : une sauvegarde de la seule base ne
# les inclut jamais. `creer_sauvegarde_complete` est une fonction
# NOUVELLE et SÉPARÉE, à utiliser explicitement lorsqu'une sauvegarde
# incluant aussi les documents est nécessaire.

PREFIXE_ARCHIVE_COMPLETE = "Backup_Complet_"


def creer_sauvegarde_complete(
    db_path: Optional[Path] = None,
    dossier_documents: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    prefixe_base: str = PREFIXE_SAUVEGARDE,
    prefixe_archive: str = PREFIXE_ARCHIVE_COMPLETE,
) -> Path:
    """
    Produit une archive unique `Backup_Complet_{date}.zip` contenant à
    la fois une sauvegarde cohérente de la base SQLite (même mécanisme
    que `creer_sauvegarde`) et une copie de `dossier_documents` (les
    fichiers déjà générés : bulletins, exports). Ne remplace pas
    `creer_sauvegarde` : les deux coexistent, chacune pour un usage
    différent.

    `prefixe_base` / `prefixe_archive` permettent de distinguer une
    sauvegarde prise automatiquement avant une opération sensible (ex :
    réinitialisation des données) d'une sauvegarde manuelle ; les
    valeurs par défaut conservent le nommage historique.
    """
    import zipfile as _zipfile

    dossier = Path(backup_dir) if backup_dir is not None else BACKUP_DIR
    dossier.mkdir(parents=True, exist_ok=True)

    sauvegarde_db = creer_sauvegarde(db_path=db_path, backup_dir=dossier, prefixe=prefixe_base)

    horodatage = _horodatage()
    chemin_zip = dossier / f"{prefixe_archive}{horodatage}.zip"
    compteur = 1
    while chemin_zip.exists():
        chemin_zip = dossier / f"{prefixe_archive}{horodatage}_{compteur}.zip"
        compteur += 1

    with _zipfile.ZipFile(chemin_zip, "w", _zipfile.ZIP_DEFLATED) as archive:
        archive.write(sauvegarde_db, arcname=f"base_de_donnees/{sauvegarde_db.name}")
        if dossier_documents is not None and dossier_documents.exists():
            for fichier in dossier_documents.rglob("*"):
                if fichier.is_file():
                    archive.write(fichier, arcname=f"documents/{fichier.relative_to(dossier_documents)}")

    logger.info("Sauvegarde complète créée : %s", chemin_zip.name)
    return chemin_zip
