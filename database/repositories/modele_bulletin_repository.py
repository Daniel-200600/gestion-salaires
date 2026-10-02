"""
Accès aux données de la table `modeles_bulletin` (modèles de bulletin
importés). Aucune logique métier : voir services/modele_bulletin_service.py.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional, Union

from database.connection import get_connection

DbPath = Optional[Union[str, Path]]


def creer(nom: str, format_: str, nom_fichier: str, nom_fichier_origine: str, empreinte: str,
          correspondances: str, utilisateur: Optional[str], db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        curseur = conn.execute(
            """INSERT INTO modeles_bulletin
               (nom, format, nom_fichier, nom_fichier_origine, empreinte, correspondances, utilisateur)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nom, format_, nom_fichier, nom_fichier_origine, empreinte, correspondances, utilisateur),
        )
        conn.commit()
        return curseur.lastrowid


def obtenir(modele_id: int, db_path: DbPath = None) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT * FROM modeles_bulletin WHERE id = ?", (modele_id,)).fetchone()


def lister(db_path: DbPath = None) -> List[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT * FROM modeles_bulletin ORDER BY date_import DESC, id DESC").fetchall()


def supprimer(modele_id: int, db_path: DbPath = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM modeles_bulletin WHERE id = ?", (modele_id,))
        conn.commit()
