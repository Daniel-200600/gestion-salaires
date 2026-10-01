"""
Accès aux données de la table `utilisateurs`.

Ce module ne contient AUCUNE logique métier : ni hachage de mot de
passe (cf. utils/security.py), ni règle de permission (cf.
services/permission_service.py), ni validation (cf.
services/utilisateur_service.py, y compris la protection du dernier
ADMIN actif). Il se contente d'exécuter des requêtes SQL et de
convertir les résultats en objets Utilisateur.

Chaque fonction accepte un paramètre optionnel `db_path` afin de
rester testable sur une base temporaire.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional, Union

from database.connection import get_connection
from models.enums import RoleUtilisateur
from models.utilisateur import Utilisateur

DbPath = Optional[Union[str, Path]]


def creer(utilisateur: Utilisateur, db_path: DbPath = None) -> int:
    """Insère un nouvel utilisateur et retourne son id généré."""
    with get_connection(db_path) as conn:
        curseur = conn.execute(
            """
            INSERT INTO utilisateurs (nom, prenom, username, password_hash, role, actif)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                utilisateur.nom,
                utilisateur.prenom,
                utilisateur.username,
                utilisateur.password_hash,
                utilisateur.role.value,
                int(utilisateur.actif),
            ),
        )
        conn.commit()
        return curseur.lastrowid


def obtenir_par_id(utilisateur_id: int, db_path: DbPath = None) -> Optional[Utilisateur]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM utilisateurs WHERE id = ?", (utilisateur_id,)).fetchone()
        return Utilisateur.from_row(row) if row else None


def obtenir_par_username(username: str, db_path: DbPath = None) -> Optional[Utilisateur]:
    """Recherche insensible à la casse (deux usernames ne différant que par la casse seraient ambigus)."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM utilisateurs WHERE LOWER(username) = LOWER(?)", (username,)
        ).fetchone()
        return Utilisateur.from_row(row) if row else None


def lister(inclure_inactifs: bool = True, db_path: DbPath = None) -> List[Utilisateur]:
    requete = "SELECT * FROM utilisateurs"
    if not inclure_inactifs:
        requete += " WHERE actif = 1"
    requete += " ORDER BY nom, prenom"
    with get_connection(db_path) as conn:
        rows = conn.execute(requete).fetchall()
        return [Utilisateur.from_row(row) for row in rows]


def modifier_informations(
    utilisateur_id: int, nom: str, prenom: str, role: RoleUtilisateur, db_path: DbPath = None
) -> None:
    """Modifie nom/prénom/rôle. Ne touche JAMAIS au mot de passe (opération séparée, cf. changer_mot_de_passe)."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE utilisateurs SET nom = ?, prenom = ?, role = ? WHERE id = ?",
            (nom, prenom, role.value, utilisateur_id),
        )
        conn.commit()


def changer_mot_de_passe(utilisateur_id: int, nouveau_hash: str, db_path: DbPath = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE utilisateurs SET password_hash = ? WHERE id = ?", (nouveau_hash, utilisateur_id)
        )
        conn.commit()


def changer_statut_actif(utilisateur_id: int, actif: bool, db_path: DbPath = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE utilisateurs SET actif = ? WHERE id = ?", (int(actif), utilisateur_id)
        )
        conn.commit()


def mettre_a_jour_derniere_connexion(utilisateur_id: int, db_path: DbPath = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE utilisateurs SET derniere_connexion = datetime('now') WHERE id = ?",
            (utilisateur_id,),
        )
        conn.commit()


def compter_admins_actifs(
    db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None, exclure_id: Optional[int] = None
) -> int:
    """
    Nombre d'administrateurs actifs, optionnellement en excluant un id
    donné (utilisé pour vérifier AVANT une désactivation/changement de
    rôle si l'opération laisserait le système sans aucun ADMIN actif).
    """
    requete = "SELECT COUNT(*) AS total FROM utilisateurs WHERE role = ? AND actif = 1"
    parametres: List = [RoleUtilisateur.ADMIN.value]
    if exclure_id is not None:
        requete += " AND id != ?"
        parametres.append(exclure_id)

    if conn is not None:
        return conn.execute(requete, parametres).fetchone()["total"]
    with get_connection(db_path) as connexion:
        return connexion.execute(requete, parametres).fetchone()["total"]


def compter_tout(db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT COUNT(*) AS total FROM utilisateurs").fetchone()["total"]


def compter_actifs(db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT COUNT(*) AS total FROM utilisateurs WHERE actif = 1").fetchone()["total"]
