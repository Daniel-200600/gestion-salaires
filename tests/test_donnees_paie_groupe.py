"""
Tests du durcissement transactionnel de l'enregistrement groupé
(services/donnees_paie_service.py).

Vérifie que l'ensemble d'un groupe d'enseignants est soit intégralement
enregistré (commit unique), soit intégralement annulé (rollback
complet) en cas d'erreur sur un seul enseignant du groupe — y compris
pour ceux déjà traités avec succès plus tôt dans la boucle.
"""

import sqlite3

import pytest

import database.connection as database_connection
import database.repositories.heures_repository as heures_repository
import database.repositories.remuneration_repository as remuneration_repository
import database.repositories.retenue_repository as retenue_repository
from database.connection import get_connection
from services import enseignant_service, heures_service, periode_service, remuneration_service, retenue_service
from services.donnees_paie_service import DonneesPaieEnseignant, enregistrer_donnees_paie_groupe
from services.heures_service import DonneesPaieValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Sano", "prenom": "Ibrahim", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=4, annee=2027):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


# ---------------------------------------------------------------------
# 1. Enregistrement groupé entièrement réussi
# ---------------------------------------------------------------------

def test_enregistrement_groupe_entierement_reussi():
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    e2 = _creer_enseignant(nom="Keita", prenom="Sekou")
    e3 = _creer_enseignant(nom="Cisse", prenom="Awa")
    periode = _creer_periode_ouverte()

    groupe = [
        DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10, 2: 12}, prime_ap_pp=1000),
        DonneesPaieEnseignant(enseignant_id=e2.id, heures_par_semaine={1: 15}, dette=500),
        DonneesPaieEnseignant(enseignant_id=e3.id, heures_par_semaine={1: 20}, retenue_amicale=200),
    ]

    enregistrer_donnees_paie_groupe(periode.id, groupe)  # ne doit lever aucune exception

    assert heures_service.obtenir_heures_enseignant(periode.id, e1.id)[1] == 10
    assert heures_service.obtenir_heures_enseignant(periode.id, e1.id)[2] == 12
    assert remuneration_service.obtenir_remuneration_enseignant(periode.id, e1.id)["prime_ap_pp"] == 1000
    assert heures_service.obtenir_heures_enseignant(periode.id, e2.id)[1] == 15
    assert retenue_service.obtenir_retenues_enseignant(periode.id, e2.id)["dette"] == 500
    assert heures_service.obtenir_heures_enseignant(periode.id, e3.id)[1] == 20
    assert retenue_service.obtenir_retenues_enseignant(periode.id, e3.id)["retenue_amicale"] == 200


# ---------------------------------------------------------------------
# 2. Échec sur un enseignant au milieu du groupe
# ---------------------------------------------------------------------

def test_echec_enseignant_au_milieu_du_groupe():
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    e2 = _creer_enseignant(nom="Keita", prenom="Sekou")
    e3 = _creer_enseignant(nom="Cisse", prenom="Awa")
    periode = _creer_periode_ouverte()

    groupe = [
        DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10}),
        DonneesPaieEnseignant(enseignant_id=e2.id, heures_par_semaine={1: -5}),  # invalide : négatif
        DonneesPaieEnseignant(enseignant_id=e3.id, heures_par_semaine={1: 20}),
    ]

    with pytest.raises(DonneesPaieValidationError):
        enregistrer_donnees_paie_groupe(periode.id, groupe)


# ---------------------------------------------------------------------
# 3. Le rollback annule aussi les enseignants déjà traités avant l'échec
# ---------------------------------------------------------------------

def test_rollback_annule_enseignants_precedents():
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    e2 = _creer_enseignant(nom="Keita", prenom="Sekou")
    periode = _creer_periode_ouverte()

    groupe = [
        DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10, 2: 12}, prime_ap_pp=3000),
        DonneesPaieEnseignant(enseignant_id=e2.id, heures_par_semaine={1: -1}),  # échoue en dernier
    ]

    with pytest.raises(DonneesPaieValidationError):
        enregistrer_donnees_paie_groupe(periode.id, groupe)

    # e1 était pourtant valide et traité en premier : rien ne doit être resté.
    heures_e1 = heures_service.obtenir_heures_enseignant(periode.id, e1.id)
    assert all(valeur == 0.0 for valeur in heures_e1.values())
    remuneration_e1 = remuneration_service.obtenir_remuneration_enseignant(periode.id, e1.id)
    assert remuneration_e1["prime_ap_pp"] == 0


# ---------------------------------------------------------------------
# 4. Les heures ne restent pas enregistrées seules après un rollback
# ---------------------------------------------------------------------

def test_heures_non_persistees_seules_apres_rollback():
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    e2 = _creer_enseignant(nom="Keita", prenom="Sekou")
    periode = _creer_periode_ouverte()

    groupe = [
        DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10}),
        DonneesPaieEnseignant(enseignant_id=e2.id, heures_par_semaine={7: 5}),  # semaine invalide
    ]

    with pytest.raises(DonneesPaieValidationError):
        enregistrer_donnees_paie_groupe(periode.id, groupe)

    lignes_e1 = heures_repository.lister_par_enseignant_periode(e1.id, periode.id)
    assert lignes_e1 == []


# ---------------------------------------------------------------------
# 5. Les rémunérations ne restent pas enregistrées seules après un rollback
# ---------------------------------------------------------------------

