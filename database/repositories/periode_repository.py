"""
Accès aux données de la table `periodes_paie`.

Ce module ne contient AUCUNE logique métier ni validation : il exécute
des requêtes SQL et convertit les résultats en objets PeriodePaie.
Toute règle de gestion (validations, contrôle des transitions) vit
dans services/periode_service.py.

Le contrôle des transitions d'état est en plus garanti au niveau SQL
par des triggers (cf. database/schema.sql) : même un appel direct à ce
repository hors du service resterait bloqué en cas de transition
illégale.

Chaque fonction accepte un paramètre optionnel `db_path` afin de rester
testable sur une base temporaire, sans dépendre de la base de
production (config.settings.DB_PATH utilisé par défaut si omis).
"""

from pathlib import Path
from typing import List, Optional, Union
import sqlite3

from database.connection import get_connection
from models.enums import StatutPeriode
from models.periode_paie import PeriodePaie

DbPath = Optional[Union[str, Path]]


def creer(periode: PeriodePaie, db_path: DbPath = None) -> int:
    """Insère une nouvelle période (toujours créée au statut BROUILLON par défaut du schéma)."""
    with get_connection(db_path) as conn:
        curseur = conn.execute(
            "INSERT INTO periodes_paie (mois, annee, libelle) VALUES (?, ?, ?)",
            (periode.mois, periode.annee, periode.libelle),
        )
        conn.commit()
        return curseur.lastrowid


def obtenir_par_id(
    periode_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> Optional[PeriodePaie]:
    """
    Si `conn` est fourni, la lecture est exécutée sur cette connexion
    (utilisé par l'enregistrement groupé transactionnel de
    services/donnees_paie_service.py). Sinon, comportement inchangé.
    """
    if conn is not None:
        row = conn.execute("SELECT * FROM periodes_paie WHERE id = ?", (periode_id,)).fetchone()
        return PeriodePaie.from_row(row) if row is not None else None
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM periodes_paie WHERE id = ?", (periode_id,)).fetchone()
        return PeriodePaie.from_row(row) if row is not None else None


def obtenir_par_mois_annee(mois: int, annee: int, db_path: DbPath = None) -> Optional[PeriodePaie]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM periodes_paie WHERE mois = ? AND annee = ?", (mois, annee)
        ).fetchone()
        return PeriodePaie.from_row(row) if row is not None else None


def lister(
    annee: Optional[int] = None,
    statut: Optional[StatutPeriode] = None,
    db_path: DbPath = None,
) -> List[PeriodePaie]:
    """
    Liste les périodes, les plus récentes en premier (tri par année puis
    mois décroissants), avec filtres optionnels par année et/ou statut.
    """
    requete = "SELECT * FROM periodes_paie WHERE 1 = 1"
    parametres: List[Union[int, str]] = []
    if annee is not None:
        requete += " AND annee = ?"
        parametres.append(annee)
    if statut is not None:
        valeur_statut = statut.value if isinstance(statut, StatutPeriode) else statut
        requete += " AND statut = ?"
        parametres.append(valeur_statut)
    requete += " ORDER BY annee DESC, mois DESC"
    with get_connection(db_path) as conn:
        rows = conn.execute(requete, parametres).fetchall()
        return [PeriodePaie.from_row(row) for row in rows]


def modifier(periode: PeriodePaie, db_path: DbPath = None) -> None:
    """
    Met à jour mois/année/libellé d'une période existante.

    Le service garantit que cette fonction n'est appelée que pour une
    période encore en BROUILLON ; ce repository ne fait aucune
    vérification de statut lui-même.
    """
    if periode.id is None:
        raise ValueError("periode.id est requis pour une mise à jour.")
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE periodes_paie SET mois = ?, annee = ?, libelle = ? WHERE id = ?",
            (periode.mois, periode.annee, periode.libelle, periode.id),
        )
        conn.commit()


def changer_statut(
    periode_id: int, statut: StatutPeriode, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> None:
    """
    Change le statut sans toucher date_cloture (utilisé pour OUVERTE et VALIDEE).

    Si `conn` est fourni, exécuté sur cette connexion sans commit
    (transaction gérée par l'appelant — utilisé par
    services/controle_paie_service.py pour que la transition d'état et
    l'écriture d'audit appartiennent à la même transaction SQLite).
    """
    requete = "UPDATE periodes_paie SET statut = ? WHERE id = ?"
    if conn is not None:
        conn.execute(requete, (statut.value, periode_id))
        return
    with get_connection(db_path) as connexion:
        connexion.execute(requete, (statut.value, periode_id))
        connexion.commit()


def cloturer(periode_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None) -> None:
    """
    Passe la période au statut CLOTUREE et renseigne date_cloture dans la
    même transaction (requis par la contrainte CHECK du schéma qui lie
    les deux colonnes).

    Si `conn` est fourni, exécuté sur cette connexion sans commit
    (transaction gérée par l'appelant).
    """
    requete = "UPDATE periodes_paie SET statut = ?, date_cloture = datetime('now') WHERE id = ?"
    if conn is not None:
        conn.execute(requete, (StatutPeriode.CLOTUREE.value, periode_id))
        return
    with get_connection(db_path) as connexion:
        connexion.execute(requete, (StatutPeriode.CLOTUREE.value, periode_id))
        connexion.commit()


def supprimer_definitivement(
    periode_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> None:
    """
    Suppression PHYSIQUE et IRRÉVERSIBLE d'une période.

    Ne doit être appelée que par
    services/periode_service.supprimer_periode_definitivement, APRÈS
    suppression de toutes les dépendances (heures, rémunérations,
    retenues) et vérification qu'aucun bulletin n'existe pour cette
    période. Le trigger SQL trg_periodes_paie_suppression_limitee
    (cf. database/schema.sql) constitue un filet de sécurité
    supplémentaire : il rejette de toute façon toute suppression d'une
    période dont le statut n'est pas 'brouillon'.

    Si `conn` est fourni, exécutée sur cette connexion sans commit
    (transaction gérée par l'appelant).
    """
    requete = "DELETE FROM periodes_paie WHERE id = ?"
    if conn is not None:
        conn.execute(requete, (periode_id,))
        return
    with get_connection(db_path) as connexion:
        connexion.execute(requete, (periode_id,))
        connexion.commit()
