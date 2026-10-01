"""
Accès aux données des tables `imports` et `import_erreurs` (module 15).
Ce module ne contient AUCUNE logique métier : ni parsing de fichier,
ni validation, ni détection de doublon (cf. services/import_service.py).
"""

from pathlib import Path
from typing import List, Optional, Union

from database.connection import get_connection
from models.enums import TypeImport
from models.import_journal import AnomalieImport, ImportJournal

DbPath = Optional[Union[str, Path]]


def enregistrer_import(journal: ImportJournal, db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        curseur = conn.execute(
            """
            INSERT INTO imports (
                utilisateur, nom_fichier, type_import, statut, periode_id,
                nb_lignes, nb_creations, nb_mises_a_jour, nb_ignorees, nb_rejetees,
                nb_erreurs, nb_avertissements
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                journal.utilisateur, journal.nom_fichier, journal.type_import.value, journal.statut.value,
                journal.periode_id, journal.nb_lignes, journal.nb_creations, journal.nb_mises_a_jour,
                journal.nb_ignorees, journal.nb_rejetees, journal.nb_erreurs, journal.nb_avertissements,
            ),
        )
        conn.commit()
        return curseur.lastrowid


def enregistrer_anomalies(import_id: int, anomalies: List[AnomalieImport], db_path: DbPath = None) -> None:
    if not anomalies:
        return
    with get_connection(db_path) as conn:
        conn.executemany(
            "INSERT INTO import_erreurs (import_id, ligne, champ, valeur, niveau, message) VALUES (?, ?, ?, ?, ?, ?)",
            [(import_id, a.ligne, a.champ, a.valeur, a.niveau.value, a.message) for a in anomalies],
        )
        conn.commit()


def obtenir_import(import_id: int, db_path: DbPath = None) -> Optional[ImportJournal]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
        return ImportJournal.from_row(row) if row else None


def lister_anomalies(import_id: int, db_path: DbPath = None) -> List[AnomalieImport]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM import_erreurs WHERE import_id = ? ORDER BY ligne", (import_id,)
        ).fetchall()
        return [AnomalieImport.from_row(row) for row in rows]


def lister_imports(type_import: Optional[TypeImport] = None, db_path: DbPath = None) -> List[ImportJournal]:
    requete = "SELECT * FROM imports"
    parametres: List = []
    if type_import is not None:
        requete += " WHERE type_import = ?"
        parametres.append(type_import.value)
    requete += " ORDER BY date_import DESC"

    with get_connection(db_path) as conn:
        rows = conn.execute(requete, parametres).fetchall()
        return [ImportJournal.from_row(row) for row in rows]


def dernier_import(db_path: DbPath = None) -> Optional[ImportJournal]:
    imports = lister_imports(db_path=db_path)
    return imports[0] if imports else None