def test_remuneration_non_persistee_seule_apres_rollback():
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    e2 = _creer_enseignant(nom="Keita", prenom="Sekou")
    periode = _creer_periode_ouverte()

    groupe = [
        DonneesPaieEnseignant(enseignant_id=e1.id, prime_ap_pp=2000, surveillance_secretariat=500),
        DonneesPaieEnseignant(enseignant_id=e2.id, prime_ap_pp=-100),  # invalide : négatif
    ]

    with pytest.raises(DonneesPaieValidationError):
        enregistrer_donnees_paie_groupe(periode.id, groupe)

    lignes_e1 = remuneration_repository.lister_par_enseignant_periode(e1.id, periode.id)
    assert lignes_e1 == []


# ---------------------------------------------------------------------
# 6. Les retenues ne restent pas enregistrées seules après un rollback
# ---------------------------------------------------------------------

def test_retenues_non_persistees_seules_apres_rollback():
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    e2 = _creer_enseignant(nom="Keita", prenom="Sekou")
    periode = _creer_periode_ouverte()

    groupe = [
        DonneesPaieEnseignant(enseignant_id=e1.id, retenue_amicale=300, dette=100),
        DonneesPaieEnseignant(enseignant_id=e2.id, dette=250.75),  # invalide : fractionnaire
    ]

    with pytest.raises(DonneesPaieValidationError):
        enregistrer_donnees_paie_groupe(periode.id, groupe)

    lignes_e1 = retenue_repository.lister_par_enseignant_periode(e1.id, periode.id)
    assert lignes_e1 == []


# ---------------------------------------------------------------------
# 7. Une opération réussie fait bien le COMMIT (persistance réelle,
#    vérifiée via une connexion entièrement nouvelle et indépendante)
# ---------------------------------------------------------------------

def test_operation_reussie_est_bien_committee(db_path):
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    periode = _creer_periode_ouverte()

    groupe = [DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 18}, prime_ap_pp=1500)]
    enregistrer_donnees_paie_groupe(periode.id, groupe)

    # Connexion neuve et indépendante, ouverte directement sur le
    # fichier de la base : si les données ne sont visibles que via
    # une lecture sur cette connexion séparée, c'est la preuve que le
    # commit a bien été exécuté (et non simplement resté en mémoire
    # dans la transaction de la connexion d'écriture).
    with get_connection(db_path) as conn_lecture:
        ligne_heures = conn_lecture.execute(
            "SELECT heures_effectuees FROM saisies_heures WHERE enseignant_id = ? AND periode_id = ? AND numero_semaine = 1",
            (e1.id, periode.id),
        ).fetchone()
        ligne_prime = conn_lecture.execute(
            "SELECT montant FROM elements_remuneration WHERE enseignant_id = ? AND periode_id = ? AND type_element = 'prime_ap_pp'",
            (e1.id, periode.id),
        ).fetchone()

    assert ligne_heures is not None and ligne_heures["heures_effectuees"] == 18
    assert ligne_prime is not None and ligne_prime["montant"] == 1500


# ---------------------------------------------------------------------
# 8. Compatibilité avec les upserts existants (pas de doublon, mise à jour)
# ---------------------------------------------------------------------

def test_compatibilite_upsert_pas_de_doublon():
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    periode = _creer_periode_ouverte()

    # Premier enregistrement groupé
    enregistrer_donnees_paie_groupe(
        periode.id,
        [DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10}, prime_ap_pp=1000, dette=200)],
    )
    # Second enregistrement groupé sur les mêmes clés : doit mettre à jour, pas dupliquer
    enregistrer_donnees_paie_groupe(
        periode.id,
        [DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 25}, prime_ap_pp=4000, dette=800)],
    )

    lignes_heures = heures_repository.lister_par_enseignant_periode(e1.id, periode.id)
    lignes_prime = remuneration_repository.lister_par_enseignant_periode(e1.id, periode.id)
    lignes_dette = retenue_repository.lister_par_enseignant_periode(e1.id, periode.id)

    assert len(lignes_heures) == 1 and lignes_heures[0].heures_effectuees == 25
    lignes_prime_filtrees = [l for l in lignes_prime if l.type_element.value == "prime_ap_pp"]
    assert len(lignes_prime_filtrees) == 1 and lignes_prime_filtrees[0].montant == 4000
    lignes_dette_filtrees = [l for l in lignes_dette if l.type_retenue.value == "dette"]
    assert len(lignes_dette_filtrees) == 1 and lignes_dette_filtrees[0].montant == 800


def test_compatibilite_upsert_service_individuel_puis_groupe():
    """Un enregistrement via le service individuel, puis via le groupé, doit continuer à faire un upsert cohérent."""
    e1 = _creer_enseignant(nom="Sano", prenom="Ibrahim")
    periode = _creer_periode_ouverte()

    heures_service.enregistrer_heures_enseignant(periode.id, e1.id, {1: 5})
    enregistrer_donnees_paie_groupe(
        periode.id, [DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 30})]
    )

    lignes = heures_repository.lister_par_enseignant_periode(e1.id, periode.id)
    assert len(lignes) == 1
    assert lignes[0].heures_effectuees == 30


# ---------------------------------------------------------------------
# Cas complémentaires (période introuvable / non ouverte, groupe vide)
# ---------------------------------------------------------------------

def test_refus_periode_inexistante_groupe():
    e1 = _creer_enseignant()
    with pytest.raises(DonneesPaieValidationError):
        enregistrer_donnees_paie_groupe(9999, [DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10})])


def test_refus_periode_non_ouverte_groupe():
    e1 = _creer_enseignant()
    periode = periode_service.creer_periode(mois=5, annee=2027)  # reste en brouillon
    with pytest.raises(DonneesPaieValidationError):
        enregistrer_donnees_paie_groupe(periode.id, [DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10})])


def test_groupe_vide_ne_leve_rien():
    periode = _creer_periode_ouverte()
    enregistrer_donnees_paie_groupe(periode.id, [])  # aucune exception attendue
