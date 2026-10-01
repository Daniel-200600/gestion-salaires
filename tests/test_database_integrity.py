"""
Tests de création et d'intégrité de la base de données.

Ces tests vérifient que le schéma SQL est correctement créé et que
toutes les contraintes (UNIQUE, CHECK, clés étrangères) sont bien
appliquées par SQLite.
"""

import sqlite3

import pytest

from database.connection import get_connection
from database.initialization import get_table_names, init_database


TABLES_ATTENDUES = {
    "enseignants",
    "periodes_paie",
    "saisies_heures",
    "elements_remuneration",
    "retenues",
    "bulletins_paie",
    "audit_log",
}


# ---------------------------------------------------------------------
# Création de la base
# ---------------------------------------------------------------------

def test_creation_toutes_les_tables(db_path):
    tables = set(get_table_names(db_path))
    assert TABLES_ATTENDUES.issubset(tables)


def test_initialisation_idempotente(db_path):
    # Ré-appeler init_database ne doit pas lever d'erreur (IF NOT EXISTS)
    init_database(db_path=db_path)
    tables = set(get_table_names(db_path))
    assert TABLES_ATTENDUES.issubset(tables)


def test_foreign_keys_actives(db_path):
    with get_connection(db_path) as conn:
        result = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert result == 1


# ---------------------------------------------------------------------
# Table enseignants
# ---------------------------------------------------------------------

def _inserer_enseignant(conn, **overrides):
    data = {
        "nom": "Ali",
        "prenom": "Karim",
        "sexe": "M",
        "statut": "P",
        "taux_horaire": 150.0,
    }
    data.update(overrides)
    cur = conn.execute(
        """
        INSERT INTO enseignants (nom, prenom, sexe, statut, taux_horaire, email, telephone, adresse, actif)
        VALUES (:nom, :prenom, :sexe, :statut, :taux_horaire, :email, :telephone, :adresse, :actif)
        """,
        {
            "email": None,
            "telephone": None,
            "adresse": None,
            "actif": 1,
            **data,
        },
    )
    conn.commit()
    return cur.lastrowid


