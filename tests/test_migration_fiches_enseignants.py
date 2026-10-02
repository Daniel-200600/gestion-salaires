"""
Migration des bases existantes : sexe, statut et taux horaire d'un
enseignant deviennent facultatifs (fiches importées à compléter plus tard),
sans perte de donnée ni rupture des liens avec les heures, primes, retenues
et bulletins.
"""

import sqlite3

import pytest

from config.settings import SCHEMA_PATH
from database import migrations
from database.initialization import init_database

ANCIENNE_DEFINITION = """    nom                 TEXT    NOT NULL,
    prenom              TEXT    NOT NULL,
    sexe                TEXT    NOT NULL CHECK (sexe IN ('M', 'F')),
    statut              TEXT    NOT NULL CHECK (statut IN ('V', 'P')),
    taux_horaire        INTEGER NOT NULL
                            CHECK (taux_horaire >= 0)
                            CHECK (taux_horaire = CAST(taux_horaire AS INTEGER)),
"""


def _ancien_schema() -> str:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    debut = schema.index("    nom                 TEXT    NOT NULL,\n    prenom")
    fin = schema.index("    email               TEXT    NULL,", debut)
    return schema[:debut] + ANCIENNE_DEFINITION + schema[fin:]


@pytest.fixture
def ancienne_base(tmp_path):
    chemin = tmp_path / "ancienne.db"
    with sqlite3.connect(chemin) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_ancien_schema())
        conn.execute(
            "INSERT INTO enseignants (nom, prenom, sexe, statut, taux_horaire, telephone) "
            "VALUES ('Fouda', 'Alain', 'M', 'V', 1500, '600000000')"
        )
        conn.execute("INSERT INTO periodes_paie (mois, annee, libelle) VALUES (3, 2026, 'Mars 2026')")
        conn.execute("UPDATE periodes_paie SET statut = 'ouverte'")
        conn.execute(
            "INSERT INTO saisies_heures (periode_id, enseignant_id, numero_semaine, heures_effectuees) VALUES (1, 1, 1, 12)"
        )
    return chemin


def _sql_table(chemin, nom):
    with sqlite3.connect(chemin) as conn:
        return conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (nom,)).fetchone()[0]


def test_ancienne_base_migree_sans_perte(ancienne_base):
    init_database(db_path=ancienne_base)

    assert "sexe IS NULL OR" in _sql_table(ancienne_base, "enseignants")
    with sqlite3.connect(ancienne_base) as conn:
        assert conn.execute(
            "SELECT nom, prenom, sexe, statut, taux_horaire, telephone FROM enseignants"
        ).fetchall() == [("Fouda", "Alain", "M", "V", 1500, "600000000")]
        assert conn.execute("SELECT enseignant_id, heures_effectuees FROM saisies_heures").fetchall() == [(1, 12)]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_fiche_incomplete_acceptee_apres_migration(ancienne_base):
    init_database(db_path=ancienne_base)
    with sqlite3.connect(ancienne_base) as conn:
        conn.execute("INSERT INTO enseignants (nom) VALUES ('Mbarga')")
        assert conn.execute(
            "SELECT prenom, sexe, statut, taux_horaire FROM enseignants WHERE nom = 'Mbarga'"
        ).fetchone() == ("", None, None, None)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO enseignants (nom, sexe) VALUES ('X', 'Z')")  # valeurs toujours contrôlées
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO enseignants (nom, taux_horaire) VALUES ('X', -5)")


def test_liens_et_regles_conserves_apres_migration(ancienne_base):
    init_database(db_path=ancienne_base)
    with sqlite3.connect(ancienne_base) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        noms = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE tbl_name = 'enseignants'")}
        assert {"trg_enseignants_maj_date", "idx_enseignants_actif"} <= noms
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM enseignants WHERE id = 1")  # heures liées : suppression refusée
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO saisies_heures (periode_id, enseignant_id, numero_semaine, heures_effectuees) VALUES (1, 99, 2, 3)")


def test_migration_idempotente(ancienne_base):
    init_database(db_path=ancienne_base)
    with sqlite3.connect(ancienne_base) as conn:
        assert migrations.rendre_fiches_enseignants_completables(conn, SCHEMA_PATH.read_text(encoding="utf-8")) is False
    init_database(db_path=ancienne_base)


def test_base_neuve_deja_au_bon_format(tmp_path):
    chemin = tmp_path / "neuve.db"
    init_database(db_path=chemin)
    assert "sexe IS NULL OR" in _sql_table(chemin, "enseignants")
