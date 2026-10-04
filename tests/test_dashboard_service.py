"""
Tests du service tableau de bord (services/dashboard_service.py).

Couvre : indicateurs enseignants, agrégats de paie (période, statut,
sexe), recherche/filtres, contrôles de cohérence, historique des
bulletins, évolution de la masse salariale, export, et le cas
d'intégrité officiel du projet (100h x 2000 FCFA -> net 208250).
"""

import inspect

import pytest

import database.connection as database_connection
from services import dashboard_service, donnees_paie_service, enseignant_service, periode_service
from services.comptabilite_service import preparer_etat_comptable
from services.donnees_paie_service import DonneesPaieEnseignant

# Cas de référence officiel : vacataire, taxe de 5 %.
pytestmark = pytest.mark.taxe_historique


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch, tmp_path):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    # Isole les fichiers d'export générés pendant les tests.
    from exports import excel_export as excel_export_module
    monkeypatch.setattr(excel_export_module, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(dashboard_service, "EXPORT_DIR", tmp_path / "exports")


def _creer_enseignant(**overrides):
    donnees = {"nom": "Mbarga", "prenom": "Paul", "sexe": "M", "statut": "V", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=1, annee=2032):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


# ---------------------------------------------------------------------
# Indicateurs enseignants
# ---------------------------------------------------------------------

def test_indicateurs_enseignants_corrects():
    _creer_enseignant(nom="A", prenom="A", statut="P")
    _creer_enseignant(nom="B", prenom="B", statut="V")
    e3 = _creer_enseignant(nom="C", prenom="C", statut="V")
    enseignant_service.desactiver_enseignant(e3.id)

    indicateurs = dashboard_service.obtenir_indicateurs_enseignants()
    assert indicateurs.total == 3
    assert indicateurs.actifs == 2
    assert indicateurs.inactifs == 1
    assert indicateurs.permanents == 1
    assert indicateurs.vacataires == 2


# ---------------------------------------------------------------------
# Récupération correcte d'une période + agrégats de paie
# ---------------------------------------------------------------------

def test_recuperation_periode_et_agregats():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=500)
    p = periode_service.valider_periode(p.id)

    etat = preparer_etat_comptable(p.id)
    assert etat.periode.id == p.id
    assert len(etat.resultats) == 1
    assert etat.totaux.total_gain_heures == 10000


# ---------------------------------------------------------------------
# Séparation permanent/vacataire, masculin/féminin
# ---------------------------------------------------------------------

def test_separation_permanent_vacataire():
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", statut="V", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 20})
    p = periode_service.valider_periode(p.id)

    etat = preparer_etat_comptable(p.id)
    synthese = {s.libelle: s for s in dashboard_service.synthese_par_statut(etat.resultats)}
    assert synthese["P"].nombre == 1
    assert synthese["V"].nombre == 1
    assert synthese["V"].total_gain_heures == 20000


