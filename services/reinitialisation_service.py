"""
Réinitialisation complète des données MÉTIER de l'application.

RÉINITIALISER LES DONNÉES ≠ RÉINITIALISER LES COMPTES.

Cette opération remet l'application dans un état métier vierge
(aucun enseignant, aucune période, aucune donnée de paie, aucun
bulletin, aucun document généré, aucun import, aucune alerte) tout en
conservant strictement à l'identique :

- la table `utilisateurs` (identifiants, mots de passe hachés, rôles,
  statut actif/inactif, dates) — jamais lue autrement que pour
  vérifier qu'elle n'a pas changé ;
- le journal d'audit en entier (sécurité ET historique métier : un
  administrateur ne peut pas effacer la trace de ce qui a été fait) ;
- la configuration : paramètres de l'établissement, schéma, sauvegardes,
  journaux techniques, modèle de bulletin.

La liste des tables traitées provient de l'analyse du schéma réel
(database/schema.sql) ; un test vérifie que toute table du schéma est
classée soit dans `CATEGORIES_SUPPRIMEES`, soit dans
`TABLES_CONSERVEES`, afin qu'une table ajoutée plus tard ne soit
jamais oubliée silencieusement.

Protections, dans l'ordre d'exécution :
1. autorisation vérifiée DANS ce service (rôle relu en base) ;
2. confirmation explicite + phrase de confirmation saisie ;
3. contrôle d'intégrité de la base avant toute action ;
4. sauvegarde complète automatique (base + documents) ;
5. mise à l'écart réversible des fichiers générés ;
6. suppression en UNE transaction SQLite, avec vérifications avant
   validation (tables vides, comptes identiques, déclencheurs de
   protection rétablis, clés étrangères, intégrité) ;
7. vérification d'intégrité après validation ; en cas d'échec,
   restauration automatique de la sauvegarde ;
8. journalisation (auteur, date, résultat, volumes par catégorie),
   sans aucune donnée d'authentification.
"""

import hashlib
import logging
import re
import shutil
import sqlite3
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from config.settings import BACKUP_DIR, DB_PATH
from models.audit_log import AuditLog
from models.enums import TypeActionAudit
from services import backup_service, permission_service
from services.autorisation_service import AutorisationRefuseeError, exiger_permission_utilisateur

logger = logging.getLogger("salaires_app.reinitialisation_service")

DbPath = Optional[Union[str, Path]]

# Phrase à saisir manuellement. La variante sans accent est acceptée
# car la majuscule accentuée est difficile à saisir sur certains
# claviers ; la casse, elle, doit être exacte (majuscules).
PHRASE_CONFIRMATION = "RÉINITIALISER"
_PHRASES_ACCEPTEES = {"RÉINITIALISER", "REINITIALISER"}

_MOTIF_DECLENCHEUR_SUPPRESSION = re.compile(r"\b(BEFORE|AFTER|INSTEAD\s+OF)\s+DELETE\b", re.IGNORECASE)

PREFIXE_SAUVEGARDE_BASE = "avant_reinitialisation_"
PREFIXE_SAUVEGARDE_ARCHIVE = "Avant_Reinitialisation_"
SOUS_DOSSIERS_EXPORTS_RECREES = ("bulletins",)


@dataclass(frozen=True)
class CategorieDonnees:
    table: str
    libelle: str


# Ordre de suppression : dépendances d'abord, tables référencées ensuite
# (les clés étrangères RESTRICT restent actives pendant toute l'opération).
CATEGORIES_SUPPRIMEES: Tuple[CategorieDonnees, ...] = (
    CategorieDonnees("alertes", "Alertes et notifications"),
    CategorieDonnees("import_erreurs", "Erreurs d'importation"),
    CategorieDonnees("imports", "Historique des importations"),
    CategorieDonnees("documents", "Registre des documents générés"),
    CategorieDonnees("bulletins_paie", "Bulletins de paie"),
    CategorieDonnees("saisies_heures", "Heures saisies"),
    CategorieDonnees("elements_remuneration", "Primes et indemnités"),
    CategorieDonnees("retenues", "Retenues"),
    CategorieDonnees("periodes_paie", "Périodes de paie"),
    CategorieDonnees("enseignants", "Enseignants"),
)

