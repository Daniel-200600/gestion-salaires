"""Modèle de données : Retenue. montant est en FCFA entiers (int)."""

from dataclasses import dataclass
from typing import Optional

from models.enums import TypeRetenue


@dataclass
class Retenue:
    enseignant_id: int
    periode_id: int
    type_retenue: TypeRetenue
    montant: int = 0  # FCFA entiers

    id: Optional[int] = None

    @staticmethod
    def from_row(row) -> "Retenue":
        return Retenue(
            id=row["id"],
            enseignant_id=row["enseignant_id"],
            periode_id=row["periode_id"],
            type_retenue=TypeRetenue(row["type_retenue"]),
            montant=row["montant"],
        )
