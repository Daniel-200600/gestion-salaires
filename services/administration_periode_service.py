"""
Actions d'administrateur sur une période de paie : la rouvrir (invalider
sa validation ou sa clôture) ou la supprimer avec toutes ses données.

Les règles de protection de la base (triggers) interdisent ces opérations
en temps normal : une période validée ou clôturée est figée, ses bulletins
sont immuables. Pour ces deux actions, et pour elles seules, les règles
concernées sont levées puis recréées à l'identique DANS LA MÊME
TRANSACTION (même principe que la réinitialisation des données) : en cas
d'échec, rien n'est modifié et les protections restent en place.

Chaque action exige l'administrateur, la saisie exacte du libellé de la
période, crée d'abord une sauvegarde de la base et est inscrite au
journal d'audit.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from database.connection import get_connection
from database.repositories import audit_log_repository, periode_repository
from models.audit_log import AuditLog
from models.enums import StatutPeriode, TypeActionAudit
from services import backup_service, permission_service
from services.autorisation_service import exiger_permission_utilisateur

DbPath = Optional[Union[str, Path]]

PREFIXE_SAUVEGARDE_REOUVERTURE = "avant_reouverture_"
PREFIXE_SAUVEGARDE_SUPPRESSION = "avant_suppression_periode_"


class AdministrationPeriodeError(ValueError):
    """Action refusée (confirmation incorrecte, période introuvable, statut)."""


@dataclass
class RapportActionPeriode:
    libelle: str
    sauvegarde: Path
    nb_saisies_heures: int = 0
    nb_elements_remuneration: int = 0
    nb_retenues: int = 0
    nb_instantanes_bulletins: int = 0


def _periode_confirmee(periode_id: int, confirmation: str, db_path: DbPath):
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise AdministrationPeriodeError(f"Aucune période avec l'id {periode_id}.")
    if " ".join((confirmation or "").split()).lower() != periode.libelle.lower():
        raise AdministrationPeriodeError(
            f"Confirmation incorrecte : saisissez exactement le nom de la période (« {periode.libelle} »)."
        )
    return periode


def _sauvegarde(db_path: DbPath, prefixe: str) -> Path:
    """
    Sauvegarde de la base réellement utilisée. Celle de l'application va dans le
    dossier habituel des sauvegardes ; toute autre base (test, base déplacée) est
    sauvegardée à côté d'elle, jamais dans le dossier d'une autre base.
    """
    from config import settings
    from database import connection

    source = Path(db_path) if db_path is not None else Path(connection.DB_PATH)
    dossier = None if source.resolve() == Path(settings.DB_PATH).resolve() else source.parent / "backups"
    return backup_service.creer_sauvegarde(db_path=source, backup_dir=dossier, prefixe=prefixe)


def _declencheurs(conn: sqlite3.Connection, noms: Tuple[str, ...]) -> List[Tuple[str, str]]:
    marqueurs = ",".join("?" for _ in noms)
    return [(ligne[0], ligne[1]) for ligne in conn.execute(
        f"SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND name IN ({marqueurs})", noms
    ).fetchall()]


def _compter(conn, table: str, periode_id: int) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE periode_id = ?", (periode_id,)).fetchone()[0]


def _executer_sans_declencheurs(db_path: DbPath, noms: Tuple[str, ...], operations) -> None:
    """Lève les règles nommées, exécute `operations(conn)`, recrée les règles ; tout ou rien."""
    with get_connection(db_path) as conn:
        conn.isolation_level = None  # transaction explicite (le DDL des triggers y est inclus)
        conn.execute("BEGIN IMMEDIATE;")
        try:
            declencheurs = _declencheurs(conn, noms)
            for nom, _sql in declencheurs:
                conn.execute(f'DROP TRIGGER "{nom}";')
            operations(conn)
            for _nom, sql in declencheurs:
                conn.execute(sql)
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def _journaliser(type_action, periode, utilisateur, details, db_path) -> None:
    audit_log_repository.enregistrer(
        AuditLog(type_action=type_action, entite="periode_paie", entite_id=periode.id, utilisateur=utilisateur,
                 details=f"{periode.libelle} — {details}"),
        db_path=db_path,
    )


def rouvrir_periode(
    acteur_id: Optional[int], periode_id: int, confirmation: str, motif: str = "", db_path: DbPath = None
) -> RapportActionPeriode:
    """
    Invalide une période VALIDÉE ou CLÔTURÉE : elle redevient OUVERTE, ses
    données de paie sont de nouveau modifiables. Les instantanés de
    bulletins de la période sont retirés : une nouvelle validation en
    produira de nouveaux, à partir des données corrigées. Les fichiers de
    bulletins déjà produits restent dans la gestion des documents.
    """
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.PERIODE_SUPPRIMER, db_path)
    periode = _periode_confirmee(periode_id, confirmation, db_path)
    if periode.statut not in (StatutPeriode.VALIDEE, StatutPeriode.CLOTUREE):
        raise AdministrationPeriodeError(
            f"{periode.libelle} est {periode.statut.value} : seule une période validée ou clôturée peut être rouverte."
        )
    sauvegarde = _sauvegarde(db_path, PREFIXE_SAUVEGARDE_REOUVERTURE)
    rapport = RapportActionPeriode(libelle=periode.libelle, sauvegarde=sauvegarde)

    def operations(conn):
        rapport.nb_instantanes_bulletins = _compter(conn, "bulletins_paie", periode_id)
        conn.execute("DELETE FROM bulletins_paie WHERE periode_id = ?", (periode_id,))
        conn.execute("UPDATE periodes_paie SET statut = 'ouverte', date_cloture = NULL WHERE id = ?", (periode_id,))

    _executer_sans_declencheurs(db_path, (
        "trg_periodes_paie_cloturee_figee", "trg_periodes_paie_transition_invalide",
        "trg_bulletins_paie_immuable_delete",
    ), operations)
    _journaliser(
        TypeActionAudit.MODIFICATION, periode, acteur.username,
        f"période rouverte (était {periode.statut.value}) ; {rapport.nb_instantanes_bulletins} instantané(s) de "
        f"bulletin retiré(s) ; sauvegarde préalable : {sauvegarde.name}"
        + (f" ; motif : {' '.join(motif.split())}" if motif and motif.strip() else ""),
        db_path,
    )
    return rapport


def supprimer_periode(
    acteur_id: Optional[int], periode_id: int, confirmation: str, db_path: DbPath = None
) -> RapportActionPeriode:
    """
    Supprime une période, quel que soit son statut, avec ses heures, primes,
    retenues et instantanés de bulletins. Les fiches des enseignants ne sont
    pas touchées ; les documents déjà produits restent enregistrés (sans
    période). Une sauvegarde de la base est créée juste avant.
    """
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.PERIODE_SUPPRIMER, db_path)
    periode = _periode_confirmee(periode_id, confirmation, db_path)
    sauvegarde = _sauvegarde(db_path, PREFIXE_SAUVEGARDE_SUPPRESSION)
    rapport = RapportActionPeriode(libelle=periode.libelle, sauvegarde=sauvegarde)

    def operations(conn):
        rapport.nb_saisies_heures = _compter(conn, "saisies_heures", periode_id)
        rapport.nb_elements_remuneration = _compter(conn, "elements_remuneration", periode_id)
        rapport.nb_retenues = _compter(conn, "retenues", periode_id)
        rapport.nb_instantanes_bulletins = _compter(conn, "bulletins_paie", periode_id)
        for table in ("saisies_heures", "elements_remuneration", "retenues", "bulletins_paie"):
            conn.execute(f"DELETE FROM {table} WHERE periode_id = ?", (periode_id,))
        conn.execute("DELETE FROM periodes_paie WHERE id = ?", (periode_id,))

    _executer_sans_declencheurs(db_path, (
        "trg_periodes_paie_suppression_limitee", "trg_bulletins_paie_immuable_delete",
    ), operations)
    _journaliser(
        TypeActionAudit.SUPPRESSION_DEFINITIVE, periode, acteur.username,
        f"période supprimée (statut {periode.statut.value}) avec {rapport.nb_saisies_heures} saisie(s) d'heures, "
        f"{rapport.nb_elements_remuneration} élément(s) de rémunération, {rapport.nb_retenues} retenue(s), "
        f"{rapport.nb_instantanes_bulletins} instantané(s) de bulletin ; sauvegarde préalable : {sauvegarde.name}",
        db_path,
    )
    return rapport
