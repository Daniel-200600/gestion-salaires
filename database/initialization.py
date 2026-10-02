"""
Initialisation de la base de données.

Exécute database/schema.sql sur une connexion donnée pour créer
(ou vérifier l'existence de) toutes les tables, contraintes et index.
Idempotent : peut être appelé plusieurs fois sans erreur grâce aux
clauses `IF NOT EXISTS` du schéma.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Union

from config.settings import DB_PATH, SCHEMA_PATH, ensure_data_dirs
from database import migrations
from database.connection import get_connection


def init_database(
    db_path: Optional[Union[str, Path]] = None,
    schema_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Crée les tables de l'application si elles n'existent pas encore.

    Corrige également, de façon idempotente et sans perte de donnée,
    toute base créée par une version antérieure de l'application dont
    la contrainte CHECK de `audit_log` serait devenue obsolète (voir
    `database/migrations.py`) — appelé systématiquement AVANT
    l'exécution normale du schéma, pour une base neuve comme pour une
    base existante.

    Args:
        db_path: chemin du fichier SQLite cible (défaut: config.settings.DB_PATH)
        schema_path: chemin du fichier schema.sql (défaut: config.settings.SCHEMA_PATH)
    """
    ensure_data_dirs()
    schema_file = Path(schema_path) if schema_path is not None else SCHEMA_PATH

    if not schema_file.exists():
        raise FileNotFoundError(f"Fichier de schéma introuvable : {schema_file}")

    schema_sql = schema_file.read_text(encoding="utf-8")

    with get_connection(db_path if db_path is not None else DB_PATH) as conn:
        migrations.migrer_audit_log_si_necessaire(conn, schema_sql)
        migrations.ajouter_colonnes_manquantes(conn)
        migrations.rendre_fiches_enseignants_completables(conn, schema_sql)
        conn.executescript(schema_sql)
        conn.commit()


def get_table_names(db_path: Optional[Union[str, Path]] = None) -> list[str]:
    """Retourne la liste des tables utilisateur existantes (hors tables internes SQLite)."""
    with get_connection(db_path if db_path is not None else DB_PATH) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name;"
        ).fetchall()
        return [row["name"] for row in rows]


if __name__ == "__main__":
    init_database()
    print(f"Base initialisée : {DB_PATH}")
    print("Tables créées :", get_table_names())
