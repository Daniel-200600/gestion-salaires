"""
Tests du module 04 : retenues (retenue amicale, dette) — service + repository.
"""

import pytest

import database.connection as database_connection
import database.repositories.retenue_repository as retenue_repository
from services import enseignant_service, periode_service, retenue_service
from services.heures_service import DonneesPaieValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Toure", "prenom": "Mariam", "sexe": "F", "statut": "V", "taux_horaire": 900}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=6, annee=2026):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


# ---------------------------------------------------------------------
# Montants : validation
# ---------------------------------------------------------------------

def test_refus_montant_negatif():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    with pytest.raises(DonneesPaieValidationError):
        retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=-100)


def test_acceptation_montant_zero():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    resultat = retenue_service.enregistrer_retenues_enseignant(
        periode.id, enseignant.id, retenue_amicale=0, dette=0
    )
    assert resultat["retenue_amicale"] == 0
    assert resultat["dette"] == 0


def test_stockage_entier_fcfa():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    resultat = retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=2500)
    assert resultat["dette"] == 2500
    assert isinstance(resultat["dette"], int)


def test_refus_montant_fractionnaire():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    with pytest.raises(DonneesPaieValidationError):
        retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, retenue_amicale=500.5)


# ---------------------------------------------------------------------
# Périodes
# ---------------------------------------------------------------------

def test_saisie_impossible_periode_brouillon():
    enseignant = _creer_enseignant()
    periode = periode_service.creer_periode(mois=9, annee=2026)
    with pytest.raises(DonneesPaieValidationError):
        retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=100)


def test_lecture_seule_periode_cloturee():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=100)
    periode_service.valider_periode(periode.id)
    periode_service.cloturer_periode(periode.id)

    with pytest.raises(DonneesPaieValidationError):
        retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=200)

    resultat = retenue_service.obtenir_retenues_enseignant(periode.id, enseignant.id)
    assert resultat["dette"] == 100


def test_refus_periode_inexistante():
    enseignant = _creer_enseignant()
    with pytest.raises(DonneesPaieValidationError):
        retenue_service.enregistrer_retenues_enseignant(9999, enseignant.id, dette=100)


# ---------------------------------------------------------------------
# Enseignants
# ---------------------------------------------------------------------

def test_enseignant_desactive_refuse_pour_nouvelle_saisie():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    enseignant_service.desactiver_enseignant(enseignant.id)
    with pytest.raises(DonneesPaieValidationError):
        retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=100)


def test_anciennes_donnees_enseignant_desactive_consultables():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, retenue_amicale=750)
    enseignant_service.desactiver_enseignant(enseignant.id)

    resultat = retenue_service.obtenir_retenues_enseignant(periode.id, enseignant.id)
    assert resultat["retenue_amicale"] == 750


# ---------------------------------------------------------------------
# Doublons / upsert / unicité par type
# ---------------------------------------------------------------------

def test_upsert_ne_cree_pas_de_doublon():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=100)
    retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, dette=350)

    lignes = retenue_repository.lister_par_enseignant_periode(enseignant.id, periode.id)
    lignes_dette = [l for l in lignes if l.type_retenue.value == "dette"]
    assert len(lignes_dette) == 1
    assert lignes_dette[0].montant == 350


def test_deux_types_distincts_coexistent():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    retenue_service.enregistrer_retenues_enseignant(periode.id, enseignant.id, retenue_amicale=200, dette=800)
    lignes = retenue_repository.lister_par_enseignant_periode(enseignant.id, periode.id)
    assert len(lignes) == 2
