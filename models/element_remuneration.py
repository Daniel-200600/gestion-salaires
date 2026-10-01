"""Modèle de données : ElementRemuneration. montant est en FCFA entiers (int)."""

from dataclasses import dataclass
from typing import Optional

from models.enums import TypeElementRemuneration


@dataclass
class ElementRemuneration:
    enseignant_id: int
    periode_id: int
    type_element: TypeElementRemuneration
    montant: int = 0  # FCFA entiers

    id: Optional[int] = None

    @staticmethod
    def from_row(row) -> "ElementRemuneration":
        return ElementRemuneration(
            id=row["id"],
            enseignant_id=row["enseignant_id"],
            periode_id=row["periode_id"],
            type_element=TypeElementRemuneration(row["type_element"]),
            montant=row["montant"],
        )
