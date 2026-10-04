"""
Migrations SQLite runtime (correction — consolidation finale).

`database/schema.sql` utilise exclusivement `CREATE TABLE IF NOT
EXISTS`, qui ne modifie JAMAIS une table déjà existante — y compris
sa contrainte CHECK. Chaque module ayant ajouté de nouvelles valeurs
à `type_action` (09 à 19) l'a donc fait correctement pour une base
NEUVE, mais une base créée par une version antérieure de l'application
conserve silencieusement son ancienne contrainte CHECK pour toujours.

Conséquence concrète : `auth_service.connecter()` (ou toute autre
action journalisée dont le type n'existait pas encore lors de la
création de cette base) échoue avec
`sqlite3.IntegrityError: CHECK constraint failed` — le bug rapporté.

Ce module corrige cela avec une VRAIE migration runtime, car SQLite
ne permet pas de modifier une contrainte CHECK en place : la seule
stratégie sûre est de renommer l'ancienne table, recréer la table à
jour, copier les données, puis supprimer l'ancienne. Idempotente
(une base déjà à jour n'est jamais touchée) et sans perte de données
(toutes les lignes existantes sont copiées, y compris celles dont le
`type_action` était déjà valide sous l'ancienne contrainte — un
sur-ensemble strict, jamais un retrait de valeur, dans toute
l'histoire additive du projet).
"""

import logging
import re
import sqlite3
from typing import Optional

logger = logging.getLogger("salaires_app.migrations")

_COLONNES_AUDIT_LOG = "id, date_action, type_action, entite, entite_id, utilisateur, details"


