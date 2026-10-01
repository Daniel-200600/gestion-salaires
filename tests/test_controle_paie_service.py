"""
Tests de services/controle_paie_service.py (module 09) :
- détection d'anomalies (erreurs bloquantes / avertissements) ;
- workflow complet de validation avec contrôle ;
- workflow complet de clôture avec contrôle ;
- statistiques descriptives ;
- non-régression du cas de référence du moteur de paie.
"""

import inspect
import sqlite3

import pytest

import database.connection as database_connection
from database.connection import get_connection
from database.repositories import periode_repository
from models.enums import Sexe, StatutEnseignant
from models.resultat_paie import ResultatPaie
from services import controle_paie_service, donnees_paie_service, enseignant_service, periode_service
from services.controle_paie_service import (
    ControlePaieError,
    NiveauAnomalie,
    cloturer_periode_avec_controle,
    controler_periode,
    statistiques_net,
    valider_periode_avec_controle,
)
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Ondoa", "prenom": "Serge", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=1, annee=2040):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


def _resultat_factice(**overrides):
    """Construit un ResultatPaie directement, pour tester des scénarios normalement impossibles via la saisie réelle."""
    donnees = dict(
        enseignant_id=1, periode_id=1, nom="Test", prenom="Factice",
        sexe=Sexe.HOMME, statut=StatutEnseignant.PERMANENT, taux_horaire=1000,
        semaine_1=10.0, semaine_2=0.0, semaine_3=0.0, semaine_4=0.0, semaine_5=0.0, total_heures=10.0,
        gain_heures=10000, prime_ap_pp=0, surveillance_secretariat=0, indemnite_suggestion_admin=0,
        base_taxable=10000, taxe_5=500, retenue_amicale=0, dette=0, net_a_percevoir=9500,
    )
    donnees.update(overrides)
    return ResultatPaie(**donnees)


# ---------------------------------------------------------------------
# Contrôle : données valides
# ---------------------------------------------------------------------

def test_controle_donnees_valides_cas_reference():
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    rapport = controler_periode(p.id)
    assert rapport.erreurs == []
    assert not rapport.est_bloque
    assert rapport.nombre_enseignants == 1
    assert rapport.nombre_conformes == 1


# ---------------------------------------------------------------------
# Contrôle : période vide / données manquantes
# ---------------------------------------------------------------------

def test_controle_periode_sans_donnees():
    p = _creer_periode_ouverte()
    rapport = controler_periode(p.id)
    assert rapport.nombre_enseignants == 0
    assert not rapport.est_bloque  # avertissement seulement, pas bloquant
    assert len(rapport.avertissements) == 1
    assert rapport.avertissements[0].code == "PERIODE_VIDE"


def test_controle_periode_inexistante():
    from services.periode_service import PeriodeNotFoundError
    with pytest.raises(PeriodeNotFoundError):
        controler_periode(9999)


# ---------------------------------------------------------------------
# Contrôle : enseignant non calculable (sélection explicite invalide)
# ---------------------------------------------------------------------

def test_controle_enseignant_inexistant_dans_selection():
    p = _creer_periode_ouverte()
    rapport = controler_periode(p.id, enseignant_ids=[9999])
    assert rapport.est_bloque
    assert any(a.code == "ENSEIGNANT_NON_CALCULABLE" for a in rapport.erreurs)


# ---------------------------------------------------------------------
# Contrôle : heures négatives (scénario impossible via la saisie réelle,
# testé via construction directe d'un ResultatPaie)
# ---------------------------------------------------------------------

def test_controle_heures_negatives_detectees():
    resultat = _resultat_factice(semaine_1=-5.0, total_heures=-5.0)
    anomalies = controle_paie_service._controler_heures(resultat)
    codes = [a.code for a in anomalies]
    assert "HEURE_NEGATIVE" in codes
    assert all(a.niveau == NiveauAnomalie.ERREUR for a in anomalies if a.code == "HEURE_NEGATIVE")


def test_controle_total_heures_incoherent_detecte():
    resultat = _resultat_factice(semaine_1=10.0, total_heures=999.0)  # incohérent avec la somme des semaines
    anomalies = controle_paie_service._controler_heures(resultat)
    assert any(a.code == "TOTAL_HEURES_INCOHERENT" and a.niveau == NiveauAnomalie.ERREUR for a in anomalies)


def test_controle_taux_invalide_detecte():
    resultat = _resultat_factice(taux_horaire=0)
    anomalies = controle_paie_service._controler_taux_et_montants(resultat)
    assert any(a.code == "TAUX_INVALIDE" and a.niveau == NiveauAnomalie.ERREUR for a in anomalies)