def test_separation_masculin_feminin():
    e1 = _creer_enseignant(nom="A", prenom="A", sexe="M", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", sexe="F", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 30})
    p = periode_service.valider_periode(p.id)

    etat = preparer_etat_comptable(p.id)
    synthese = {s.libelle: s for s in dashboard_service.synthese_par_sexe(etat.resultats)}
    assert synthese["M"].nombre == 1
    assert synthese["F"].total_gain_heures == 30000


# ---------------------------------------------------------------------
# Total gains / taxe / retenues / net
# ---------------------------------------------------------------------

def test_totaux_gains_taxe_retenues_net():
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    p = periode_service.valider_periode(p.id)

    etat = preparer_etat_comptable(p.id)
    assert etat.totaux.total_gain_heures == 200000
    assert etat.totaux.total_taxe == 11750
    assert etat.totaux.total_retenues == 15000
    assert etat.totaux.total_net_a_percevoir == 208250


# ---------------------------------------------------------------------
# Filtres (statut, sexe, actif) — combinables
# ---------------------------------------------------------------------

def test_filtre_statut():
    from models.enums import StatutEnseignant
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P")
    e2 = _creer_enseignant(nom="B", prenom="B", statut="V")
    tous = enseignant_service.lister_enseignants(inclure_inactifs=True)
    filtres = dashboard_service.filtrer_enseignants(tous, statut=StatutEnseignant.PERMANENT)
    assert {e.id for e in filtres} == {e1.id}


def test_filtre_sexe():
    from models.enums import Sexe
    e1 = _creer_enseignant(nom="A", prenom="A", sexe="M")
    e2 = _creer_enseignant(nom="B", prenom="B", sexe="F")
    tous = enseignant_service.lister_enseignants(inclure_inactifs=True)
    filtres = dashboard_service.filtrer_enseignants(tous, sexe=Sexe.FEMME)
    assert {e.id for e in filtres} == {e2.id}


def test_filtre_actif():
    e1 = _creer_enseignant(nom="A", prenom="A")
    e2 = _creer_enseignant(nom="B", prenom="B")
    enseignant_service.desactiver_enseignant(e2.id)
    tous = enseignant_service.lister_enseignants(inclure_inactifs=True)
    filtres = dashboard_service.filtrer_enseignants(tous, actif=True)
    assert {e.id for e in filtres} == {e1.id}


def test_combinaison_filtres():
    from models.enums import StatutEnseignant, Sexe
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", sexe="M")
    e2 = _creer_enseignant(nom="B", prenom="B", statut="P", sexe="F")
    e3 = _creer_enseignant(nom="C", prenom="C", statut="V", sexe="M")
    tous = enseignant_service.lister_enseignants(inclure_inactifs=True)
    filtres = dashboard_service.filtrer_enseignants(tous, statut=StatutEnseignant.PERMANENT, sexe=Sexe.HOMME)
    assert {e.id for e in filtres} == {e1.id}


# ---------------------------------------------------------------------
# Recherche (réutilise enseignant_service, insensible à la casse)
# ---------------------------------------------------------------------

def test_recherche_par_nom_insensible_casse():
    _creer_enseignant(nom="MBALLA", prenom="Clarisse Ndome")
    resultats = enseignant_service.rechercher_enseignants("mballa", inclure_inactifs=True)
    assert len(resultats) == 1
    assert resultats[0].nom == "MBALLA"


def test_recherche_par_prenom():
    _creer_enseignant(nom="Dupont", prenom="Xavier")
    resultats = enseignant_service.rechercher_enseignants("xavier", inclure_inactifs=True)
    assert len(resultats) == 1


def test_recherche_par_nom_complet():
    _creer_enseignant(nom="Mballa", prenom="Clarisse Ndome")
    resultats = enseignant_service.rechercher_enseignants("Mballa Clarisse", inclure_inactifs=True)
    assert len(resultats) == 1


# ---------------------------------------------------------------------
# Contrôles de cohérence
# ---------------------------------------------------------------------

def test_controle_coherence_aucune_anomalie():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    etat = preparer_etat_comptable(p.id)
    anomalies = dashboard_service.controler_coherence_resultats(etat.resultats)
    assert anomalies == []


def test_controle_coherence_detecte_incoherence_arithmetique():
    from models.resultat_paie import ResultatPaie
    from models.enums import Sexe, StatutEnseignant

    resultat_incoherent = ResultatPaie(
        enseignant_id=1, periode_id=1, nom="Test", prenom="Incoherent",
        sexe=Sexe.HOMME, statut=StatutEnseignant.PERMANENT, taux_horaire=1000,
        semaine_1=0, semaine_2=0, semaine_3=0, semaine_4=0, semaine_5=0, total_heures=0,
        gain_heures=0, prime_ap_pp=0, surveillance_secretariat=0, indemnite_suggestion_admin=0,
        base_taxable=1000, taxe_5=50, retenue_amicale=0, dette=0,
        net_a_percevoir=999,  # incohérent : devrait être 950
    )
    anomalies = dashboard_service.controler_coherence_resultats([resultat_incoherent])
    assert len(anomalies) == 1
    assert "incohérence" in anomalies[0]


def test_controle_coherence_detecte_doublon():
    from models.resultat_paie import ResultatPaie
    from models.enums import Sexe, StatutEnseignant

    def _resultat():
        return ResultatPaie(
            enseignant_id=1, periode_id=1, nom="Test", prenom="Doublon",
            sexe=Sexe.HOMME, statut=StatutEnseignant.PERMANENT, taux_horaire=1000,
            semaine_1=0, semaine_2=0, semaine_3=0, semaine_4=0, semaine_5=0, total_heures=0,
            gain_heures=0, prime_ap_pp=0, surveillance_secretariat=0, indemnite_suggestion_admin=0,
            base_taxable=0, taxe_5=0, retenue_amicale=0, dette=0, net_a_percevoir=0,
        )
    anomalies = dashboard_service.controler_coherence_resultats([_resultat(), _resultat()])
    assert any("plusieurs résultats" in a for a in anomalies)


# ---------------------------------------------------------------------
# Historique des bulletins (lecture seule du système du module 07)
# ---------------------------------------------------------------------

def test_etat_bulletins_periode_reflete_generation_reelle(tmp_path, monkeypatch):
    from services import bulletin_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")

    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    etat = preparer_etat_comptable(p.id)
    etats_avant = dashboard_service.etat_bulletins_periode(etat.resultats, p.libelle)
    assert etats_avant[e.id] is False

    bulletin_service.generer_bulletin_enseignant(p.id, e.id)

    etats_apres = dashboard_service.etat_bulletins_periode(etat.resultats, p.libelle)
    assert etats_apres[e.id] is True


# ---------------------------------------------------------------------
# Évolution de la masse salariale
# ---------------------------------------------------------------------

def test_evolution_masse_salariale_plusieurs_periodes():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=1, annee=2033)
    p2 = _creer_periode_ouverte(mois=2, annee=2033)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 20})
    periode_service.valider_periode(p1.id)
    periode_service.valider_periode(p2.id)

    evolution = dashboard_service.evolution_masse_salariale()
    assert len(evolution) == 2
    assert evolution[0].mois == 1 and evolution[1].mois == 2
    assert evolution[0].total_net < evolution[1].total_net