TABLES_CONSERVEES: Dict[str, str] = {
    "utilisateurs": "Comptes utilisateurs : identifiants, mots de passe, rôles et statut",
    "audit_log": "Journal d'audit complet : sécurité, administration et historique métier",
    "parametres_paie": "Paramètres de paie : taux de taxe par défaut, modèle de bulletin actif",
    "modeles_bulletin": "Modèles de bulletin importés (Word, PDF)",
}

# Le journal d'audit est conservé EN ENTIER, historique métier compris
# (calculs, validations, exports...) : il doit permettre de retracer ce
# qui a été fait sur les données, y compris par l'administrateur qui
# lance la réinitialisation. La réinitialisation y ajoute sa propre entrée.

LIBELLE_FICHIERS = "Fichiers générés (bulletins, exports, archives)"

ELEMENTS_CONSERVES: Tuple[str, ...] = (
    "Comptes utilisateurs, noms d'utilisateur et mots de passe",
    "Rôles et permissions",
    "Session en cours et paramètres de sécurité",
    "Journal d'audit complet (connexions, comptes, sauvegardes, calculs, validations, exports)",
    "Paramètres de l'établissement",
    "Sauvegardes existantes",
    "Journaux techniques",
    "Modèles de bulletin (standard et importés) et modèle actif",
    "Taux de taxe par défaut des nouvelles périodes",
)


class ReinitialisationError(Exception):
    """Réinitialisation impossible ou refusée — message toujours compréhensible."""


class ConfirmationInvalideError(ReinitialisationError):
    """La confirmation explicite ou la phrase de confirmation est absente ou incorrecte."""


@dataclass
class ApercuReinitialisation:
    """Ce qui sera supprimé et ce qui sera conservé, calculé sur les données réelles."""

    elements_a_supprimer: Dict[str, int]
    fichiers_a_supprimer: int
    taille_fichiers_octets: int
    comptes_conserves: int
    entrees_audit_conservees: int
    tables_non_classees: List[str] = field(default_factory=list)

    @property
    def total_elements(self) -> int:
        return sum(self.elements_a_supprimer.values()) + self.fichiers_a_supprimer


@dataclass
class RapportReinitialisation:
    reussie: bool
    message: str
    sauvegarde_archive: Optional[Path] = None
    sauvegarde_base: Optional[Path] = None
    elements_supprimes: Dict[str, int] = field(default_factory=dict)
    fichiers_supprimes: int = 0
    comptes_conserves: int = 0
    restauration_effectuee: bool = False


# ---------------------------------------------------------------------
# Utilitaires internes
# ---------------------------------------------------------------------

def _dossier_exports_par_defaut() -> Path:
    from exports.excel_export import EXPORT_DIR

    return EXPORT_DIR


