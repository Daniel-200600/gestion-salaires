"""Modèle de données : Alerte (module 16 — notifications et surveillance opérationnelle)."""

from dataclasses import dataclass
from typing import Optional

from models.enums import NiveauAlerte, StatutAlerte


@dataclass
class Alerte:
    type_alerte: str
    niveau: NiveauAlerte
    titre: str
    message: str
    source: str
    cle_deduplication: str

    id: Optional[int] = None
    statut: StatutAlerte = StatutAlerte.NOUVELLE
    date_creation: Optional[str] = None
    date_derniere_detection: Optional[str] = None
    periode_id: Optional[int] = None
    enseignant_id: Optional[int] = None
    document_id: Optional[int] = None
    import_id: Optional[int] = None
    utilisateur_concerne: Optional[str] = None
    date_acquittement: Optional[str] = None
    acquitte_par: Optional[str] = None
    date_resolution: Optional[str] = None
    resolue_par: Optional[str] = None

    @staticmethod
    def from_row(row) -> "Alerte":
        return Alerte(
            id=row["id"],
            type_alerte=row["type_alerte"],
            niveau=NiveauAlerte(row["niveau"]),
            titre=row["titre"],
            message=row["message"],
            source=row["source"],
            cle_deduplication=row["cle_deduplication"],
            statut=StatutAlerte(row["statut"]),
            date_creation=row["date_creation"],
            date_derniere_detection=row["date_derniere_detection"],
            periode_id=row["periode_id"],
            enseignant_id=row["enseignant_id"],
            document_id=row["document_id"],
            import_id=row["import_id"],
            utilisateur_concerne=row["utilisateur_concerne"],
            date_acquittement=row["date_acquittement"],
            acquitte_par=row["acquitte_par"],
            date_resolution=row["date_resolution"],
            resolue_par=row["resolue_par"],
        )
