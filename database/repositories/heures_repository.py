"""
Accès aux données de la table `saisies_heures`.

Utilise un upsert SQL (INSERT ... ON CONFLICT ... DO UPDATE) sur la
contrainte UNIQUE (enseignant_id, periode_id, numero_semaine) : aucune
requête SELECT préalable n'est nécessaire pour savoir si la ligne
existe déjà, et aucun doublon ne peut être créé par une resaisie.

Ce module ne fait AUCUNE validation ni contrôle de statut de période :
ces règles vivent dans services/heures_service.py. Les triggers SQL du
schéma (cf. database/schema.sql) constituent un filet de sécurité
supplémentaire — une tentative d'upsert sur une période qui n'est pas
OUVERTE est de toute façon rejetée par la base.
"""

from pathlib import Path
from typing import List, Optional, Union
import sqlite3

from database.connection import get_connection
from models.saisie_heures import SaisieHeures

DbPath = Optional[Union[str, Path]]


def upsert(saisie: SaisieHeures, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None) -> None:
    """
    Insère ou met à jour les heures d'une semaine donnée (aucun doublon possible).

    Si `conn` est fourni, l'opération est exécutée sur cette connexion
    SANS commit : le commit (ou rollback) est alors à la charge de
    l'appelant — utilisé par l'enregistrement groupé transactionnel de
    services/donnees_paie_service.py, pour que plusieurs upserts sur
    plusieurs tables partagent une seule et même transaction. Sinon,
    comportement inchangé (connexion dédiée, commit immédiat).
    """
    requete = """
        INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(enseignant_id, periode_id, numero_semaine)
        DO UPDATE SET heures_effectuees = excluded.heures_effectuees
    """
    parametres = (saisie.enseignant_id, saisie.periode_id, saisie.numero_semaine, saisie.heures_effectuees)

    if conn is not None:
        conn.execute(requete, parametres)
        return

    with get_connection(db_path) as connexion:
        connexion.execute(requete, parametres)
        connexion.commit()


def lister_par_enseignant_periode(
    enseignant_id: int, periode_id: int, db_path: DbPath = None
) -> List[SaisieHeures]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM saisies_heures WHERE enseignant_id = ? AND periode_id = ? ORDER BY numero_semaine",
            (enseignant_id, periode_id),
        ).fetchall()
        return [SaisieHeures.from_row(row) for row in rows]


def lister_par_periode(periode_id: int, db_path: DbPath = None) -> List[SaisieHeures]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM saisies_heures WHERE periode_id = ? ORDER BY enseignant_id, numero_semaine",
            (periode_id,),
        ).fetchall()
        return [SaisieHeures.from_row(row) for row in rows]


def compter_par_enseignant(
    enseignant_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """Nombre de saisies (semaines) enregistrées pour un enseignant, toutes périodes confondues."""
    requete = "SELECT COUNT(*) AS total FROM saisies_heures WHERE enseignant_id = ?"
    if conn is not None:
        return conn.execute(requete, (enseignant_id,)).fetchone()["total"]
    with get_connection(db_path) as connexion:
        return connexion.execute(requete, (enseignant_id,)).fetchone()["total"]


def supprimer_par_enseignant(
    enseignant_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """
    Supprime TOUTES les saisies d'heures d'un enseignant (irréversible),
    toutes périodes confondues. Utilisé uniquement par
    services/enseignant_service.supprimer_enseignant_definitivement.

    Si `conn` est fourni, exécuté sur cette connexion sans commit
    (transaction gérée par l'appelant). Retourne le nombre de lignes
    supprimées.
    """
    requete = "DELETE FROM saisies_heures WHERE enseignant_id = ?"
    if conn is not None:
        return conn.execute(requete, (enseignant_id,)).rowcount
    with get_connection(db_path) as connexion:
        curseur = connexion.execute(requete, (enseignant_id,))
        connexion.commit()
        return curseur.rowcount


def compter_par_periode(
    periode_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """Nombre de saisies (semaines) enregistrées pour une période, tous enseignants confondus."""
    requete = "SELECT COUNT(*) AS total FROM saisies_heures WHERE periode_id = ?"
    if conn is not None:
        return conn.execute(requete, (periode_id,)).fetchone()["total"]
    with get_connection(db_path) as connexion:
        return connexion.execute(requete, (periode_id,)).fetchone()["total"]


def supprimer_par_periode(
    periode_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """
    Supprime TOUTES les saisies d'heures d'une période (irréversible),
    tous enseignants confondus. Utilisé uniquement par
    services/periode_service.supprimer_periode_definitivement.
    """
    requete = "DELETE FROM saisies_heures WHERE periode_id = ?"
    if conn is not None:
        return conn.execute(requete, (periode_id,)).rowcount
    with get_connection(db_path) as connexion:
        curseur = connexion.execute(requete, (periode_id,))
        connexion.commit()
        return curseur.rowcount
