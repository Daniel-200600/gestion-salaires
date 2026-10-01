"""
Accès aux données de la table `elements_remuneration`.

Upsert SQL sur la contrainte UNIQUE (enseignant_id, periode_id,
type_element) : aucun doublon possible par type d'élément (prime
AP/PP, surveillance/secrétariat, indemnité suggestion/admin).

Aucune validation ni contrôle de statut ici (cf.
services/remuneration_service.py) ; les triggers SQL du schéma
constituent un filet de sécurité supplémentaire.
"""

from pathlib import Path
from typing import List, Optional, Union
import sqlite3

from database.connection import get_connection
from models.element_remuneration import ElementRemuneration

DbPath = Optional[Union[str, Path]]


def upsert(
    element: ElementRemuneration, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> None:
    """
    Si `conn` est fourni, l'opération est exécutée sur cette connexion
    SANS commit (utilisé par l'enregistrement groupé transactionnel de
    services/donnees_paie_service.py). Sinon, comportement inchangé.
    """
    requete = """
        INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(enseignant_id, periode_id, type_element)
        DO UPDATE SET montant = excluded.montant
    """
    parametres = (element.enseignant_id, element.periode_id, element.type_element.value, element.montant)

    if conn is not None:
        conn.execute(requete, parametres)
        return

    with get_connection(db_path) as connexion:
        connexion.execute(requete, parametres)
        connexion.commit()


def lister_par_enseignant_periode(
    enseignant_id: int, periode_id: int, db_path: DbPath = None
) -> List[ElementRemuneration]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM elements_remuneration WHERE enseignant_id = ? AND periode_id = ?",
            (enseignant_id, periode_id),
        ).fetchall()
        return [ElementRemuneration.from_row(row) for row in rows]


def lister_par_periode(periode_id: int, db_path: DbPath = None) -> List[ElementRemuneration]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM elements_remuneration WHERE periode_id = ?",
            (periode_id,),
        ).fetchall()
        return [ElementRemuneration.from_row(row) for row in rows]


def compter_par_enseignant(
    enseignant_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """Nombre d'éléments de rémunération enregistrés pour un enseignant, toutes périodes confondues."""
    requete = "SELECT COUNT(*) AS total FROM elements_remuneration WHERE enseignant_id = ?"
    if conn is not None:
        return conn.execute(requete, (enseignant_id,)).fetchone()["total"]
    with get_connection(db_path) as connexion:
        return connexion.execute(requete, (enseignant_id,)).fetchone()["total"]


def supprimer_par_enseignant(
    enseignant_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """
    Supprime TOUS les éléments de rémunération d'un enseignant
    (irréversible), toutes périodes confondues. Utilisé uniquement par
    services/enseignant_service.supprimer_enseignant_definitivement.
    """
    requete = "DELETE FROM elements_remuneration WHERE enseignant_id = ?"
    if conn is not None:
        return conn.execute(requete, (enseignant_id,)).rowcount
    with get_connection(db_path) as connexion:
        curseur = connexion.execute(requete, (enseignant_id,))
        connexion.commit()
        return curseur.rowcount


def compter_par_periode(
    periode_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """Nombre d'éléments de rémunération enregistrés pour une période, tous enseignants confondus."""
    requete = "SELECT COUNT(*) AS total FROM elements_remuneration WHERE periode_id = ?"
    if conn is not None:
        return conn.execute(requete, (periode_id,)).fetchone()["total"]
    with get_connection(db_path) as connexion:
        return connexion.execute(requete, (periode_id,)).fetchone()["total"]


def supprimer_par_periode(
    periode_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """
    Supprime TOUS les éléments de rémunération d'une période
    (irréversible), tous enseignants confondus. Utilisé uniquement par
    services/periode_service.supprimer_periode_definitivement.
    """
    requete = "DELETE FROM elements_remuneration WHERE periode_id = ?"
    if conn is not None:
        return conn.execute(requete, (periode_id,)).rowcount
    with get_connection(db_path) as connexion:
        curseur = connexion.execute(requete, (periode_id,))
        connexion.commit()
        return curseur.rowcount