def test_evolution_ignore_periodes_brouillon():
    _creer_periode_ouverte(mois=3, annee=2033)  # ouverte mais sans donnée -> ignorée
    periode_service.creer_periode(mois=4, annee=2033)  # reste en brouillon -> ignorée
    evolution = dashboard_service.evolution_masse_salariale()
    assert evolution == []


# ---------------------------------------------------------------------
# Export Excel de la consultation (réutilise le module 06)
# ---------------------------------------------------------------------

def test_export_consultation_cree_fichier_excel():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    chemin = dashboard_service.exporter_consultation_excel(p.id)
    assert chemin.exists()
    assert chemin.suffix == ".xlsx"


def test_export_consultation_nom_avec_enseignant():
    e = _creer_enseignant(nom="Mballa", prenom="Clarisse", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    chemin = dashboard_service.exporter_consultation_excel(p.id, enseignant_ids=[e.id])
    assert "MBALLA" in chemin.name.upper()
    assert "CLARISSE" in chemin.name.upper()


# ---------------------------------------------------------------------
# Cas d'intégrité officiel du projet
# ---------------------------------------------------------------------

def test_cas_integrite_officiel_100h_2000():
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    p = periode_service.valider_periode(p.id)

    etat = preparer_etat_comptable(p.id)
    r = etat.resultats[0]
    assert r.total_heures == 100
    assert r.gain_heures == 200000
    assert r.base_taxable == 235000
    assert r.taxe_5 == 11750
    assert r.net_a_percevoir == 208250
    assert etat.totaux.total_net_a_percevoir == 208250


# ---------------------------------------------------------------------
# Aucune duplication de formule de paie
# ---------------------------------------------------------------------

def test_aucune_formule_de_paie_dans_dashboard_service():
    source = inspect.getsource(dashboard_service)
    assert "* 0.05" not in source
    assert "TAUX_TAXE" not in source
    assert "taux_horaire *" not in source
