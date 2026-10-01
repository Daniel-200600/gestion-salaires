"""Modèle de données : Document (module 14 — registre documentaire)."""

from dataclasses import dataclass
from typing import Optional

from models.enums import TypeDocument


@dataclass
class Document:
    type_document: TypeDocument
    nom_fichier: str
    chemin: str

    id: Optional[int] = None
    enseignant_id: Optional[int] = None
    periode_id: Optional[int] = None
    date_creation: Optional[str] = None
    utilisateur: Optional[str] = None
    taille: Optional[int] = None
    hash_fichier: Optional[str] = None

    @staticmethod
    def from_row(row) -> "Document":
        return Document(
            id=row["id"],
            type_document=TypeDocument(row["type_document"]),
            nom_fichier=row["nom_fichier"],
            chemin=row["chemin"],
            enseignant_id=row["enseignant_id"],
            periode_id=row["periode_id"],
            date_creation=row["date_creation"],
            utilisateur=row["utilisateur"],
            taille=row["taille"],
            hash_fichier=row["hash_fichier"],
        )
