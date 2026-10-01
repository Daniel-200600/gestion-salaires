"""Modèle de données : PeriodePaie."""

from dataclasses import dataclass
from typing import Optional

from models.enums import StatutPeriode


@dataclass
class PeriodePaie:
    mois: int
    annee: int
    libelle: str

    id: Optional[int] = None
    statut: StatutPeriode = StatutPeriode.BROUILLON
    date_creation: Optional[str] = None
    date_cloture: Optional[str] = None

    @staticmethod
    def from_row(row) -> "PeriodePaie":
        return PeriodePaie(
            id=row["id"],
            mois=row["mois"],
            annee=row["annee"],
            libelle=row["libelle"],
            statut=StatutPeriode(row["statut"]),
            date_creation=row["date_creation"],
            date_cloture=row["date_cloture"],
        )
