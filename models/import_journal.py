"""Modèles de données : ImportJournal et AnomalieImport (module 15 — importation massive)."""

from dataclasses import dataclass
from typing import Optional

from models.enums import NiveauAnomalie, StatutImport, TypeImport


@dataclass
class ImportJournal:
    """Une opération d'importation enregistrée (section 17/32)."""

    nom_fichier: str
    type_import: TypeImport
    statut: StatutImport

    id: Optional[int] = None
    utilisateur: Optional[str] = None
    date_import: Optional[str] = None
    periode_id: Optional[int] = None
    nb_lignes: int = 0
    nb_creations: int = 0
    nb_mises_a_jour: int = 0
    nb_ignorees: int = 0
    nb_rejetees: int = 0
    nb_erreurs: int = 0
    nb_avertissements: int = 0

    @staticmethod
    def from_row(row) -> "ImportJournal":
        return ImportJournal(
            id=row["id"],
            utilisateur=row["utilisateur"],
            date_import=row["date_import"],
            nom_fichier=row["nom_fichier"],
            type_import=TypeImport(row["type_import"]),
            statut=StatutImport(row["statut"]),
            periode_id=row["periode_id"],
            nb_lignes=row["nb_lignes"],
            nb_creations=row["nb_creations"],
            nb_mises_a_jour=row["nb_mises_a_jour"],
            nb_ignorees=row["nb_ignorees"],
            nb_rejetees=row["nb_rejetees"],
            nb_erreurs=row["nb_erreurs"],
            nb_avertissements=row["nb_avertissements"],
        )


@dataclass
class AnomalieImport:
    """Une anomalie détectée sur une ligne du fichier importé (section 18/27)."""

    ligne: int
    niveau: NiveauAnomalie
    message: str
    champ: Optional[str] = None
    valeur: Optional[str] = None

    id: Optional[int] = None
    import_id: Optional[int] = None

    @staticmethod
    def from_row(row) -> "AnomalieImport":
        return AnomalieImport(
            id=row["id"],
            import_id=row["import_id"],
            ligne=row["ligne"],
            champ=row["champ"],
            valeur=row["valeur"],
            niveau=NiveauAnomalie(row["niveau"]),
            message=row["message"],
        )
