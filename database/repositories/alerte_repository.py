"""
Accès aux données de la table `alertes` (module 16). Ce module ne
contient AUCUNE logique de détection : il se contente d'exécuter des
requêtes SQL et de convertir les résultats en objets Alerte. Toute
règle de détection vit dans services/alert_detection_service.py, et
les règles de cycle de vie (transitions, déduplication applicative)
dans services/alert_service.py.
"""

from pathlib import Path
from typing import List, Optional, Union

from database.connection import get_connection
from models.alerte import Alerte
from models.enums import NiveauAlerte, StatutAlerte

DbPath = Optional[Union[str, Path]]


def obtenir_par_cle_active(cle_deduplication: str, db_path: DbPath = None) -> Optional[Alerte]:
    """Retourne l'alerte ACTIVE (ni résolue ni ignorée) portant cette clé, s'il en existe une."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM alertes WHERE cle_deduplication = ? AND statut NOT IN ('resolue', 'ignoree')",
            (cle_deduplication,),
        ).fetchone()
        return Alerte.from_row(row) if row else None


def creer(alerte: Alerte, db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        curseur = conn.execute(
            """
            INSERT INTO alertes (
                type_alerte, niveau, titre, message, source, cle_deduplication, statut,
                periode_id, enseignant_id, document_id, import_id, utilisateur_concerne
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alerte.type_alerte, alerte.niveau.value, alerte.titre, alerte.message, alerte.source,
                alerte.cle_deduplication, alerte.statut.value, alerte.periode_id, alerte.enseignant_id,
                alerte.document_id, alerte.import_id, alerte.utilisateur_concerne,
            ),
        )
        conn.commit()
        return curseur.lastrowid


def mettre_a_jour_detection(alerte_id: int, titre: str, message: str, db_path: DbPath = None) -> None:
    """Anomalie toujours présente : rafraîchit le message et la date de dernière détection, sans dupliquer la ligne."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE alertes SET titre = ?, message = ?, date_derniere_detection = datetime('now') WHERE id = ?",
            (titre, message, alerte_id),
        )
        conn.commit()


def changer_statut(
    alerte_id: int, statut: StatutAlerte, utilisateur: Optional[str] = None, db_path: DbPath = None
) -> None:
    """Effectue la transition de statut et horodate/attribue l'action correspondante (acquittement ou résolution)."""
    colonnes_date = {
        StatutAlerte.ACQUITTEE: ("date_acquittement", "acquitte_par"),
        StatutAlerte.RESOLUE: ("date_resolution", "resolue_par"),
    }
    with get_connection(db_path) as conn:
        if statut in colonnes_date:
            colonne_date, colonne_acteur = colonnes_date[statut]
            conn.execute(
                f"UPDATE alertes SET statut = ?, {colonne_date} = datetime('now'), {colonne_acteur} = ? WHERE id = ?",
                (statut.value, utilisateur, alerte_id),
            )
        else:
            conn.execute("UPDATE alertes SET statut = ? WHERE id = ?", (statut.value, alerte_id))
        conn.commit()


def obtenir_par_id(alerte_id: int, db_path: DbPath = None) -> Optional[Alerte]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM alertes WHERE id = ?", (alerte_id,)).fetchone()
        return Alerte.from_row(row) if row else None


def rechercher(
    niveau: Optional[NiveauAlerte] = None,
    statut: Optional[StatutAlerte] = None,
    type_alerte: Optional[str] = None,
    periode_id: Optional[int] = None,
    enseignant_id: Optional[int] = None,
    source: Optional[str] = None,
    terme: Optional[str] = None,
    db_path: DbPath = None,
) -> List[Alerte]:
    """Recherche filtrée (section 17/34) : tous les filtres fournis se combinent (ET logique)."""
    requete = "SELECT * FROM alertes WHERE 1 = 1"
    parametres: List = []
    if niveau is not None:
        requete += " AND niveau = ?"
        parametres.append(niveau.value)
    if statut is not None:
        requete += " AND statut = ?"
        parametres.append(statut.value)
    if type_alerte is not None:
        requete += " AND type_alerte = ?"
        parametres.append(type_alerte)
    if periode_id is not None:
        requete += " AND periode_id = ?"
        parametres.append(periode_id)
    if enseignant_id is not None:
        requete += " AND enseignant_id = ?"
        parametres.append(enseignant_id)
    if source is not None:
        requete += " AND source = ?"
        parametres.append(source)
    if terme:
        requete += " AND (LOWER(titre) LIKE LOWER(?) OR LOWER(message) LIKE LOWER(?))"
        motif = f"%{terme}%"
        parametres.extend([motif, motif])
    requete += " ORDER BY date_derniere_detection DESC"

    with get_connection(db_path) as conn:
        rows = conn.execute(requete, parametres).fetchall()
        return [Alerte.from_row(row) for row in rows]


def compter_par_niveau(statut_exclu: Optional[List[StatutAlerte]] = None, db_path: DbPath = None) -> dict:
    """Compte les alertes par niveau (section 16/26), en excluant éventuellement certains statuts (résolues/ignorées)."""
    requete = "SELECT niveau, COUNT(*) AS total FROM alertes"
    parametres: List = []
    if statut_exclu:
        placeholders = ", ".join("?" for _ in statut_exclu)
        requete += f" WHERE statut NOT IN ({placeholders})"
        parametres.extend(s.value for s in statut_exclu)
    requete += " GROUP BY niveau"

    with get_connection(db_path) as conn:
        rows = conn.execute(requete, parametres).fetchall()
        resultat = {n.value: 0 for n in NiveauAlerte}
        for row in rows:
            resultat[row["niveau"]] = row["total"]
        return resultat


def lister_actives_par_source(source: str, db_path: DbPath = None) -> List[Alerte]:
    """Toutes les alertes actives (non résolues/ignorées) d'une source donnée — utilisé pour la résolution automatique."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM alertes WHERE source = ? AND statut NOT IN ('resolue', 'ignoree')", (source,)
        ).fetchall()
        return [Alerte.from_row(row) for row in rows]
