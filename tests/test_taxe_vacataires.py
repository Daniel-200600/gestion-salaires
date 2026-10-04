"""
Taxe de 5,5 % appliquée aux vacataires uniquement ; aucune taxe pour les
permanents. Les périodes validées ou clôturées sous l'ancienne règle
(taxe pour tous) gardent leurs montants à l'identique.
"""

import sqlite3
from decimal import Decimal

import pytest

import database.connection as database_connection
from config.settings import SCHEMA_PATH, TAUX_TAXE
from database import migrations
from database.initialization import init_database
from database.repositories import periode_repository
from services import donnees_paie_service, enseignant_service, paie_service, periode_service
from services.donnees_paie_service import DonneesPaieEnseignant
from utils.formatters import formater_taxe_periode


@pytest.fixture(autouse=True)
def _base(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _periode_ouverte(mois=7, annee=2026):
    return periode_service.ouvrir_periode(periode_service.creer_periode(mois=mois, annee=annee).id)


def _enseignant(statut, nom="Ngono"):
    return enseignant_service.creer_enseignant(nom=nom, prenom="Marie", sexe="F", statut=statut, taux_horaire=1800)


def _paie(periode, enseignant, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode.id, [DonneesPaieEnseignant(enseignant_id=enseignant.id, heures_par_semaine={1: 10}, **kwargs)]
    )
    return paie_service.calculer_paie_enseignant(periode.id, enseignant.id)


def test_taux_par_defaut_5_5_pourcent():
    assert TAUX_TAXE == Decimal("0.055")
    periode = _periode_ouverte()
    assert periode.taux_taxe == Decimal("0.055") and periode.taxe_permanents is False
    assert formater_taxe_periode(periode) == "5,5 %, vacataires"


def test_vacataire_taxe_a_5_5_pourcent():
    resultat = _paie(_periode_ouverte(), _enseignant("V"), retenue_amicale=1000)
    assert (resultat.gain_heures, resultat.taxe_5, resultat.net_a_percevoir) == (18000, 990, 16010)
    assert resultat.taux_taxe == Decimal("0.055")


def test_permanent_sans_taxe():
    resultat = _paie(_periode_ouverte(), _enseignant("P"), prime_ap_pp=2000, retenue_amicale=1000)
    assert (resultat.base_taxable, resultat.taxe_5, resultat.net_a_percevoir) == (20000, 0, 19000)
    assert resultat.taux_taxe == 0


def test_totaux_de_periode_ne_comptent_que_la_taxe_des_vacataires():
    periode = _periode_ouverte()
    vacataire, permanent = _enseignant("V", "AAA"), _enseignant("P", "BBB")
    _paie(periode, vacataire)
    _paie(periode, permanent)
    groupe = paie_service.calculer_paie_groupe(periode.id, [vacataire.id, permanent.id])
    assert paie_service.calculer_totaux_groupe(groupe.resultats).total_taxe == 990


def test_changement_de_statut_change_la_taxe_tant_que_la_periode_est_ouverte():
    periode = _periode_ouverte()
    enseignant = _enseignant("V")
    assert _paie(periode, enseignant).taxe_5 == 990
    enseignant_service.changer_statut_enseignant(enseignant.id, "P")
    assert paie_service.calculer_paie_enseignant(periode.id, enseignant.id).taxe_5 == 0


def test_ancienne_regle_conservee_pour_une_periode_qui_l_utilisait(db_path):
    periode = _periode_ouverte()
    with sqlite3.connect(db_path) as conn:  # période calculée avant la version 1.6.0
        conn.execute("UPDATE periodes_paie SET taxe_permanents = 1 WHERE id = ?", (periode.id,))
    resultat = _paie(periode, _enseignant("P"))
    assert resultat.taxe_5 == 990
    assert formater_taxe_periode(periode_repository.obtenir_par_id(periode.id)) == "5,5 %, tous les enseignants"


def test_regle_figee_apres_validation(db_path):
    periode = _periode_ouverte()
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE periodes_paie SET statut = 'validee' WHERE id = ?", (periode.id,))
        with pytest.raises(sqlite3.IntegrityError, match="Regle de taxe figee"):
            conn.execute("UPDATE periodes_paie SET taxe_permanents = 1 WHERE id = ?", (periode.id,))


def test_migration_garde_l_ancienne_regle_pour_les_periodes_validees_et_cloturees(tmp_path):
    chemin = tmp_path / "ancienne.db"
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    debut_colonne = schema.index("    -- Règle de taxe : la taxe ne s'applique qu'aux vacataires")
    fin_colonne = schema.index("    UNIQUE (mois, annee),")
    ancien_schema = schema[:debut_colonne] + schema[fin_colonne:]
    debut = ancien_schema.index("-- La règle de taxe d'une période validée")
    fin = ancien_schema.index("-- Seule une période encore en brouillon")
    ancien_schema = ancien_schema[:debut] + ancien_schema[fin:]
    assert "taxe_permanents" not in ancien_schema

    conn = sqlite3.connect(chemin)
    conn.executescript(ancien_schema)
    for mois, statut, cloture in ((1, "cloturee", "2026-02-01"), (2, "validee", None),
                                  (3, "ouverte", None), (4, "brouillon", None)):
        conn.execute(
            "INSERT INTO periodes_paie (mois, annee, libelle, statut, date_cloture, taux_taxe) "
            "VALUES (?, 2026, ?, ?, ?, '0.05')", (mois, f"P{mois}", statut, cloture),
        )
    conn.commit()
    conn.close()

    init_database(db_path=chemin)
    init_database(db_path=chemin)  # idempotent

    conn = sqlite3.connect(chemin)
    regles = dict(conn.execute("SELECT mois, taxe_permanents FROM periodes_paie").fetchall())
    taux = {l[0] for l in conn.execute("SELECT taux_taxe FROM periodes_paie")}
    declencheurs = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert regles == {1: 1, 2: 1, 3: 0, 4: 0}
    assert taux == {"0.05"}  # les taux existants ne sont jamais modifiés
    assert "trg_periodes_paie_regle_taxe_figee" in declencheurs
    assert migrations.ajouter_colonnes_manquantes(conn) == []
    conn.close()

    # Une période créée après la migration suit la nouvelle règle.
    nouvelle = periode_service.creer_periode(mois=5, annee=2026, db_path=chemin)
    assert nouvelle.taxe_permanents is False