def _connexion(cible: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(cible, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _tables_existantes(conn: sqlite3.Connection) -> List[str]:
    lignes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [ligne["name"] for ligne in lignes]


def _compter(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def _empreinte_comptes(conn: sqlite3.Connection) -> str:
    """
    Empreinte de l'intégralité de la table `utilisateurs`, utilisée
    uniquement en mémoire pour prouver qu'elle n'a pas changé. Jamais
    journalisée, jamais renvoyée à l'appelant.
    """
    colonnes = [c["name"] for c in conn.execute("PRAGMA table_info(utilisateurs)").fetchall()]
    condensat = hashlib.sha256()
    for ligne in conn.execute("SELECT * FROM utilisateurs ORDER BY id").fetchall():
        condensat.update(repr(tuple(ligne[c] for c in colonnes)).encode("utf-8"))
    return condensat.hexdigest()


def _declencheurs_de_suppression(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    """
    Déclencheurs qui bloquent une suppression sur une table métier
    (ex : bulletins immuables, périodes non supprimables hors
    brouillon). Leur définition exacte est relue en base afin d'être
    recréée à l'identique dans la même transaction.
    """
    tables = tuple(c.table for c in CATEGORIES_SUPPRIMEES)
    marqueurs = ",".join("?" for _ in tables)
    lignes = conn.execute(
        f"SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name IN ({marqueurs})",
        tables,
    ).fetchall()
    return [
        (ligne["name"], ligne["sql"])
        for ligne in lignes
        if ligne["sql"] and _MOTIF_DECLENCHEUR_SUPPRESSION.search(ligne["sql"])
    ]


def _noms_declencheurs(conn: sqlite3.Connection) -> set:
    return {l["name"] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()}


def _inventaire_fichiers(dossier: Path) -> Tuple[int, int]:
    if not dossier.exists():
        return 0, 0
    nombre, taille = 0, 0
    for chemin in dossier.rglob("*"):
        if chemin.is_file():
            nombre += 1
            try:
                taille += chemin.stat().st_size
            except OSError:
                pass
    return nombre, taille


def phrase_confirmation_valide(phrase: Optional[str]) -> bool:
    """Vrai si la phrase saisie correspond exactement à la phrase de confirmation attendue."""
    if not isinstance(phrase, str):
        return False
    return unicodedata.normalize("NFC", phrase.strip()) in _PHRASES_ACCEPTEES


def _journaliser(
    cible: Path, type_action: TypeActionAudit, auteur: str, details: str, conn: Optional[sqlite3.Connection] = None
) -> None:
    from database.repositories import audit_log_repository

    entree = AuditLog(
        type_action=type_action, entite="donnees_metier", entite_id=None, utilisateur=auteur, details=details
    )
    try:
        audit_log_repository.enregistrer(entree, db_path=cible, conn=conn)
    except Exception as erreur:  # noqa: BLE001 — l'audit ne doit jamais masquer le résultat réel
        if conn is not None:
            raise
        logger.error("Impossible d'enregistrer l'audit de réinitialisation : %s", erreur)


def _resume_volumes(elements: Dict[str, int], fichiers: int) -> str:
    parties = [f"{libelle} : {nombre}" for libelle, nombre in elements.items()]
    parties.append(f"{LIBELLE_FICHIERS} : {fichiers}")
    return " ; ".join(parties)


# ---------------------------------------------------------------------
# Aperçu (lecture seule)
# ---------------------------------------------------------------------

def apercu_reinitialisation(db_path: DbPath = None, dossier_exports: Optional[Path] = None) -> ApercuReinitialisation:
    """Calcule, sans rien modifier, les volumes qui seraient supprimés et conservés."""
    cible = Path(db_path) if db_path is not None else DB_PATH
    dossier = Path(dossier_exports) if dossier_exports is not None else _dossier_exports_par_defaut()

    conn = _connexion(cible)
    try:
        existantes = set(_tables_existantes(conn))
        elements = {
            c.libelle: _compter(conn, c.table) for c in CATEGORIES_SUPPRIMEES if c.table in existantes
        }
        comptes = _compter(conn, "utilisateurs") if "utilisateurs" in existantes else 0
        audit_total = _compter(conn, "audit_log") if "audit_log" in existantes else 0
        classees = {c.table for c in CATEGORIES_SUPPRIMEES} | set(TABLES_CONSERVEES)
        non_classees = sorted(existantes - classees)
    finally:
        conn.close()

    nombre_fichiers, taille = _inventaire_fichiers(dossier)
    return ApercuReinitialisation(
        elements_a_supprimer=elements,
        fichiers_a_supprimer=nombre_fichiers,
        taille_fichiers_octets=taille,
        comptes_conserves=comptes,
        entrees_audit_conservees=audit_total,
        tables_non_classees=non_classees,
    )


# ---------------------------------------------------------------------
# Étapes de l'opération (fonctions séparées : testables individuellement)
# ---------------------------------------------------------------------

def _creer_sauvegarde_prealable(cible: Path, dossier_exports: Path, dossier_sauvegardes: Path) -> Tuple[Path, Path]:
    archive = backup_service.creer_sauvegarde_complete(
        db_path=cible,
        dossier_documents=dossier_exports,
        backup_dir=dossier_sauvegardes,
        prefixe_base=PREFIXE_SAUVEGARDE_BASE,
        prefixe_archive=PREFIXE_SAUVEGARDE_ARCHIVE,
    )
    with zipfile.ZipFile(archive) as zf:
        noms_base = [n for n in zf.namelist() if n.startswith("base_de_donnees/")]
    if not noms_base:
        raise backup_service.BackupServiceError("La sauvegarde préalable ne contient pas la base de données.")
    sauvegarde_base = dossier_sauvegardes / Path(noms_base[0]).name
    verification = backup_service.verifier_integrite(sauvegarde_base)
    if not verification.valide:
        raise backup_service.BackupServiceError(f"Sauvegarde préalable invalide : {verification.message}")
    return archive, sauvegarde_base


def _mettre_fichiers_a_l_ecart(dossier_exports: Path) -> Optional[Path]:
    """
    Déplace le contenu du dossier des fichiers générés dans un dossier
    temporaire voisin (même disque : simple renommage). Réversible
    jusqu'à la validation finale.
    """
    if not dossier_exports.exists() or not any(dossier_exports.iterdir()):
        return None
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dossier_attente = dossier_exports.parent / f".reinitialisation_en_cours_{horodatage}"
    dossier_attente.mkdir(parents=True, exist_ok=False)
    deplaces: List[Path] = []
    try:
        for element in list(dossier_exports.iterdir()):
            destination = dossier_attente / element.name
            shutil.move(str(element), str(destination))
            deplaces.append(destination)
    except OSError:
        _remettre_fichiers_en_place(dossier_attente, dossier_exports)
        raise
    return dossier_attente


def _remettre_fichiers_en_place(dossier_attente: Optional[Path], dossier_exports: Path) -> None:
    if dossier_attente is None or not dossier_attente.exists():
        return
    dossier_exports.mkdir(parents=True, exist_ok=True)
    for element in list(dossier_attente.iterdir()):
        destination = dossier_exports / element.name
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.move(str(element), str(destination))
    shutil.rmtree(dossier_attente, ignore_errors=True)


def _recreer_dossiers_exports(dossier_exports: Path) -> None:
    dossier_exports.mkdir(parents=True, exist_ok=True)
    for sous_dossier in SOUS_DOSSIERS_EXPORTS_RECREES:
        (dossier_exports / sous_dossier).mkdir(parents=True, exist_ok=True)


def _verifier_etat_avant_validation(
    conn: sqlite3.Connection, empreinte_comptes: str, declencheurs_attendus: set
) -> None:
    """Contrôles exécutés DANS la transaction : tout échec provoque un ROLLBACK complet."""
    for categorie in CATEGORIES_SUPPRIMEES:
        if _compter(conn, categorie.table) != 0:
            raise ReinitialisationError(f"La table {categorie.table} n'a pas pu être vidée.")
    if _empreinte_comptes(conn) != empreinte_comptes:
        raise ReinitialisationError("Les comptes utilisateurs ont été modifiés : opération annulée.")
    if _noms_declencheurs(conn) != declencheurs_attendus:
        raise ReinitialisationError("Les règles de protection de la base n'ont pas pu être rétablies.")
    if conn.execute("PRAGMA foreign_key_check;").fetchall():
        raise ReinitialisationError("Incohérence de clés étrangères détectée : opération annulée.")
    resultat = conn.execute("PRAGMA integrity_check;").fetchone()
    if resultat is None or resultat[0] != "ok":
        raise ReinitialisationError("Contrôle d'intégrité SQLite en échec : opération annulée.")


def _verifier_etat_apres_validation(cible: Path, empreinte_comptes: str) -> None:
    """Contrôle final sur une connexion neuve, après validation de la transaction."""
    verification = backup_service.verifier_integrite(cible)
    if not verification.valide:
        raise ReinitialisationError(f"Intégrité de la base en échec après réinitialisation : {verification.message}")
    conn = _connexion(cible)
    try:
        for categorie in CATEGORIES_SUPPRIMEES:
            if _compter(conn, categorie.table) != 0:
                raise ReinitialisationError(f"Des données subsistent dans {categorie.table}.")
        if _empreinte_comptes(conn) != empreinte_comptes:
            raise ReinitialisationError("Les comptes utilisateurs diffèrent de leur état initial.")
    finally:
        conn.close()


def _restaurer_base(sauvegarde_base: Path, cible: Path) -> None:
    source = sqlite3.connect(sauvegarde_base)
    try:
        destination = sqlite3.connect(cible)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()


# ---------------------------------------------------------------------
# Opération principale
# ---------------------------------------------------------------------

def reinitialiser_donnees_metier(
    utilisateur_id: Optional[int],
    phrase_confirmation: Optional[str],
    confirmation: bool = False,
    db_path: DbPath = None,
    dossier_exports: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> RapportReinitialisation:
    """
    Supprime toutes les données métier et conserve les comptes.

    Args:
        utilisateur_id: identifiant de l'utilisateur qui lance
            l'opération ; son rôle est relu en base (ADMIN requis).
        phrase_confirmation: texte saisi manuellement, doit valoir
            « RÉINITIALISER » (ou « REINITIALISER »).
        confirmation: doit être explicitement True.

    Returns:
        RapportReinitialisation (réussite ou échec avec restauration).

    Raises:
        AutorisationRefuseeError: utilisateur non autorisé (tentative
            journalisée).
        ConfirmationInvalideError: confirmation absente ou incorrecte
            (aucune donnée touchée).
        ReinitialisationError: base non intègre ou sauvegarde
            préalable impossible (aucune donnée touchée).
    """
    cible = Path(db_path) if db_path is not None else DB_PATH
    dossier = Path(dossier_exports) if dossier_exports is not None else _dossier_exports_par_defaut()
    dossier_sauvegardes = Path(backup_dir) if backup_dir is not None else BACKUP_DIR

    # 1. Autorisation, vérifiée ici et non seulement dans l'interface.
    try:
        utilisateur = exiger_permission_utilisateur(utilisateur_id, permission_service.DONNEES_REINITIALISER, cible)
    except AutorisationRefuseeError as refus:
        from database.repositories import utilisateur_repository

        compte = utilisateur_repository.obtenir_par_id(utilisateur_id, db_path=cible) if utilisateur_id else None
        auteur = compte.username if compte is not None else f"inconnu (id={utilisateur_id})"
        _journaliser(cible, TypeActionAudit.REINITIALISATION_DONNEES_ECHEC, auteur, f"Refusée : {refus}")
        logger.warning("Réinitialisation des données refusée pour %s : %s", auteur, refus)
        raise
    auteur = utilisateur.username

    # 2. Confirmation explicite et phrase saisie.
    if confirmation is not True or not phrase_confirmation_valide(phrase_confirmation):
        raise ConfirmationInvalideError(
            f"Confirmation invalide : cochez la case de confirmation et saisissez exactement {PHRASE_CONFIRMATION}."
        )

    # 3. La base doit être saine avant toute action.
    etat_initial = backup_service.verifier_integrite(cible)
    if not etat_initial.valide:
        raise ReinitialisationError(
            f"Réinitialisation annulée : la base de données présente un problème ({etat_initial.message}). "
            "Aucune donnée n'a été modifiée."
        )

    # 4. Sauvegarde complète préalable (base + fichiers générés).
    try:
        archive, sauvegarde_base = _creer_sauvegarde_prealable(cible, dossier, dossier_sauvegardes)
    except (backup_service.BackupServiceError, OSError, zipfile.BadZipFile) as erreur:
        message = f"Réinitialisation annulée : la sauvegarde préalable a échoué ({erreur}). Aucune donnée n'a été modifiée."
        _journaliser(cible, TypeActionAudit.REINITIALISATION_DONNEES_ECHEC, auteur, message)
        logger.error(message)
        raise ReinitialisationError(message) from erreur

    logger.warning("Réinitialisation des données lancée par %s — sauvegarde : %s", auteur, archive)

    # 5. Mise à l'écart réversible des fichiers générés.
    nombre_fichiers, _ = _inventaire_fichiers(dossier)
    try:
        dossier_attente = _mettre_fichiers_a_l_ecart(dossier)
    except OSError as erreur:
        message = f"Réinitialisation annulée : fichiers générés inaccessibles ({erreur}). Aucune donnée n'a été modifiée."
        _journaliser(cible, TypeActionAudit.REINITIALISATION_DONNEES_ECHEC, auteur, message)
        return RapportReinitialisation(False, message, archive, sauvegarde_base)

    # 6. Suppression transactionnelle.
    conn = _connexion(cible)
    elements: Dict[str, int] = {}
    comptes = 0
    try:
        empreinte = _empreinte_comptes(conn)
        declencheurs_attendus = _noms_declencheurs(conn)
        comptes = _compter(conn, "utilisateurs")
        existantes = set(_tables_existantes(conn))

        conn.execute("BEGIN IMMEDIATE;")
        try:
            elements = {c.libelle: _compter(conn, c.table) for c in CATEGORIES_SUPPRIMEES if c.table in existantes}

            declencheurs = _declencheurs_de_suppression(conn)
            for nom, _sql in declencheurs:
                conn.execute(f'DROP TRIGGER "{nom}";')
            for categorie in CATEGORIES_SUPPRIMEES:
                if categorie.table in existantes:
                    conn.execute(f'DELETE FROM "{categorie.table}";')
            for _nom, sql in declencheurs:
                conn.execute(sql)

            _verifier_etat_avant_validation(conn, empreinte, declencheurs_attendus)

            details = (
                f"Réinitialisation des données métier réussie. Sauvegarde préalable : {archive.name}. "
                f"Éléments supprimés — {_resume_volumes(elements, nombre_fichiers)}. "
                f"Comptes utilisateurs conservés : {comptes}."
            )
            _journaliser(cible, TypeActionAudit.REINITIALISATION_DONNEES, auteur, details, conn=conn)
            conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
    except Exception as erreur:  # noqa: BLE001 — tout échec doit laisser les données intactes
        conn.close()
        _remettre_fichiers_en_place(dossier_attente, dossier)
        message = (
            f"La réinitialisation a échoué et a été entièrement annulée : {erreur}. "
            f"Toutes les données sont conservées. Sauvegarde préalable disponible : {archive.name}."
        )
        _journaliser(cible, TypeActionAudit.REINITIALISATION_DONNEES_ECHEC, auteur, message)
        logger.error(message)
        return RapportReinitialisation(False, message, archive, sauvegarde_base, comptes_conserves=comptes)
    else:
        conn.close()

    # 7. Vérification finale ; restauration automatique si nécessaire.
    try:
        _verifier_etat_apres_validation(cible, empreinte)
    except Exception as erreur:  # noqa: BLE001
        restauree = True
        try:
            _restaurer_base(sauvegarde_base, cible)
        except sqlite3.Error as erreur_restauration:
            restauree = False
            logger.critical("Restauration automatique impossible : %s", erreur_restauration)
        _remettre_fichiers_en_place(dossier_attente, dossier)
        if restauree:
            message = (
                f"La vérification finale a échoué ({erreur}). La sauvegarde {sauvegarde_base.name} a été "
                "restaurée automatiquement : les données sont revenues à leur état antérieur."
            )
        else:
            message = (
                f"La vérification finale a échoué ({erreur}) et la restauration automatique n'a pas abouti. "
                f"Restaurez manuellement la sauvegarde {sauvegarde_base.name} depuis l'onglet Restauration."
            )
        _journaliser(cible, TypeActionAudit.REINITIALISATION_DONNEES_ECHEC, auteur, message)
        logger.error(message)
        return RapportReinitialisation(
            False, message, archive, sauvegarde_base, comptes_conserves=comptes, restauration_effectuee=restauree
        )

    # 8. Validation définitive : suppression des fichiers mis à l'écart.
    if dossier_attente is not None:
        shutil.rmtree(dossier_attente, ignore_errors=True)
        if dossier_attente.exists():
            logger.warning("Dossier temporaire non supprimé, à effacer manuellement : %s", dossier_attente)
    _recreer_dossiers_exports(dossier)

    logger.warning("Réinitialisation des données terminée par %s : %s", auteur, _resume_volumes(elements, nombre_fichiers))
    return RapportReinitialisation(
        reussie=True,
        message="Réinitialisation terminée. Toutes les données métier ont été supprimées ; les comptes sont conservés.",
        sauvegarde_archive=archive,
        sauvegarde_base=sauvegarde_base,
        elements_supprimes=elements,
        fichiers_supprimes=nombre_fichiers,
        comptes_conserves=comptes,
    )
