"""Modèle de données : SaisieHeures (heures effectuées pour une semaine donnée)."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SaisieHeures:
    enseignant_id: int
    periode_id: int
    numero_semaine: int  # doit être compris entre 1 et 5
    heures_effectuees: float

    id: Optional[int] = None

    @staticmethod
    def from_row(row) -> "SaisieHeures":
        return SaisieHeures(
            id=row["id"],
            enseignant_id=row["enseignant_id"],
            periode_id=row["periode_id"],
            numero_semaine=row["numero_semaine"],
            heures_effectuees=row["heures_effectuees"],
        )
