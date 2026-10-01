"""
Accès aux données de la table `documents` (registre documentaire,
module 14). Ce module ne contient AUCUNE logique métier : ni calcul de
hash (cf. services/document_integrity_service.py), ni construction de
chemin (cf. les modules d'export existants), ni règle de permission.
Il se contente d'exécuter des requêtes SQL et de convertir les
résultats en objets Document.
"""

from pathlib import Path
from typing import List, Optional, Union

from database.connection import get_connection
from models.document import Document
from models.enums import TypeDocument

DbPath = Optional[Union[str, Path]]


def enregistrer(document: Document, db_path: DbPath = None) -> int:
    """Insère une nouvelle entrée dans le registre et retourne son id généré."""
    with get_connection(db_path) as conn:
        curseur = conn.execute(
            """
            INSERT INTO documents (
                type_document, nom_fichier, chemin, enseignant_id, periode_id, utilisateur, taille, hash_fichier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.type_document.value, document.nom_fichier, document.chemin,
                document.enseignant_id, document.periode_id, document.utilisateur,
                document.taille, document.hash_fichier,
            ),
        )
        conn.commit()
        return curseur.lastrowid


def obtenir_par_id(document_id: int, db_path: DbPath = None) -> Optional[Document]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return Document.from_row(row) if row else None


def rechercher(
    periode_id: Optional[int] = None,
    enseignant_id: Optional[int] = None,
    type_document: Optional[TypeDocument] = None,
    terme_recherche: Optional[str] = None,
    db_path: DbPath = None,
) -> List[Document]:
    """
    Recherche filtrée (section 16/19/20) : les filtres fournis se
    combinent (ET logique). `terme_recherche` est appliqué sur
    `nom_fichier`, insensible à la casse.
    """
    requete = "SELECT * FROM documents WHERE 1 = 1"
    parametres: List = []

    if periode_id is not None:
        requete += " AND periode_id = ?"
        parametres.append(periode_id)
    if enseignant_id is not None:
        requete += " AND enseignant_id = ?"
        parametres.append(enseignant_id)
    if type_document is not None:
        requete += " AND type_document = ?"
        parametres.append(type_document.value)
    if terme_recherche:
        requete += " AND LOWER(nom_fichier) LIKE LOWER(?)"
        parametres.append(f"%{terme_recherche}%")

    requete += " ORDER BY date_creation DESC"

    with get_connection(db_path) as conn:
        rows = conn.execute(requete, parametres).fetchall()
        return [Document.from_row(row) for row in rows]


def lister_par_periode(periode_id: int, db_path: DbPath = None) -> List[Document]:
    return rechercher(periode_id=periode_id, db_path=db_path)


def compter_tout(db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT COUNT(*) AS total FROM documents").fetchone()["total"]


def taille_totale(db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        resultat = conn.execute("SELECT COALESCE(SUM(taille), 0) AS total FROM documents").fetchone()["total"]
        return resultat or 0