def _sql_table_existante(conn: sqlite3.Connection, nom_table: str) -> Optional[str]:
    """Retourne le SQL de création réellement stocké par SQLite pour cette table, ou None si elle n'existe pas."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (nom_table,)
    ).fetchone()
    return row[0] if row else None


def _audit_log_necessite_migration(conn: sqlite3.Connection) -> bool:
    """
    Vrai uniquement si `audit_log` existe déjà mais que son CHECK
    constraint stocké ne couvre pas toutes les valeurs actuelles de
    `TypeActionAudit`. Une base neuve (table pas encore créée) ne
    nécessite aucune migration : `schema.sql` s'en charge normalement.
    """
    sql_existant = _sql_table_existante(conn, "audit_log")
    if sql_existant is None:
        return False

    from models.enums import TypeActionAudit

    return any(f"'{valeur.value}'" not in sql_existant for valeur in TypeActionAudit)


def migrer_audit_log_si_necessaire(conn: sqlite3.Connection, schema_sql: str) -> bool:
    """
    Migre `audit_log` vers la contrainte CHECK à jour si nécessaire.

    Stratégie (SQLite ne permet pas d'altérer un CHECK en place) :
    1. renommer l'ancienne table (`audit_log` -> `audit_log_migration_temp`) ;
    2. exécuter `schema.sql` (recrée `audit_log` avec le CHECK à jour ;
       toutes les autres instructions sont des `IF NOT EXISTS` déjà
       satisfaits, donc sans effet) ;
    3. copier l'intégralité des lignes de l'ancienne table (jamais de
       perte : le nouveau CHECK est toujours un sur-ensemble) ;
    4. supprimer l'ancienne table une fois la copie confirmée.

    Toute erreur en cours de route déclenche un rollback complet — la
    base n'est jamais laissée dans un état intermédiaire incohérent.
    Retourne True si une migration a effectivement eu lieu, False si
    la base était déjà à jour (cas normal, aucune action).
    """
    if not _audit_log_necessite_migration(conn):
        return False

    logger.info("Migration de audit_log : ancienne contrainte CHECK détectée, mise à jour en cours.")

    try:
        conn.execute("ALTER TABLE audit_log RENAME TO audit_log_migration_temp")
        conn.executescript(schema_sql)
        conn.execute(
            f"INSERT INTO audit_log ({_COLONNES_AUDIT_LOG}) "
            f"SELECT {_COLONNES_AUDIT_LOG} FROM audit_log_migration_temp"
        )
        nb_avant = conn.execute("SELECT COUNT(*) FROM audit_log_migration_temp").fetchone()[0]
        nb_apres = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        if nb_apres < nb_avant:
            raise RuntimeError(
                f"Migration audit_log incomplète : {nb_avant} ligne(s) avant, {nb_apres} après."
            )
        conn.execute("DROP TABLE audit_log_migration_temp")
        conn.commit()
    except Exception:
        conn.rollback()
        logger.error("Échec de la migration audit_log — la base a été restaurée à son état antérieur.")
        raise

    logger.info("Migration de audit_log terminée avec succès (%d ligne(s) conservée(s)).", nb_apres)
    return True


# ---------------------------------------------------------------------
# Colonnes ajoutées après coup (taux de taxe par période)
# ---------------------------------------------------------------------

# (table, colonne, définition SQL complète utilisée par ALTER TABLE)
COLONNES_AJOUTEES = (
    (
        "periodes_paie",
        "taux_taxe",
        "taux_taxe TEXT NOT NULL DEFAULT '0.05' "
        "CHECK (CAST(taux_taxe AS REAL) >= 0 AND CAST(taux_taxe AS REAL) < 1)",
    ),
    # Taxe réservée aux vacataires : les périodes existantes reçoivent
    # l'ancienne règle (1 = permanents taxés aussi), sans aucune mise à
    # jour de ligne — une période clôturée n'est jamais modifiée.
    (
        "periodes_paie",
        "taxe_permanents",
        "taxe_permanents INTEGER NOT NULL DEFAULT 1 CHECK (taxe_permanents IN (0, 1))",
    ),
    # Salaire mensuel fixe des permanents (version 1.7.0) : vide pour tous
    # les enseignants existants, dont le calcul reste donc inchangé.
    (
        "enseignants",
        "salaire_fixe",
        "salaire_fixe INTEGER NULL CHECK (salaire_fixe IS NULL OR salaire_fixe >= 0) "
        "CHECK (salaire_fixe IS NULL OR salaire_fixe = CAST(salaire_fixe AS INTEGER))",
    ),
)

# Après l'ajout d'une colonne : les périodes encore modifiables (brouillon,
# ouverte) passent tout de suite à la nouvelle règle.
APRES_AJOUT = {
    ("periodes_paie", "taxe_permanents"):
        "UPDATE periodes_paie SET taxe_permanents = 0 WHERE statut IN ('brouillon', 'ouverte')",
}


def _colonnes_table(conn: sqlite3.Connection, nom_table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({nom_table})").fetchall()}


def ajouter_colonnes_manquantes(conn: sqlite3.Connection) -> list:
    """
    Ajoute aux tables EXISTANTES les colonnes introduites par une
    version plus récente (ALTER TABLE ... ADD COLUMN, sans perte de
    donnée). Une base neuve n'est pas concernée : `schema.sql` crée
    directement les tables complètes.

    Les périodes existantes reçoivent le taux historique de 5 %
    ('0.05', valeur par défaut de la colonne) : c'est le taux avec
    lequel elles ont été calculées, leurs résultats restent donc
    strictement identiques.

    Retourne la liste des colonnes ajoutées (« table.colonne »).
    """
    ajoutees = []
    for table, colonne, definition in COLONNES_AJOUTEES:
        if _sql_table_existante(conn, table) is None:
            continue
        if colonne in _colonnes_table(conn, table):
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
        if (table, colonne) in APRES_AJOUT:
            conn.execute(APRES_AJOUT[(table, colonne)])
        ajoutees.append(f"{table}.{colonne}")
        logger.info("Migration : colonne %s.%s ajoutée.", table, colonne)
    if ajoutees:
        conn.commit()
    return ajoutees


# ---------------------------------------------------------------------
# Fiches enseignant complétables plus tard (sexe, statut, taux facultatifs)
# ---------------------------------------------------------------------

_COLONNES_ENSEIGNANTS = (
    "id, nom, prenom, sexe, statut, taux_horaire, email, telephone, adresse, actif, "
    "date_creation, date_modification"
)


def _enseignants_necessite_migration(conn: sqlite3.Connection) -> bool:
    sql_existant = _sql_table_existante(conn, "enseignants")
    return sql_existant is not None and re.search(r"\bsexe\s+TEXT\s+NOT\s+NULL", sql_existant) is not None


def rendre_fiches_enseignants_completables(conn: sqlite3.Connection, schema_sql: str) -> bool:
    """
    Permet d'enregistrer un enseignant sans sexe, statut ni taux horaire
    (fiche importée incomplète, complétée plus tard).

    SQLite ne sait pas retirer un NOT NULL en place : la table est
    reconstruite selon la procédure documentée par SQLite (« making other
    kinds of table schema changes ») — nouvelle table, copie intégrale,
    suppression de l'ancienne, renommage — clés étrangères suspendues le
    temps de l'opération puis vérifiées (PRAGMA foreign_key_check) avant
    validation. Les tables liées (heures, primes, retenues, bulletins...)
    gardent leurs références. Tout échec annule l'ensemble.

    Retourne True si la migration a eu lieu, False si la base était déjà à jour.
    """
    if not _enseignants_necessite_migration(conn):
        return False
    correspondance = re.search(r"CREATE TABLE IF NOT EXISTS enseignants \((.*?)\n\);", schema_sql, re.S)
    if correspondance is None:
        raise RuntimeError("Définition de la table enseignants introuvable dans schema.sql.")
    definition = correspondance.group(1)

    logger.info("Migration de enseignants : sexe, statut et taux horaire deviennent facultatifs.")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        conn.execute("BEGIN")
        conn.execute(f"CREATE TABLE enseignants_migration ({definition}\n)")
        conn.execute(
            f"INSERT INTO enseignants_migration ({_COLONNES_ENSEIGNANTS}) "
            f"SELECT {_COLONNES_ENSEIGNANTS} FROM enseignants"
        )
        nb_avant = conn.execute("SELECT COUNT(*) FROM enseignants").fetchone()[0]
        conn.execute("DROP TABLE enseignants")
        conn.execute("ALTER TABLE enseignants_migration RENAME TO enseignants")
        nb_apres = conn.execute("SELECT COUNT(*) FROM enseignants").fetchone()[0]
        if nb_apres != nb_avant:
            raise RuntimeError(f"Migration enseignants incomplète : {nb_avant} ligne(s) avant, {nb_apres} après.")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Migration enseignants : références orphelines détectées.")
        conn.commit()
    except Exception:
        conn.rollback()
        logger.error("Échec de la migration enseignants — la base a été restaurée à son état antérieur.")
        raise
    finally:
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("PRAGMA foreign_keys = ON")
    logger.info("Migration de enseignants terminée (%d enseignant(s) conservé(s)).", nb_apres)
    return True
