"""
Accès aux données de la table `enseignants`.

Ce module ne contient AUCUNE logique métier ni validation : il se
contente d'exécuter des requêtes SQL et de convertir les résultats en
objets Enseignant. Toute règle de gestion vit dans
services/enseignant_service.py.

Aucune suppression physique n'est exposée ici : un enseignant pouvant
posséder un historique de paie ne doit jamais être supprimé de la base
(cf. contraintes ON DELETE RESTRICT du schéma), seulement désactivé
via `changer_statut_actif`.

Chaque fonction accepte un paramètre optionnel `db_path` afin de rester
testable sur une base temporaire, sans dépendre de la base de
production (config.settings.DB_PATH utilisé par défaut si omis).
"""

from pathlib import Path
from typing import List, Optional, Union
import sqlite3

from database.connection import get_connection
from models.enseignant import Enseignant

DbPath = Optional[Union[str, Path]]


def creer(enseignant: Enseignant, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None) -> int:
    """
    Insère un nouvel enseignant et retourne son id généré.

    Si `conn` est fourni, l'opération est exécutée sur cette connexion
    SANS commit (utilisé par l'import transactionnel du module 15).
    Sinon, comportement inchangé : ouvre sa propre connexion et commit.
    """
    requete = """
        INSERT INTO enseignants (nom, prenom, sexe, statut, taux_horaire, email, telephone, adresse, actif)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    parametres = (
        enseignant.nom, enseignant.prenom, enseignant.sexe.value, enseignant.statut.value,
        enseignant.taux_horaire, enseignant.email, enseignant.telephone, enseignant.adresse, enseignant.actif,
    )
    if conn is not None:
        curseur = conn.execute(requete, parametres)
        return curseur.lastrowid
    with get_connection(db_path) as connexion:
        curseur = connexion.execute(requete, parametres)
        connexion.commit()
        return curseur.lastrowid


def obtenir_par_id(
    enseignant_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> Optional[Enseignant]:
    """
    Retourne l'enseignant correspondant, ou None s'il n'existe pas.

    Si `conn` est fourni, la lecture est exécutée sur cette connexion
    (aucune connexion supplémentaire n'est ouverte) : utilisé par
    l'enregistrement groupé transactionnel de
    services/donnees_paie_service.py, qui doit lire et écrire sur une
    seule et même connexion/transaction. Sinon, comportement inchangé
    (connexion dédiée via db_path).
    """
    if conn is not None:
        row = conn.execute("SELECT * FROM enseignants WHERE id = ?", (enseignant_id,)).fetchone()
        return Enseignant.from_row(row) if row is not None else None
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM enseignants WHERE id = ?", (enseignant_id,)).fetchone()
        return Enseignant.from_row(row) if row is not None else None


def lister(inclure_inactifs: bool = False, db_path: DbPath = None) -> List[Enseignant]:
    """
    Liste les enseignants, triés par nom puis prénom.

    Par défaut (inclure_inactifs=False), seuls les enseignants actifs
    sont retournés (usage typique : listes destinées aux nouvelles paies).
    """
    requete = "SELECT * FROM enseignants"
    if not inclure_inactifs:
        requete += " WHERE actif = 1"
    requete += " ORDER BY nom, prenom"
    with get_connection(db_path) as conn:
        rows = conn.execute(requete).fetchall()
        return [Enseignant.from_row(row) for row in rows]


def rechercher(terme: str, inclure_inactifs: bool = False, db_path: DbPath = None) -> List[Enseignant]:
    """
    Recherche par nom, prénom ou nom complet (dans les deux ordres),
    insensible à la casse.
    """
    motif = f"%{terme.strip().lower()}%"
    requete = """
        SELECT * FROM enseignants
        WHERE (
            LOWER(nom) LIKE ?
            OR LOWER(prenom) LIKE ?
            OR LOWER(nom || ' ' || prenom) LIKE ?
            OR LOWER(prenom || ' ' || nom) LIKE ?
        )
    """
    parametres = [motif, motif, motif, motif]
    if not inclure_inactifs:
        requete += " AND actif = 1"
    requete += " ORDER BY nom, prenom"
    with get_connection(db_path) as conn:
        rows = conn.execute(requete, parametres).fetchall()
        return [Enseignant.from_row(row) for row in rows]


def mettre_a_jour(
    enseignant: Enseignant, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> None:
    """
    Met à jour les champs modifiables d'un enseignant existant.

    Ne touche jamais `actif` (voir `changer_statut_actif`) ni
    `date_creation`. `date_modification` est mise à jour automatiquement
    par le trigger SQL `trg_enseignants_maj_date`.

    Si `conn` est fourni, l'opération est exécutée sur cette connexion
    SANS commit (utilisé par l'import transactionnel du module 15).
    """
    if enseignant.id is None:
        raise ValueError("enseignant.id est requis pour une mise à jour.")
    requete = """
        UPDATE enseignants
        SET nom = ?, prenom = ?, sexe = ?, statut = ?, taux_horaire = ?,
            email = ?, telephone = ?, adresse = ?
        WHERE id = ?
    """
    parametres = (
        enseignant.nom, enseignant.prenom, enseignant.sexe.value, enseignant.statut.value,
        enseignant.taux_horaire, enseignant.email, enseignant.telephone, enseignant.adresse, enseignant.id,
    )
    if conn is not None:
        conn.execute(requete, parametres)
        return
    with get_connection(db_path) as connexion:
        connexion.execute(requete, parametres)
        connexion.commit()


def changer_statut_actif(enseignant_id: int, actif: bool, db_path: DbPath = None) -> None:
    """Active ou désactive un enseignant. Ne supprime jamais la ligne."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE enseignants SET actif = ? WHERE id = ?",
            (1 if actif else 0, enseignant_id),
        )
        conn.commit()


def supprimer_definitivement(
    enseignant_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> None:
    """
    Suppression PHYSIQUE et IRRÉVERSIBLE d'un enseignant.

    Ne doit être appelée que par
    services/enseignant_service.supprimer_enseignant_definitivement,
    APRÈS suppression de toutes les dépendances (heures, rémunérations,
    retenues) et vérification qu'aucun bulletin n'existe pour cet
    enseignant — sans quoi la contrainte de clé étrangère ON DELETE
    RESTRICT rejettera de toute façon la suppression.

    Si `conn` est fourni, exécutée sur cette connexion sans commit
    (transaction gérée par l'appelant, pour une suppression en cascade
    atomique avec ses dépendances).
    """
    requete = "DELETE FROM enseignants WHERE id = ?"
    if conn is not None:
        conn.execute(requete, (enseignant_id,))
        return
    with get_connection(db_path) as connexion:
        connexion.execute(requete, (enseignant_id,))
        connexion.commit()
