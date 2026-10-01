"""Modèle de données : AuditLog (structure prévue pour un usage futur)."""

from dataclasses import dataclass
from typing import Optional

from models.enums import TypeActionAudit


@dataclass
class AuditLog:
    type_action: TypeActionAudit

    id: Optional[int] = None
    date_action: Optional[str] = None
    entite: Optional[str] = None
    entite_id: Optional[int] = None
    utilisateur: Optional[str] = None
    details: Optional[str] = None

    @staticmethod
    def from_row(row) -> "AuditLog":
        return AuditLog(
            id=row["id"],
            date_action=row["date_action"],
            type_action=TypeActionAudit(row["type_action"]),
            entite=row["entite"],
            entite_id=row["entite_id"],
            utilisateur=row["utilisateur"],
            details=row["details"],
        )
