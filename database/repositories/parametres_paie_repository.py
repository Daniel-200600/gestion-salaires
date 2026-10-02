"""
Accès aux données de la table `parametres_paie` (clé / valeur).

Aucune logique métier : la validation des valeurs (taux de taxe,
modèle de bulletin actif) est faite par services/parametres_paie_service.py
et services/modele_bulletin_service.py.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Union

from database.connection import get_connection

DbPath = Optional[Union[str, Path]]


def lire(cle: str, db_path: DbPath = None) -> Optional[str]:
    """Retourne la valeur enregistrée pour `cle`, ou None si elle n'a jamais été définie."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT valeur FROM parametres_paie WHERE cle = ?", (cle,)).fetchone()
        return row["valeur"] if row is not None else None


def ecrire(
    cle: str, valeur: str, utilisateur: Optional[str] = None, db_path: DbPath = None,
    conn: "Optional[sqlite3.Connection]" = None,
) -> None:
    """Crée ou remplace la valeur de `cle`. Si `conn` est fourni, aucun commit (transaction de l'appelant)."""
    requete = """
        INSERT INTO parametres_paie (cle, valeur, utilisateur, date_modification)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(cle) DO UPDATE SET
            valeur = excluded.valeur,
            utilisateur = excluded.utilisateur,
            date_modification = excluded.date_modification
    """
    if conn is not None:
        conn.execute(requete, (cle, valeur, utilisateur))
        return
    with get_connection(db_path) as connexion:
        connexion.execute(requete, (cle, valeur, utilisateur))
        connexion.commit()
