"""Modèle de données : Utilisateur (module 11 — authentification et permissions)."""

from dataclasses import dataclass
from typing import Optional

from models.enums import RoleUtilisateur


@dataclass
class Utilisateur:
    nom: str
    prenom: str
    username: str
    password_hash: str
    role: RoleUtilisateur

    id: Optional[int] = None
    actif: bool = True
    date_creation: Optional[str] = None
    date_modification: Optional[str] = None
    derniere_connexion: Optional[str] = None

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}"

    @staticmethod
    def from_row(row) -> "Utilisateur":
        return Utilisateur(
            id=row["id"],
            nom=row["nom"],
            prenom=row["prenom"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=RoleUtilisateur(row["role"]),
            actif=bool(row["actif"]),
            date_creation=row["date_creation"],
            date_modification=row["date_modification"],
            derniere_connexion=row["derniere_connexion"],
        )
