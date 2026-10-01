"""
Modèle de données : BulletinPaie.

Représente un bulletin historisé et IMMUABLE : toutes les valeurs
utilisées lors du calcul (identité, taux, montants) sont dupliquées
ici en snapshot, indépendamment des données sources qui peuvent
évoluer par la suite (cf. schema.sql, table bulletins_paie).

Note monétaire : tous les champs financiers sont des FCFA entiers
(int). Le futur paie_service.py effectuera ses calculs avec Decimal
puis arrondira explicitement à l'entier avant de peupler ce modèle.
Seules les heures (durées) restent en float.
"""

from dataclasses import dataclass
from typing import Optional

from models.enums import Sexe, StatutEnseignant


@dataclass
class BulletinPaie:
    enseignant_id: int
    periode_id: int

    # Snapshots identité
    nom_snapshot: str
    prenom_snapshot: str
    sexe_snapshot: Sexe
    statut_snapshot: StatutEnseignant

    # Heures (durée) et montants (FCFA entiers)
    total_heures: float
    taux_horaire: int
    gain_heures: int

    # Éléments de rémunération (snapshot, FCFA entiers)
    prime_ap_pp: int
    surveillance_secretariat: int
    indemnite_suggestion_admin: int

    # Taxation (FCFA entiers)
    base_taxable: int
    taxe_5pct: int

    # Retenues (snapshot, FCFA entiers)
    retenue_amicale: int
    dette: int

    # Résultat (FCFA entiers)
    net_a_payer: int

    id: Optional[int] = None
    date_generation: Optional[str] = None
    utilisateur_generation: Optional[str] = None

    @staticmethod
    def from_row(row) -> "BulletinPaie":
        return BulletinPaie(
            id=row["id"],
            enseignant_id=row["enseignant_id"],
            periode_id=row["periode_id"],
            nom_snapshot=row["nom_snapshot"],
            prenom_snapshot=row["prenom_snapshot"],
            sexe_snapshot=Sexe(row["sexe_snapshot"]),
            statut_snapshot=StatutEnseignant(row["statut_snapshot"]),
            total_heures=row["total_heures"],
            taux_horaire=row["taux_horaire"],
            gain_heures=row["gain_heures"],
            prime_ap_pp=row["prime_ap_pp"],
            surveillance_secretariat=row["surveillance_secretariat"],
            indemnite_suggestion_admin=row["indemnite_suggestion_admin"],
            base_taxable=row["base_taxable"],
            taxe_5pct=row["taxe_5pct"],
            retenue_amicale=row["retenue_amicale"],
            dette=row["dette"],
            net_a_payer=row["net_a_payer"],
            date_generation=row["date_generation"],
            utilisateur_generation=row["utilisateur_generation"] if "utilisateur_generation" in row.keys() else None,
        )