def test_insertion_enseignant_minimal(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        row = conn.execute("SELECT * FROM enseignants WHERE id = ?", (enseignant_id,)).fetchone()
        assert row["nom"] == "Ali"
        assert row["date_creation"] is not None
        assert row["date_modification"] is not None


def test_champs_optionnels_nullables(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        row = conn.execute("SELECT * FROM enseignants WHERE id = ?", (enseignant_id,)).fetchone()
        assert row["email"] is None
        assert row["telephone"] is None
        assert row["adresse"] is None


@pytest.mark.parametrize("sexe_invalide", ["X", "m", "", "Homme"])
def test_sexe_invalide_rejete(db_path, sexe_invalide):
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_enseignant(conn, sexe=sexe_invalide)


@pytest.mark.parametrize("statut_invalide", ["X", "v", "Vacataire", ""])
def test_statut_enseignant_invalide_rejete(db_path, statut_invalide):
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_enseignant(conn, statut=statut_invalide)


def test_taux_horaire_negatif_rejete(db_path):
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_enseignant(conn, taux_horaire=-10)


def test_taux_horaire_fractionnaire_rejete(db_path):
    """Les montants monétaires sont des FCFA entiers : aucune fraction autorisée."""
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_enseignant(conn, taux_horaire=150.5)


def test_trigger_date_modification_mise_a_jour(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        avant = conn.execute(
            "SELECT date_creation, date_modification FROM enseignants WHERE id = ?", (enseignant_id,)
        ).fetchone()

        conn.execute("UPDATE enseignants SET taux_horaire = 200 WHERE id = ?", (enseignant_id,))
        conn.commit()

        apres = conn.execute(
            "SELECT date_creation, date_modification FROM enseignants WHERE id = ?", (enseignant_id,)
        ).fetchone()

        assert apres["date_creation"] == avant["date_creation"]
        assert apres["date_modification"] is not None


# ---------------------------------------------------------------------
# Table periodes_paie
# ---------------------------------------------------------------------

def _inserer_periode(conn, mois=10, annee=2026, libelle="Octobre 2026"):
    cur = conn.execute(
        "INSERT INTO periodes_paie (mois, annee, libelle) VALUES (?, ?, ?)",
        (mois, annee, libelle),
    )
    conn.commit()
    return cur.lastrowid


def test_insertion_periode_valide(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        row = conn.execute("SELECT * FROM periodes_paie WHERE id = ?", (periode_id,)).fetchone()
        assert row["statut"] == "brouillon"


def test_periode_mois_annee_dupliques_rejetes(db_path):
    with get_connection(db_path) as conn:
        _inserer_periode(conn, mois=10, annee=2026)
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_periode(conn, mois=10, annee=2026, libelle="Doublon")


def test_periode_mois_hors_limites_rejete(db_path):
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_periode(conn, mois=13)


def _ouvrir_periode(conn, periode_id):
    conn.execute("UPDATE periodes_paie SET statut = 'ouverte' WHERE id = ?", (periode_id,))
    conn.commit()


def _valider_periode(conn, periode_id):
    _ouvrir_periode(conn, periode_id)
    conn.execute("UPDATE periodes_paie SET statut = 'validee' WHERE id = ?", (periode_id,))
    conn.commit()


def test_periode_meme_annee_mois_different_autorise(db_path):
    with get_connection(db_path) as conn:
        _inserer_periode(conn, mois=10, annee=2026)
        # Ne doit pas lever d'exception
        _inserer_periode(conn, mois=11, annee=2026, libelle="Novembre 2026")


# ---------------------------------------------------------------------
# Table saisies_heures
# ---------------------------------------------------------------------

def test_saisie_heures_valide(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        conn.execute(
            "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
            "VALUES (?, ?, ?, ?)",
            (enseignant_id, periode_id, 1, 12.5),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM saisies_heures WHERE enseignant_id = ? AND periode_id = ?",
            (enseignant_id, periode_id),
        ).fetchone()
        assert row["heures_effectuees"] == 12.5


@pytest.mark.parametrize("semaine_invalide", [0, 6, -1])
def test_saisie_heures_semaine_hors_limites_rejetee(db_path, semaine_invalide):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
                "VALUES (?, ?, ?, ?)",
                (enseignant_id, periode_id, semaine_invalide, 10),
            )
            conn.commit()


def test_saisie_heures_doublon_semaine_rejete(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        conn.execute(
            "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
            "VALUES (?, ?, ?, ?)",
            (enseignant_id, periode_id, 1, 10),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
                "VALUES (?, ?, ?, ?)",
                (enseignant_id, periode_id, 1, 5),
            )
            conn.commit()


def test_saisie_heures_enseignant_inexistant_rejetee(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
                "VALUES (?, ?, ?, ?)",
                (9999, periode_id, 1, 10),
            )
            conn.commit()


def test_suppression_enseignant_avec_heures_bloquee(db_path):
    """Un enseignant référencé par des données de paie ne doit pas être supprimable (ON DELETE RESTRICT)."""
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        conn.execute(
            "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
            "VALUES (?, ?, ?, ?)",
            (enseignant_id, periode_id, 1, 10),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM enseignants WHERE id = ?", (enseignant_id,))
            conn.commit()


# ---------------------------------------------------------------------
# Table elements_remuneration
# ---------------------------------------------------------------------

def test_element_remuneration_trois_types_par_enseignant_periode(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        for type_element in ("prime_ap_pp", "surveillance_secretariat", "indemnite_suggestion_admin"):
            conn.execute(
                "INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant) "
                "VALUES (?, ?, ?, ?)",
                (enseignant_id, periode_id, type_element, 100),
            )
        conn.commit()
        rows = conn.execute(
            "SELECT type_element FROM elements_remuneration WHERE enseignant_id = ? AND periode_id = ?",
            (enseignant_id, periode_id),
        ).fetchall()
        assert {r["type_element"] for r in rows} == {
            "prime_ap_pp",
            "surveillance_secretariat",
            "indemnite_suggestion_admin",
        }


def test_element_remuneration_type_invalide_rejete(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant) "
                "VALUES (?, ?, ?, ?)",
                (enseignant_id, periode_id, "type_inconnu", 100),
            )
            conn.commit()


def test_element_remuneration_doublon_type_rejete(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        conn.execute(
            "INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant) "
            "VALUES (?, ?, 'prime_ap_pp', ?)",
            (enseignant_id, periode_id, 100),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant) "
                "VALUES (?, ?, 'prime_ap_pp', ?)",
                (enseignant_id, periode_id, 50),
            )
            conn.commit()


# ---------------------------------------------------------------------
# Table retenues
# ---------------------------------------------------------------------

def test_retenue_amicale_et_dette_separees(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        conn.execute(
            "INSERT INTO retenues (enseignant_id, periode_id, type_retenue, montant) VALUES (?, ?, 'retenue_amicale', ?)",
            (enseignant_id, periode_id, 20),
        )
        conn.execute(
            "INSERT INTO retenues (enseignant_id, periode_id, type_retenue, montant) VALUES (?, ?, 'dette', ?)",
            (enseignant_id, periode_id, 75),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT type_retenue, montant FROM retenues WHERE enseignant_id = ? AND periode_id = ? ORDER BY type_retenue",
            (enseignant_id, periode_id),
        ).fetchall()
        assert len(rows) == 2


def test_retenue_type_invalide_rejete(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO retenues (enseignant_id, periode_id, type_retenue, montant) VALUES (?, ?, 'autre', ?)",
                (enseignant_id, periode_id, 10),
            )
            conn.commit()


# ---------------------------------------------------------------------
# Table bulletins_paie
# ---------------------------------------------------------------------

def _inserer_bulletin(conn, enseignant_id, periode_id, **overrides):
    data = {
        "nom_snapshot": "Ali",
        "prenom_snapshot": "Karim",
        "sexe_snapshot": "M",
        "statut_snapshot": "P",
        "total_heures": 40,
        "taux_horaire": 150,
        "gain_heures": 6000,
        "prime_ap_pp": 200,
        "surveillance_secretariat": 100,
        "indemnite_suggestion_admin": 50,
        "base_taxable": 6350,
        "taxe_5pct": 318,
        "retenue_amicale": 20,
        "dette": 0,
        "net_a_payer": 6012,
    }
    data.update(overrides)
    conn.execute(
        """
        INSERT INTO bulletins_paie (
            enseignant_id, periode_id, nom_snapshot, prenom_snapshot, sexe_snapshot, statut_snapshot,
            total_heures, taux_horaire, gain_heures, prime_ap_pp, surveillance_secretariat,
            indemnite_suggestion_admin, base_taxable, taxe_5pct, retenue_amicale, dette, net_a_payer
        ) VALUES (
            :enseignant_id, :periode_id, :nom_snapshot, :prenom_snapshot, :sexe_snapshot, :statut_snapshot,
            :total_heures, :taux_horaire, :gain_heures, :prime_ap_pp, :surveillance_secretariat,
            :indemnite_suggestion_admin, :base_taxable, :taxe_5pct, :retenue_amicale, :dette, :net_a_payer
        )
        """,
        {"enseignant_id": enseignant_id, "periode_id": periode_id, **data},
    )
    conn.commit()


def test_bulletin_paie_unique_par_enseignant_periode(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        _inserer_bulletin(conn, enseignant_id, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_bulletin(conn, enseignant_id, periode_id)


def test_bulletin_paie_snapshot_independant_de_lenseignant(db_path):
    """
    Vérifie le principe clé : modifier l'enseignant après coup ne doit
    PAS changer le bulletin déjà généré (snapshot immuable).
    """
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn, taux_horaire=150)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        _inserer_bulletin(conn, enseignant_id, periode_id, taux_horaire=150)

        # On change le taux horaire courant de l'enseignant
        conn.execute("UPDATE enseignants SET taux_horaire = 300 WHERE id = ?", (enseignant_id,))
        conn.commit()

        bulletin = conn.execute(
            "SELECT taux_horaire FROM bulletins_paie WHERE enseignant_id = ? AND periode_id = ?",
            (enseignant_id, periode_id),
        ).fetchone()
        enseignant = conn.execute(
            "SELECT taux_horaire FROM enseignants WHERE id = ?", (enseignant_id,)
        ).fetchone()

        assert bulletin["taux_horaire"] == 150
        assert enseignant["taux_horaire"] == 300


# ---------------------------------------------------------------------
# Table audit_log
# ---------------------------------------------------------------------

def test_audit_log_insertion_valide(db_path):
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO audit_log (type_action, entite, entite_id, utilisateur, details) "
            "VALUES (?, ?, ?, ?, ?)",
            ("creation", "enseignant", 1, "admin", "Création enseignant test"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM audit_log").fetchone()
        assert row["type_action"] == "creation"


def test_audit_log_type_action_invalide_rejete(db_path):
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO audit_log (type_action) VALUES (?)",
                ("action_inconnue",),
            )
            conn.commit()
