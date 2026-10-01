"""
Tests du durcissement de la fondation :
- montants monétaires strictement entiers (FCFA) ;
- immutabilité inconditionnelle des bulletins générés ;
- verrouillage des données sources (heures, primes, retenues) une fois
  la période validée ;
- règles de transition et de figeage des périodes.
"""

import sqlite3

import pytest

from database.connection import get_connection


# ---------------------------------------------------------------------
# Helpers (mêmes conventions que test_database_integrity.py)
# ---------------------------------------------------------------------

def _inserer_enseignant(conn, **overrides):
    data = {
        "nom": "Diop",
        "prenom": "Fatou",
        "sexe": "F",
        "statut": "V",
        "taux_horaire": 100,
    }
    data.update(overrides)
    cur = conn.execute(
        """
        INSERT INTO enseignants (nom, prenom, sexe, statut, taux_horaire, email, telephone, adresse, actif)
        VALUES (:nom, :prenom, :sexe, :statut, :taux_horaire, :email, :telephone, :adresse, :actif)
        """,
        {"email": None, "telephone": None, "adresse": None, "actif": 1, **data},
    )
    conn.commit()
    return cur.lastrowid


def _inserer_periode(conn, mois=3, annee=2027, libelle="Mars 2027"):
    cur = conn.execute(
        "INSERT INTO periodes_paie (mois, annee, libelle) VALUES (?, ?, ?)",
        (mois, annee, libelle),
    )
    conn.commit()
    return cur.lastrowid


_ORDRE_STATUTS = ["brouillon", "ouverte", "validee", "cloturee"]


def _avancer_vers(conn, periode_id, statut_cible):
    """
    Fait avancer une période étape par étape jusqu'au statut cible, en
    respectant la chaîne BROUILLON -> OUVERTE -> VALIDEE -> CLOTUREE
    (idempotent : ne rejoue pas les étapes déjà franchies).
    """
    statut_actuel = conn.execute(
        "SELECT statut FROM periodes_paie WHERE id = ?", (periode_id,)
    ).fetchone()["statut"]
    index_actuel = _ORDRE_STATUTS.index(statut_actuel)
    index_cible = _ORDRE_STATUTS.index(statut_cible)
    for etape in _ORDRE_STATUTS[index_actuel + 1 : index_cible + 1]:
        if etape == "cloturee":
            conn.execute(
                "UPDATE periodes_paie SET statut = ?, date_cloture = datetime('now') WHERE id = ?",
                (etape, periode_id),
            )
        else:
            conn.execute("UPDATE periodes_paie SET statut = ? WHERE id = ?", (etape, periode_id))
        conn.commit()


def _ouvrir_periode(conn, periode_id):
    _avancer_vers(conn, periode_id, "ouverte")


def _valider_periode(conn, periode_id):
    _avancer_vers(conn, periode_id, "validee")


def _cloturer_periode(conn, periode_id):
    _avancer_vers(conn, periode_id, "cloturee")


def _inserer_bulletin(conn, enseignant_id, periode_id, **overrides):
    data = {
        "nom_snapshot": "Diop",
        "prenom_snapshot": "Fatou",
        "sexe_snapshot": "F",
        "statut_snapshot": "V",
        "total_heures": 30,
        "taux_horaire": 100,
        "gain_heures": 3000,
        "prime_ap_pp": 0,
        "surveillance_secretariat": 0,
        "indemnite_suggestion_admin": 0,
        "base_taxable": 3000,
        "taxe_5pct": 150,
        "retenue_amicale": 0,
        "dette": 0,
        "net_a_payer": 2850,
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


# ---------------------------------------------------------------------
# 1. Montants monétaires strictement entiers
# ---------------------------------------------------------------------

def test_element_remuneration_montant_fractionnaire_rejete(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant) "
                "VALUES (?, ?, 'prime_ap_pp', ?)",
                (enseignant_id, periode_id, 100.75),
            )
            conn.commit()


def test_retenue_montant_fractionnaire_rejete(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO retenues (enseignant_id, periode_id, type_retenue, montant) VALUES (?, ?, 'dette', ?)",
                (enseignant_id, periode_id, 25.5),
            )
            conn.commit()