def test_controle_montant_negatif_detecte():
    resultat = _resultat_factice(dette=-100)
    anomalies = controle_paie_service._controler_taux_et_montants(resultat)
    assert any(a.code == "MONTANT_NEGATIF" and a.niveau == NiveauAnomalie.ERREUR for a in anomalies)


def test_controle_identite_manquante_detectee():
    resultat = _resultat_factice(nom="", prenom="")
    anomalies = controle_paie_service._controler_identite(resultat)
    codes = [a.code for a in anomalies]
    assert "NOM_MANQUANT" in codes
    assert "PRENOM_MANQUANT" in codes


# ---------------------------------------------------------------------
# Contrôle : avertissements (n'empêchent pas la validation)
# ---------------------------------------------------------------------

def test_avertissement_volume_heures_eleve():
    e = _creer_enseignant(taux_horaire=100)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 100, 2: 100, 3: 100, 4: 50, 5: 0})  # 350h > seuil 300h
    rapport = controler_periode(p.id)
    assert not rapport.est_bloque
    assert any(a.code == "VOLUME_HEURES_ELEVE" for a in rapport.avertissements)


def test_avertissement_dette_elevee():
    e = _creer_enseignant(taux_horaire=50000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, dette=150_000)  # gain=500000, net reste positif
    rapport = controler_periode(p.id)
    assert not rapport.est_bloque
    assert any(a.code == "DETTE_ELEVEE" for a in rapport.avertissements)


def test_avertissement_aucun_element_variable():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})  # heures seules
    rapport = controler_periode(p.id)
    assert any(a.code == "AUCUN_ELEMENT_VARIABLE" for a in rapport.avertissements)


# ---------------------------------------------------------------------
# Contrôle : incohérence de calcul (réutilise dashboard_service, testé
# via simulation du résultat de calculer_paie_groupe)
# ---------------------------------------------------------------------

def test_incoherence_calcul_detectee_et_bloquante(monkeypatch):
    from services.paie_service import ResultatCalculGroupe

    resultat_incoherent = _resultat_factice(net_a_percevoir=999999)  # incohérent avec base-taxe-retenue-dette
    groupe_factice = ResultatCalculGroupe(resultats=[resultat_incoherent], erreurs={})

    monkeypatch.setattr(controle_paie_service, "calculer_paie_groupe", lambda *a, **k: groupe_factice)

    p = _creer_periode_ouverte()
    rapport = controler_periode(p.id, enseignant_ids=[1])
    assert rapport.est_bloque
    assert any(a.code == "INCOHERENCE_CALCUL" for a in rapport.erreurs)


# ---------------------------------------------------------------------
# Validation avec contrôle : succès
# ---------------------------------------------------------------------

def test_validation_reussie(db_path):
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=500)

    rapport = valider_periode_avec_controle(p.id, confirmation=True)
    assert not rapport.est_bloque

    p_relue = periode_service.obtenir_periode(p.id)
    assert p_relue.statut.value == "validee"

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'validation_periode' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert len(lignes) == 1
    assert "Succès" in lignes[0]["details"]


# ---------------------------------------------------------------------
# Validation avec contrôle : refus (confirmation manquante)
# ---------------------------------------------------------------------

def test_validation_refusee_sans_confirmation():
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})

    with pytest.raises(ControlePaieError, match="confirmation"):
        valider_periode_avec_controle(p.id, confirmation=False)

    assert periode_service.obtenir_periode(p.id).statut.value == "ouverte"


# ---------------------------------------------------------------------
# Validation avec contrôle : refus (mauvais statut)
# ---------------------------------------------------------------------

def test_validation_refusee_mauvais_statut():
    p = periode_service.creer_periode(mois=2, annee=2040)  # reste BROUILLON
    with pytest.raises(ControlePaieError, match="BROUILLON|statut"):
        valider_periode_avec_controle(p.id, confirmation=True)


# ---------------------------------------------------------------------
# Validation avec contrôle : refus (erreurs bloquantes)
# ---------------------------------------------------------------------

def test_validation_refusee_erreurs_bloquantes(monkeypatch):
    from services.controle_paie_service import Anomalie, RapportControle

    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})

    rapport_bloque = RapportControle(
        periode_id=p.id, nombre_enseignants=1,
        anomalies=[Anomalie(NiveauAnomalie.ERREUR, "TEST_ERREUR", e.id, "Test", "Erreur simulée pour le test.")],
    )
    monkeypatch.setattr(controle_paie_service, "controler_periode", lambda *a, **k: rapport_bloque)

    with pytest.raises(ControlePaieError, match="erreur"):
        valider_periode_avec_controle(p.id, confirmation=True)

    assert periode_service.obtenir_periode(p.id).statut.value == "ouverte"  # inchangé


