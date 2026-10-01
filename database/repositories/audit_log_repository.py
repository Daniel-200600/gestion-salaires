"""
Accès aux données de la table `audit_log`.

Ce repository ne contient aucune logique métier : il se contente
d'insérer et de lire des entrées d'audit déjà construites par les
services appelants (cf. services/enseignant_service.py pour la
suppression définitive d'enseignant).
"""

from pathlib import Path
from typing import List, Optional, Union
import sqlite3

from database.connection import get_connection
from models.audit_log import AuditLog

DbPath = Optional[Union[str, Path]]


def enregistrer(
    entree: AuditLog, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> None:
    """
    Insère une entrée d'audit.

    Si `conn` est fourni, l'opération est exécutée sur cette connexion
    SANS commit (utilisé pour inclure l'entrée d'audit dans la même
    transaction qu'une opération administrative, ex : suppression
    définitive d'un enseignant). Sinon, connexion dédiée et commit
    immédiat.
    """
    requete = """
        INSERT INTO audit_log (type_action, entite, entite_id, utilisateur, details)
        VALUES (?, ?, ?, ?, ?)
    """
    parametres = (
        entree.type_action.value,
        entree.entite,
        entree.entite_id,
        entree.utilisateur,
        entree.details,
    )
    if conn is not None:
        conn.execute(requete, parametres)
        return
    with get_connection(db_path) as connexion:
        connexion.execute(requete, parametres)
        connexion.commit()


def lister_par_entite(entite: str, entite_id: int, db_path: DbPath = None) -> List[AuditLog]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE entite = ? AND entite_id = ? ORDER BY date_action",
            (entite, entite_id),
        ).fetchall()
        return [AuditLog.from_row(row) for row in rows]


def compter_tout(db_path: DbPath = None) -> int:
    """Nombre total d'entrées d'audit, toutes entités confondues (utilisé par le diagnostic système)."""
    with get_connection(db_path) as conn:
        return conn.execute("SELECT COUNT(*) AS total FROM audit_log").fetchone()["total"]
