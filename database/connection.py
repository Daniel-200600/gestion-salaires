"""
Gestion centralisée des connexions SQLite.

Toute la base de code doit obtenir ses connexions via `get_connection()`
plutôt que d'appeler `sqlite3.connect()` directement, afin de garantir :
- l'activation systématique des clés étrangères (PRAGMA foreign_keys),
- un accès aux lignes par nom de colonne (sqlite3.Row),
- une fermeture propre de la connexion (context manager).
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

from config.settings import DB_PATH, ensure_data_dirs


@contextmanager
def get_connection(db_path: Union[str, Path, None] = None) -> Iterator[sqlite3.Connection]:
    """
    Fournit une connexion SQLite prête à l'emploi sous forme de context
    manager. Les clés étrangères sont activées et les lignes sont
    accessibles par nom de colonne (row["colonne"]).

    Usage :
        with get_connection() as conn:
            conn.execute(...)
            conn.commit()
    """
    path = Path(db_path) if db_path is not None else DB_PATH
    ensure_data_dirs()

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()
