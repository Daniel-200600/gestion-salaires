"""
Accès à la table `bulletins_paie`.

Ce repository expose UNE SEULE fonction d'écriture, `enregistrer_snapshot`,
qui ne fait qu'INSÉRER (jamais mettre à jour ni supprimer) : chaque
ligne, une fois créée, devient immuable pour toujours — garanti à la
fois par les triggers SQL du schéma (trg_bulletins_paie_immuable_update
/ _delete, cf. database/schema.sql) ET par l'absence intentionnelle de
toute fonction de modification/suppression ici. C'est cette
combinaison qui garantit que le CAS 3 de la suppression d'enseignant
(bulletin existant -> suppression interdite) ne peut jamais être
contourné, et que l'historique d'une période clôturée (module 12) ne
peut jamais dériver après coup.
"""

from pathlib import Path
from typing import List, Optional, Union
import sqlite3

from database.connection import get_connection
from models.bulletin_paie import BulletinPaie

DbPath = Optional[Union[str, Path]]


def compter_par_enseignant(
    enseignant_id: int, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> int:
    """Nombre de bulletins existants pour un enseignant, tous périodes confondues."""
    requete = "SELECT COUNT(*) AS total FROM bulletins_paie WHERE enseignant_id = ?"
    if conn is not None:
        return conn.execute(requete, (enseignant_id,)).fetchone()["total"]
    with get_connection(db_path) as connexion:
        return connexion.execute(requete, (enseignant_id,)).fetchone()["total"]


def lister_par_enseignant(enseignant_id: int, db_path: DbPath = None) -> List[BulletinPaie]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM bulletins_paie WHERE enseignant_id = ? ORDER BY periode_id",
            (enseignant_id,),
        ).fetchall()
        return [BulletinPaie.from_row(row) for row in rows]


def lister_par_periode(periode_id: int, db_path: DbPath = None) -> List[BulletinPaie]:
    """Tous les instantanés de bulletins enregistrés pour une période, tout enseignant confondu."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM bulletins_paie WHERE periode_id = ? ORDER BY nom_snapshot, prenom_snapshot",
            (periode_id,),
        ).fetchall()
        return [BulletinPaie.from_row(row) for row in rows]


def enregistrer_snapshot(
    bulletin: BulletinPaie, db_path: DbPath = None, conn: "Optional[sqlite3.Connection]" = None
) -> bool:
    """
    Enregistre l'instantané IMMUABLE d'un bulletin (module 12, section 11) :
    identité, heures et montants au moment de la génération, indépendamment
    de toute donnée source pouvant changer ensuite.

    Contraintes déjà appliquées par le schéma : le trigger
    `trg_bulletins_paie_requiert_periode_validee` exige que la période
    soit VALIDEE au moment de l'insertion (un bulletin ne peut donc être
    snapshotté que pour une période VALIDEE ou CLOTUREE — jamais
    OUVERTE) ; la contrainte UNIQUE(enseignant_id, periode_id) empêche
    un second instantané pour le même couple.

    Retourne True si l'instantané a été créé, False s'il existait déjà
    (idempotent : le PREMIER instantané fait foi, aucune exception n'est
    levée pour un appel répété) ou si la période n'est pas VALIDEE/CLOTUREE
    (auquel cas aucun instantané n'est pris — comportement volontaire :
    la génération de bulletins reste possible pour une période OUVERTE,
    comme depuis le module 07, mais ne produit alors aucun instantané).
    """
    requete = """
        INSERT INTO bulletins_paie (
            enseignant_id, periode_id, nom_snapshot, prenom_snapshot,
            sexe_snapshot, statut_snapshot, total_heures, taux_horaire,
            gain_heures, prime_ap_pp, surveillance_secretariat,
            indemnite_suggestion_admin, base_taxable, taxe_5pct,
            retenue_amicale, dette, net_a_payer, utilisateur_generation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    parametres = (
        bulletin.enseignant_id, bulletin.periode_id, bulletin.nom_snapshot, bulletin.prenom_snapshot,
        bulletin.sexe_snapshot.value, bulletin.statut_snapshot.value, bulletin.total_heures,
        bulletin.taux_horaire, bulletin.gain_heures, bulletin.prime_ap_pp, bulletin.surveillance_secretariat,
        bulletin.indemnite_suggestion_admin, bulletin.base_taxable, bulletin.taxe_5pct,
        bulletin.retenue_amicale, bulletin.dette, bulletin.net_a_payer, bulletin.utilisateur_generation,
    )

    try:
        if conn is not None:
            conn.execute(requete, parametres)
            return True
        with get_connection(db_path) as connexion:
            connexion.execute(requete, parametres)
            connexion.commit()
            return True
    except sqlite3.IntegrityError:
        # UNIQUE(enseignant_id, periode_id) déjà pris (régénération d'un
        # bulletin déjà instantané) ou trigger de statut (période pas
        # encore VALIDEE) : dans les deux cas, silencieusement ignoré —
        # jamais d'exception propagée pour un instantané absent ou déjà pris.
        return False