# ---------------------------------------------------------------------
# Validation avec contrôle : atomicité (rollback si l'écriture échoue)
# ---------------------------------------------------------------------

def test_validation_atomicite_rollback(monkeypatch, db_path):
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})

    def _echec_simule(*args, **kwargs):
        raise sqlite3.OperationalError("panne simulée")

    monkeypatch.setattr(periode_repository, "changer_statut", _echec_simule)

    with pytest.raises(ControlePaieError):
        valider_periode_avec_controle(p.id, confirmation=True)

    assert periode_service.obtenir_periode(p.id).statut.value == "ouverte"
    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'validation_periode' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert lignes == []  # aucune trace d'audit pour une opération annulée


# ---------------------------------------------------------------------
# Clôture avec contrôle : succès, refus, atomicité
# ---------------------------------------------------------------------

def test_cloture_reussie(db_path):
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    valider_periode_avec_controle(p.id, confirmation=True)

    rapport = cloturer_periode_avec_controle(p.id, confirmation=True)
    assert not rapport.est_bloque
    assert periode_service.obtenir_periode(p.id).statut.value == "cloturee"

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'cloture_periode' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert len(lignes) == 1


def test_cloture_refusee_mauvais_statut():
    p = _creer_periode_ouverte()  # encore OUVERTE, pas VALIDEE
    with pytest.raises(ControlePaieError):
        cloturer_periode_avec_controle(p.id, confirmation=True)


def test_cloture_refusee_sans_confirmation():
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    valider_periode_avec_controle(p.id, confirmation=True)

    with pytest.raises(ControlePaieError, match="confirmation"):
        cloturer_periode_avec_controle(p.id, confirmation=False)

    assert periode_service.obtenir_periode(p.id).statut.value == "validee"


# ---------------------------------------------------------------------
# Workflow complet BROUILLON -> OUVERTE -> VALIDEE -> CLOTUREE
# ---------------------------------------------------------------------

def test_workflow_complet_avec_controle():
    e = _creer_enseignant(taux_horaire=1500)
    p = periode_service.creer_periode(mois=3, annee=2040)
    assert p.statut.value == "brouillon"

    p = periode_service.ouvrir_periode(p.id)
    assert p.statut.value == "ouverte"

    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=1000)

    valider_periode_avec_controle(p.id, confirmation=True)
    assert periode_service.obtenir_periode(p.id).statut.value == "validee"

    cloturer_periode_avec_controle(p.id, confirmation=True)
    assert periode_service.obtenir_periode(p.id).statut.value == "cloturee"


def test_transitions_interdites_restent_interdites():
    """Le workflow avec contrôle ne doit pas permettre de contourner les transitions déjà interdites."""
    p = periode_service.creer_periode(mois=4, annee=2040)  # BROUILLON
    with pytest.raises(ControlePaieError):
        cloturer_periode_avec_controle(p.id, confirmation=True)  # BROUILLON -> CLOTUREE interdit


# ---------------------------------------------------------------------
# Statistiques descriptives
# ---------------------------------------------------------------------

def test_statistiques_net_calcul_correct():
    resultats = [
        _resultat_factice(net_a_percevoir=1000),
        _resultat_factice(net_a_percevoir=2000),
        _resultat_factice(net_a_percevoir=3000),
    ]
    stats = statistiques_net(resultats)
    assert stats.moyenne == 2000
    assert stats.mediane == 2000
    assert stats.minimum == 1000
    assert stats.maximum == 3000


def test_statistiques_net_liste_vide():
    stats = statistiques_net([])
    assert stats.moyenne == 0.0
    assert stats.minimum == 0
    assert stats.maximum == 0


# ---------------------------------------------------------------------
# Cas de référence officiel (non-régression du moteur de paie)
# ---------------------------------------------------------------------

def test_cas_reference_100h_2000fcfa_inchange():
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    rapport = valider_periode_avec_controle(p.id, confirmation=True)
    cloturer_periode_avec_controle(p.id, confirmation=True)

    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.total_heures == 100
    assert resultat.gain_heures == 200000
    assert resultat.base_taxable == 235000
    assert resultat.taxe_5 == 11750
    assert resultat.net_a_percevoir == 208250


# ---------------------------------------------------------------------
# Aucune formule de paie dans ce service
# ---------------------------------------------------------------------

def test_aucune_formule_de_paie_dans_controle_paie_service():
    source = inspect.getsource(controle_paie_service)
    assert "* 0.05" not in source
    assert "TAUX_TAXE" not in source
    assert "taux_horaire *" not in source
    assert "gain_heures =" not in source