def test_bulletin_montant_fractionnaire_rejete(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_bulletin(conn, enseignant_id, periode_id, net_a_payer=2850.99)


def test_montant_entier_accepte(db_path):
    """Un montant entier (même via un float Python sans décimales, ex: 100.0) reste accepté."""
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        # 100.0 n'a pas de partie fractionnaire réelle : accepté
        conn.execute(
            "INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant) "
            "VALUES (?, ?, 'prime_ap_pp', ?)",
            (enseignant_id, periode_id, 100.0),
        )
        conn.commit()


# ---------------------------------------------------------------------
# 2. Immutabilité inconditionnelle des bulletins générés
# ---------------------------------------------------------------------

def test_bulletin_ne_peut_etre_genere_que_pour_periode_validee(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)  # reste en 'brouillon'
        with pytest.raises(sqlite3.IntegrityError):
            _inserer_bulletin(conn, enseignant_id, periode_id)


def test_bulletin_generation_possible_apres_validation(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        _inserer_bulletin(conn, enseignant_id, periode_id)  # ne doit pas lever d'erreur
        row = conn.execute(
            "SELECT * FROM bulletins_paie WHERE enseignant_id = ? AND periode_id = ?",
            (enseignant_id, periode_id),
        ).fetchone()
        assert row is not None


def test_bulletin_update_bloque(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        _inserer_bulletin(conn, enseignant_id, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE bulletins_paie SET net_a_payer = 9999 WHERE enseignant_id = ? AND periode_id = ?",
                (enseignant_id, periode_id),
            )
            conn.commit()


def test_bulletin_delete_bloque(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        _inserer_bulletin(conn, enseignant_id, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM bulletins_paie WHERE enseignant_id = ? AND periode_id = ?",
                (enseignant_id, periode_id),
            )
            conn.commit()


# ---------------------------------------------------------------------
# 3. Verrouillage des données sources une fois la période validée
# ---------------------------------------------------------------------

def test_saisie_heures_bloquee_apres_validation(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
                "VALUES (?, ?, 1, 10)",
                (enseignant_id, periode_id),
            )
            conn.commit()


def test_saisie_heures_modification_bloquee_apres_validation(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        # Saisie autorisée pendant OUVERTE
        conn.execute(
            "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
            "VALUES (?, ?, 1, 10)",
            (enseignant_id, periode_id),
        )
        conn.commit()

        _valider_periode(conn, periode_id)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE saisies_heures SET heures_effectuees = 20 "
                "WHERE enseignant_id = ? AND periode_id = ? AND numero_semaine = 1",
                (enseignant_id, periode_id),
            )
            conn.commit()


def test_saisie_heures_impossible_avant_ouverture(db_path):
    """La saisie n'est pas autorisée tant que la période est encore en BROUILLON."""
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)  # reste en BROUILLON
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
                "VALUES (?, ?, 1, 10)",
                (enseignant_id, periode_id),
            )
            conn.commit()


def test_correction_heures_possible_pendant_ouverte(db_path):
    """Vérifie explicitement que la correction reste libre tant que la période est OUVERTE."""
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        conn.execute(
            "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
            "VALUES (?, ?, 1, 10)",
            (enseignant_id, periode_id),
        )
        conn.commit()

        # Correction : ne doit lever aucune erreur
        conn.execute(
            "UPDATE saisies_heures SET heures_effectuees = 15 "
            "WHERE enseignant_id = ? AND periode_id = ? AND numero_semaine = 1",
            (enseignant_id, periode_id),
        )
        conn.commit()

        row = conn.execute(
            "SELECT heures_effectuees FROM saisies_heures WHERE enseignant_id = ? AND periode_id = ? AND numero_semaine = 1",
            (enseignant_id, periode_id),
        ).fetchone()
        assert row["heures_effectuees"] == 15


def test_element_remuneration_bloque_apres_validation(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO elements_remuneration (enseignant_id, periode_id, type_element, montant) "
                "VALUES (?, ?, 'prime_ap_pp', ?)",
                (enseignant_id, periode_id, 50),
            )
            conn.commit()


def test_retenue_bloquee_apres_validation(db_path):
    with get_connection(db_path) as conn:
        enseignant_id = _inserer_enseignant(conn)
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO retenues (enseignant_id, periode_id, type_retenue, montant) VALUES (?, ?, 'dette', ?)",
                (enseignant_id, periode_id, 50),
            )
            conn.commit()


# ---------------------------------------------------------------------
# 4. Transitions et figeage des périodes
# ---------------------------------------------------------------------

def test_transition_brouillon_vers_ouverte_autorisee(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)  # ne doit pas lever d'erreur
        row = conn.execute("SELECT statut FROM periodes_paie WHERE id = ?", (periode_id,)).fetchone()
        assert row["statut"] == "ouverte"


def test_transition_ouverte_vers_validee_autorisee(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)  # passe par ouverte puis validee
        row = conn.execute("SELECT statut FROM periodes_paie WHERE id = ?", (periode_id,)).fetchone()
        assert row["statut"] == "validee"


def test_transition_validee_vers_cloturee_autorisee(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        _cloturer_periode(conn, periode_id)  # ne doit pas lever d'erreur
        row = conn.execute("SELECT statut FROM periodes_paie WHERE id = ?", (periode_id,)).fetchone()
        assert row["statut"] == "cloturee"


def test_transition_brouillon_vers_validee_directe_interdite(db_path):
    """Le saut d'étape (sans passer par OUVERTE) doit être rejeté."""
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE periodes_paie SET statut = 'validee' WHERE id = ?", (periode_id,))
            conn.commit()


def test_transition_brouillon_vers_cloturee_interdite(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE periodes_paie SET statut = 'cloturee', date_cloture = datetime('now') WHERE id = ?",
                (periode_id,),
            )
            conn.commit()


def test_transition_ouverte_vers_cloturee_directe_interdite(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE periodes_paie SET statut = 'cloturee', date_cloture = datetime('now') WHERE id = ?",
                (periode_id,),
            )
            conn.commit()


def test_transition_retour_arriere_interdite(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE periodes_paie SET statut = 'brouillon' WHERE id = ?", (periode_id,))
            conn.commit()


def test_transition_retour_ouverte_vers_brouillon_interdite(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _ouvrir_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE periodes_paie SET statut = 'brouillon' WHERE id = ?", (periode_id,))
            conn.commit()


def test_periode_cloturee_totalement_figee(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        _cloturer_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE periodes_paie SET libelle = 'Nouveau libelle' WHERE id = ?", (periode_id,))
            conn.commit()


def test_suppression_periode_non_brouillon_interdite(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        _valider_periode(conn, periode_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM periodes_paie WHERE id = ?", (periode_id,))
            conn.commit()


def test_suppression_periode_brouillon_autorisee(db_path):
    with get_connection(db_path) as conn:
        periode_id = _inserer_periode(conn)
        conn.execute("DELETE FROM periodes_paie WHERE id = ?", (periode_id,))  # ne doit pas lever d'erreur
        conn.commit()
        row = conn.execute("SELECT * FROM periodes_paie WHERE id = ?", (periode_id,)).fetchone()
        assert row is None
