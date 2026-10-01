"""
Tests du module 04 : éléments de rémunération (service + repository).
"""

import pytest

import database.connection as database_connection
import database.repositories.remuneration_repository as remuneration_repository
from services import enseignant_service, periode_service, remuneration_service
from services.heures_service import DonneesPaieValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Diakite", "prenom": "Oumar", "sexe": "M", "statut": "P", "taux_horaire": 1200}
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
        remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=-500)


def test_acceptation_montant_zero():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    resultat = remuneration_service.enregistrer_remuneration_enseignant(
        periode.id, enseignant.id, prime_ap_pp=0, surveillance_secretariat=0, indemnite_suggestion_admin=0
    )
    assert resultat["prime_ap_pp"] == 0
    assert resultat["surveillance_secretariat"] == 0
    assert resultat["indemnite_suggestion_admin"] == 0


def test_stockage_entier_fcfa():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    resultat = remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=5000)
    assert resultat["prime_ap_pp"] == 5000
    assert isinstance(resultat["prime_ap_pp"], int)


def test_refus_montant_fractionnaire():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    with pytest.raises(DonneesPaieValidationError):
        remuneration_service.enregistrer_remuneration_enseignant(
            periode.id, enseignant.id, surveillance_secretariat=1500.75
        )


# ---------------------------------------------------------------------
# Périodes
# ---------------------------------------------------------------------

def test_saisie_impossible_periode_brouillon():
    enseignant = _creer_enseignant()
    periode = periode_service.creer_periode(mois=8, annee=2026)
    with pytest.raises(DonneesPaieValidationError):
        remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=1000)


def test_lecture_seule_periode_validee():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=1000)
    periode_service.valider_periode(periode.id)

    with pytest.raises(DonneesPaieValidationError):
        remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=2000)

    resultat = remuneration_service.obtenir_remuneration_enseignant(periode.id, enseignant.id)
    assert resultat["prime_ap_pp"] == 1000


def test_refus_periode_inexistante():
    enseignant = _creer_enseignant()
    with pytest.raises(DonneesPaieValidationError):
        remuneration_service.enregistrer_remuneration_enseignant(9999, enseignant.id, prime_ap_pp=1000)


# ---------------------------------------------------------------------
# Enseignants
# ---------------------------------------------------------------------

def test_enseignant_desactive_refuse_pour_nouvelle_saisie():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    enseignant_service.desactiver_enseignant(enseignant.id)
    with pytest.raises(DonneesPaieValidationError):
        remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=1000)


def test_anciennes_donnees_enseignant_desactive_consultables():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=3000)
    enseignant_service.desactiver_enseignant(enseignant.id)

    resultat = remuneration_service.obtenir_remuneration_enseignant(periode.id, enseignant.id)
    assert resultat["prime_ap_pp"] == 3000


# ---------------------------------------------------------------------
# Doublons / upsert / unicité par type
# ---------------------------------------------------------------------

def test_upsert_ne_cree_pas_de_doublon():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=1000)
    remuneration_service.enregistrer_remuneration_enseignant(periode.id, enseignant.id, prime_ap_pp=4000)

    lignes = remuneration_repository.lister_par_enseignant_periode(enseignant.id, periode.id)
    lignes_prime = [l for l in lignes if l.type_element.value == "prime_ap_pp"]
    assert len(lignes_prime) == 1
    assert lignes_prime[0].montant == 4000


def test_trois_types_distincts_coexistent():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    remuneration_service.enregistrer_remuneration_enseignant(
        periode.id, enseignant.id,
        prime_ap_pp=1000, surveillance_secretariat=2000, indemnite_suggestion_admin=3000,
    )
    lignes = remuneration_repository.lister_par_enseignant_periode(enseignant.id, periode.id)
    assert len(lignes) == 3


def test_lister_remuneration_periode_plusieurs_enseignants():
    e1 = _creer_enseignant(nom="Diakite", prenom="Oumar")
    e2 = _creer_enseignant(nom="Coulibaly", prenom="Aissata")
    periode = _creer_periode_ouverte()
    remuneration_service.enregistrer_remuneration_enseignant(periode.id, e1.id, prime_ap_pp=1000)
    remuneration_service.enregistrer_remuneration_enseignant(periode.id, e2.id, prime_ap_pp=2000)

    resultat = remuneration_service.lister_remuneration_periode(periode.id)
    assert resultat[e1.id]["prime_ap_pp"] == 1000
    assert resultat[e2.id]["prime_ap_pp"] == 2000
