"""
Modèle de données : Enseignant.

Note monétaire : taux_horaire est un montant en FCFA entiers (int),
jamais un float. Les calculs de paie utiliseront Decimal côté service ;
la base et les modèles ne manipulent que des entiers pour éviter toute
imprécision flottante sur des données de salaire.
"""

from dataclasses import dataclass
from typing import Optional

from models.enums import Sexe, StatutEnseignant


@dataclass
class Enseignant:
    nom: str
    prenom: str
    sexe: Sexe
    statut: StatutEnseignant
    taux_horaire: int  # FCFA entiers

    id: Optional[int] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    actif: bool = True
    date_creation: Optional[str] = None
    date_modification: Optional[str] = None

    @staticmethod
    def from_row(row) -> "Enseignant":
        """Construit un Enseignant à partir d'une ligne sqlite3.Row."""
        return Enseignant(
            id=row["id"],
            nom=row["nom"],
            prenom=row["prenom"],
            sexe=Sexe(row["sexe"]),
            statut=StatutEnseignant(row["statut"]),
            taux_horaire=row["taux_horaire"],
            email=row["email"],
            telephone=row["telephone"],
            adresse=row["adresse"],
            actif=bool(row["actif"]),
            date_creation=row["date_creation"],
            date_modification=row["date_modification"],
        )
