"""Modèle de données : PeriodePaie."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from config.settings import TAUX_TAXE
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
    # Taux de taxe propre à la période (fraction : Decimal("0.055") = 5,5 %).
    # Figé dès que la période est validée (cf. trigger trg_periodes_paie_taux_fige).
    taux_taxe: Decimal = TAUX_TAXE

    @staticmethod
    def from_row(row) -> "PeriodePaie":
        cles = row.keys()
        return PeriodePaie(
            id=row["id"],
            mois=row["mois"],
            annee=row["annee"],
            libelle=row["libelle"],
            statut=StatutPeriode(row["statut"]),
            date_creation=row["date_creation"],
            date_cloture=row["date_cloture"],
            taux_taxe=Decimal(str(row["taux_taxe"])) if "taux_taxe" in cles else TAUX_TAXE,
        )
