"""
Modèle de données : Enseignant.

Note monétaire : taux_horaire est un montant en FCFA entiers (int),
jamais un float. Les calculs de paie utiliseront Decimal côté service ;
la base et les modèles ne manipulent que des entiers pour éviter toute
imprécision flottante sur des données de salaire.

Fiches incomplètes : un enseignant importé depuis une liste existante
peut n'avoir ni sexe, ni statut, ni taux horaire. Sa fiche est complétée
plus tard (page Enseignants). Tant qu'elle est incomplète (`est_complet`),
il n'entre dans aucune saisie ni aucun calcul de paie.
"""

from dataclasses import dataclass
from typing import List, Optional

from models.enums import Sexe, StatutEnseignant


@dataclass
class Enseignant:
    nom: str
    prenom: str = ""
    sexe: Optional[Sexe] = None
    statut: Optional[StatutEnseignant] = None
    taux_horaire: Optional[int] = None  # FCFA entiers
    # Salaire mensuel fixe (FCFA) d'un permanent : remplace heures × taux horaire.
    salaire_fixe: Optional[int] = None

    id: Optional[int] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    actif: bool = True
    date_creation: Optional[str] = None
    date_modification: Optional[str] = None

    @property
    def champs_manquants(self) -> List[str]:
        """Informations à compléter, en toutes lettres (ex. ["sexe", "taux horaire"])."""
        manquants = []
        if self.sexe is None:
            manquants.append("sexe")
        if self.statut is None:
            manquants.append("statut")
        if self.taux_horaire is None and not self.remuneration_fixe:
            manquants.append("taux horaire ou salaire fixe" if self.statut == StatutEnseignant.PERMANENT
                             else "taux horaire")
        return manquants

    @property
    def remuneration_fixe(self) -> bool:
        """Permanent payé au salaire mensuel fixe (et non à l'heure)."""
        return self.statut == StatutEnseignant.PERMANENT and self.salaire_fixe is not None

    @property
    def est_complet(self) -> bool:
        return not self.champs_manquants

    @staticmethod
    def from_row(row) -> "Enseignant":
        """Construit un Enseignant à partir d'une ligne sqlite3.Row."""
        return Enseignant(
            id=row["id"],
            nom=row["nom"],
            prenom=row["prenom"] or "",
            sexe=Sexe(row["sexe"]) if row["sexe"] else None,
            statut=StatutEnseignant(row["statut"]) if row["statut"] else None,
            taux_horaire=row["taux_horaire"],
            salaire_fixe=row["salaire_fixe"] if "salaire_fixe" in row.keys() else None,
            email=row["email"],
            telephone=row["telephone"],
            adresse=row["adresse"],
            actif=bool(row["actif"]),
            date_creation=row["date_creation"],
            date_modification=row["date_modification"],
        )
