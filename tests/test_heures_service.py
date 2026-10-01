"""
Tests du module 04 : saisie des heures effectuées (service + repository).

Même convention que test_enseignant_service.py / test_periode_service.py :
le fixture `_rediriger_connexion_par_defaut` redirige
database.connection.DB_PATH vers la base temporaire du fixture db_path.
"""

import pytest

import database.connection as database_connection
import database.repositories.heures_repository as heures_repository
from services import enseignant_service, heures_service, periode_service
from services.heures_service import DonneesPaieValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _creer_enseignant(**overrides):
    donnees = {"nom": "Kaba", "prenom": "Alpha", "sexe": "M", "statut": "V", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=6, annee=2026):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


# ---------------------------------------------------------------------
# Heures : validation des valeurs
# ---------------------------------------------------------------------

def test_refus_heure_negative():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: -5})


def test_acceptation_heure_zero():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 0})
    resultat = heures_service.obtenir_heures_enseignant(periode.id, enseignant.id)
    assert resultat[1] == 0.0


def test_acceptation_heure_decimale():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 7.5})
    resultat = heures_service.obtenir_heures_enseignant(periode.id, enseignant.id)
    assert resultat[1] == 7.5


def test_refus_semaine_hors_bornes():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {0: 10})
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {6: 10})


# ---------------------------------------------------------------------
# Périodes : statut requis pour la saisie
# ---------------------------------------------------------------------

def test_saisie_impossible_periode_brouillon():
    enseignant = _creer_enseignant()
    periode = periode_service.creer_periode(mois=7, annee=2026)  # reste en brouillon
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})


def test_saisie_possible_periode_ouverte():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    resultat = heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})
    assert len(resultat) == 1
    assert resultat[0].heures_effectuees == 10


def test_lecture_seule_periode_validee():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})
    periode_service.valider_periode(periode.id)

    # Écriture bloquée...
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 20})

    # ...mais la lecture reste possible et inchangée.
    resultat = heures_service.obtenir_heures_enseignant(periode.id, enseignant.id)
    assert resultat[1] == 10


def test_lecture_seule_periode_cloturee():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})
    periode_service.valider_periode(periode.id)
    periode_service.cloturer_periode(periode.id)

    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 20})

    resultat = heures_service.obtenir_heures_enseignant(periode.id, enseignant.id)
    assert resultat[1] == 10


def test_refus_periode_inexistante():
    enseignant = _creer_enseignant()
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(9999, enseignant.id, {1: 10})


# ---------------------------------------------------------------------
# Enseignants : actif requis pour la saisie
# ---------------------------------------------------------------------

def test_enseignant_actif_accepte():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})  # ne lève rien


def test_enseignant_desactive_refuse_pour_nouvelle_saisie():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    enseignant_service.desactiver_enseignant(enseignant.id)
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})


def test_anciennes_donnees_enseignant_desactive_toujours_consultables():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10, 2: 12})
    enseignant_service.desactiver_enseignant(enseignant.id)

    resultat = heures_service.obtenir_heures_enseignant(periode.id, enseignant.id)
    assert resultat[1] == 10
    assert resultat[2] == 12


def test_refus_enseignant_inexistant():
    periode = _creer_periode_ouverte()
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(periode.id, 9999, {1: 10})


# ---------------------------------------------------------------------
# Doublons / upsert
# ---------------------------------------------------------------------

def test_upsert_ne_cree_pas_de_doublon():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 25})  # même semaine

    lignes = heures_repository.lister_par_enseignant_periode(enseignant.id, periode.id)
    assert len(lignes) == 1
    assert lignes[0].heures_effectuees == 25


def test_saisie_semaines_multiples_sans_doublon():
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(
        periode.id, enseignant.id, {1: 10, 2: 12, 3: 8, 4: 15, 5: 11}
    )
    lignes = heures_repository.lister_par_enseignant_periode(enseignant.id, periode.id)
    assert len(lignes) == 5


# ---------------------------------------------------------------------
# Total dérivé (jamais stocké)
# ---------------------------------------------------------------------

def test_total_heures_calcule_correctement():
    heures = {1: 10, 2: 15, 3: 12, 4: 16, 5: 14}
    assert heures_service.total_heures(heures) == 67


def test_total_heures_absent_de_saisie_heures():
    """Le total n'est jamais une colonne de la table saisies_heures (pas de 2e source de vérité)."""
    enseignant = _creer_enseignant()
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, enseignant.id, {1: 10})
    ligne = heures_repository.lister_par_enseignant_periode(enseignant.id, periode.id)[0]
    assert not hasattr(ligne, "total")
    assert not hasattr(ligne, "total_heures")


# ---------------------------------------------------------------------
# Vue d'ensemble d'une période
# ---------------------------------------------------------------------

def test_lister_heures_periode_plusieurs_enseignants():
    e1 = _creer_enseignant(nom="Kaba", prenom="Alpha")
    e2 = _creer_enseignant(nom="Sy", prenom="Fanta")
    periode = _creer_periode_ouverte()
    heures_service.enregistrer_heures_enseignant(periode.id, e1.id, {1: 10})
    heures_service.enregistrer_heures_enseignant(periode.id, e2.id, {1: 20})

    resultat = heures_service.lister_heures_periode(periode.id)
    assert resultat[e1.id][1] == 10
    assert resultat[e2.id][1] == 20
