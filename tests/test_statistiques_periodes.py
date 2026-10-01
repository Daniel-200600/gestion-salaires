"""
Tests de services/statistiques_service.analyser_periodes (module 17,
section 8) — évolution, variations, robustesse.
"""

import pytest

import database.connection as database_connection
from services import controle_paie_service, donnees_paie_service, enseignant_service, periode_service, statistiques_service
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Kamgang", "prenom": "Jean", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _periode_ouverte(mois, annee=2096):
    p = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(p.id)


def _saisir(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)])


# ---------------------------------------------------------------------
# Première période — pas de variation calculable
# ---------------------------------------------------------------------

def test_premiere_periode_sans_variation():
    e = _creer_enseignant()
    p = _periode_ouverte(1)
    _saisir(p.id, e.id, heures_par_semaine={1: 10})

    points = statistiques_service.analyser_periodes([p.id])
    assert len(points) == 1
    assert points[0].variation_net_absolue is None
    assert points[0].variation_net_pourcentage is None


# ---------------------------------------------------------------------
# Variation absolue et relative
# ---------------------------------------------------------------------

def test_variation_hausse_calculee_correctement():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _periode_ouverte(1)
    p2 = _periode_ouverte(2)
    _saisir(p1.id, e.id, heures_par_semaine={1: 10})   # net = 9500 environ
    _saisir(p2.id, e.id, heures_par_semaine={1: 20})   # net double environ

    points = statistiques_service.analyser_periodes([p1.id, p2.id])
    assert points[1].variation_net_absolue == points[1].total_net - points[0].total_net
    assert points[1].variation_net_pourcentage is not None
    assert points[1].variation_net_pourcentage > 0


def test_variation_baisse_calculee_correctement():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _periode_ouverte(3)
    p2 = _periode_ouverte(4)
    _saisir(p1.id, e.id, heures_par_semaine={1: 20})
    _saisir(p2.id, e.id, heures_par_semaine={1: 5})

    points = statistiques_service.analyser_periodes([p1.id, p2.id])
    assert points[1].variation_net_pourcentage < 0


# ---------------------------------------------------------------------
# Valeur précédente égale à zéro — jamais de division par zéro
# ---------------------------------------------------------------------

def test_periode_precedente_vide_pas_de_division_par_zero():
    e = _creer_enseignant()
    p1 = _periode_ouverte(5)  # aucune saisie -> total_net = 0
    p2 = _periode_ouverte(6)
    _saisir(p2.id, e.id, heures_par_semaine={1: 10})

    points = statistiques_service.analyser_periodes([p1.id, p2.id])
    assert points[0].total_net == 0
    assert points[1].variation_net_absolue == points[1].total_net  # écart brut correct
    assert points[1].variation_net_pourcentage is None  # jamais de division par zéro


# ---------------------------------------------------------------------
# Ordre chronologique garanti, quel que soit l'ordre d'entrée
# ---------------------------------------------------------------------

def test_periodes_triees_chronologiquement():
    e = _creer_enseignant()
    p1 = _periode_ouverte(7)
    p2 = _periode_ouverte(8)
    _saisir(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir(p2.id, e.id, heures_par_semaine={1: 10})

    points = statistiques_service.analyser_periodes([p2.id, p1.id])  # ordre inversé en entrée
    assert points[0].periode.mois == 7
    assert points[1].periode.mois == 8


# ---------------------------------------------------------------------
# Données manquantes — période sans donnée exploitable
# ---------------------------------------------------------------------

def test_periode_sans_donnee_incluse_avec_totaux_a_zero():
    _creer_enseignant()
    p = _periode_ouverte(9)  # aucune saisie
    points = statistiques_service.analyser_periodes([p.id])
    assert len(points) == 1
    assert points[0].nombre_enseignants == 0
    assert points[0].total_net == 0


def test_liste_periodes_vide():
    assert statistiques_service.analyser_periodes([]) == []
