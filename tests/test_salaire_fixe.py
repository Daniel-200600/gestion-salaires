"""Salaire mensuel fixe des permanents : remplace heures × taux horaire."""

import sqlite3

import pytest

import database.connection as database_connection
from database.repositories import enseignant_repository
from models.enseignant import Enseignant
from models.enums import Sexe, StatutEnseignant
from services import bulletin_service, controle_paie_service, enseignant_service, paie_service, periode_service
from services import donnees_paie_service
from services.donnees_paie_service import DonneesPaieEnseignant
from utils.validators import EnseignantValidationError


@pytest.fixture(autouse=True)
def _base(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _periode():
    return periode_service.ouvrir_periode(periode_service.creer_periode(mois=9, annee=2026).id)


def _paie(periode, enseignant, heures=None, **montants):
    donnees_paie_service.enregistrer_donnees_paie_groupe(periode.id, [DonneesPaieEnseignant(
        enseignant_id=enseignant.id, heures_par_semaine=heures or {1: 5, 2: 6}, **montants)])
    return paie_service.calculer_paie_enseignant(periode.id, enseignant.id)


def test_permanent_au_salaire_fixe_sans_taux_horaire():
    e = enseignant_service.creer_enseignant("ESSOMBA", "Jean", "M", "P", None, salaire_fixe=150000)
    assert e.est_complet and e.remuneration_fixe and e.taux_horaire is None
    r = _paie(_periode(), e, indemnite_suggestion_admin=5000, retenue_amicale=5000)
    assert (r.total_heures, r.gain_heures, r.taxe_5, r.net_a_percevoir) == (11, 150000, 0, 150000)
    assert r.salaire_fixe == 150000 and r.taux_horaire == 0


def test_heures_et_taux_ignores_quand_le_salaire_est_fixe():
    e = enseignant_service.creer_enseignant("ESSOMBA", "Jean", "M", "P", 2000, salaire_fixe=120000)
    assert _paie(_periode(), e, heures={1: 40}).gain_heures == 120000


def test_salaire_fixe_reserve_aux_permanents():
    with pytest.raises(EnseignantValidationError, match="réservé aux permanents"):
        enseignant_service.creer_enseignant("BELLA", "Christine", "F", "V", 1800, salaire_fixe=100000)
    with pytest.raises(EnseignantValidationError, match="taux horaire est obligatoire"):
        enseignant_service.creer_enseignant("BELLA", "Christine", "F", "V", None)


def test_vacataire_ignore_un_ancien_salaire_fixe():
    # Fiche passée de permanent à vacataire : le salaire fixe reste enregistré mais ne s'applique plus.
    eid = enseignant_repository.creer(Enseignant(nom="OWONA", prenom="Luc", sexe=Sexe.HOMME,
                                                 statut=StatutEnseignant.VACATAIRE, taux_horaire=1000,
                                                 salaire_fixe=90000))
    r = _paie(_periode(), enseignant_service.obtenir_enseignant(eid), heures={1: 10})
    assert (r.gain_heures, r.taxe_5) == (10000, 550)


def test_permanent_sans_taux_ni_salaire_est_a_completer():
    e = Enseignant(nom="X", statut=StatutEnseignant.PERMANENT, sexe=Sexe.HOMME)
    assert e.champs_manquants == ["taux horaire ou salaire fixe"]
    assert not Enseignant(nom="X", statut=StatutEnseignant.VACATAIRE, sexe=Sexe.HOMME, salaire_fixe=1).est_complet


def test_modifier_ou_retirer_le_salaire_fixe():
    e = enseignant_service.creer_enseignant("ESSOMBA", "Jean", "M", "P", 2000)
    e = enseignant_service.modifier_enseignant(e.id, e.nom, e.prenom, "M", "P", None, salaire_fixe=130000)
    assert e.salaire_fixe == 130000
    e = enseignant_service.modifier_enseignant(e.id, e.nom, e.prenom, "M", "P", None)  # inchangé par défaut
    assert e.salaire_fixe == 130000
    e = enseignant_service.modifier_enseignant(e.id, e.nom, e.prenom, "M", "P", None, salaire_fixe=None)
    assert e.salaire_fixe is None and e.taux_horaire == 2000


def test_completer_en_lot_avec_un_salaire_fixe():
    eid = enseignant_repository.creer(Enseignant(nom="NGONO", prenom="Marie", sexe=Sexe.FEMME,
                                                 statut=StatutEnseignant.PERMANENT))
    resultat = enseignant_service.completer_fiches_en_lot(
        [enseignant_service.ComplementFiche(eid, salaire_fixe=110000)])
    assert resultat.nb_fiches_completees == 1
    assert enseignant_service.obtenir_enseignant(eid).salaire_fixe == 110000


def test_controle_et_bulletin_sans_taux_horaire():
    e = enseignant_service.creer_enseignant("ESSOMBA", "Jean", "M", "P", None, salaire_fixe=150000)
    periode = _periode()
    r = _paie(periode, e)
    assert not [a for a in controle_paie_service._controler_resultat(r) if a.code == "TAUX_INVALIDE"]
    valeurs = bulletin_service._preparer_valeurs_placeholder(r, periode)
    assert valeurs["{{TAUX_HORAIRE}}"] == "" and valeurs["{{GAIN_HEURES}}"] == "150000"


def test_colonne_ajoutee_aux_bases_existantes(tmp_path):
    from database.initialization import init_database

    chemin = tmp_path / "ancienne.db"
    init_database(db_path=chemin)
    conn = sqlite3.connect(chemin)
    conn.execute("ALTER TABLE enseignants DROP COLUMN salaire_fixe")
    conn.commit()
    conn.close()
    init_database(db_path=chemin)
    conn = sqlite3.connect(chemin)
    assert "salaire_fixe" in [ligne[1] for ligne in conn.execute("PRAGMA table_info(enseignants)")]
    conn.close()
