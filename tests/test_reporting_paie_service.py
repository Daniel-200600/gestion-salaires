"""
Tests de services/reporting_paie_service.py (module 13).
"""

import inspect

import pytest

import database.connection as database_connection
from services import (
    controle_paie_service,
    donnees_paie_service,
    enseignant_service,
    periode_service,
    reporting_paie_service,
)
from services.comptabilite_service import ComptabiliteError, preparer_etat_comptable
from services.donnees_paie_service import DonneesPaieEnseignant
from services.historique_paie_service import comparer_periodes
from services.reporting_paie_service import StatutRapprochement


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Mbarga", "prenom": "Paul", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=1, annee=2050):
    p = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(p.id)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


def _resultat_factice(**overrides):
    from models.resultat_paie import ResultatPaie
    from models.enums import Sexe, StatutEnseignant

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
# Synthèses détaillées par statut / sexe
# ---------------------------------------------------------------------

def test_synthese_detaillee_par_statut():
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", statut="V", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10}, prime_ap_pp=500)
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 20}, dette=200)

    etat = preparer_etat_comptable(p.id)
    synthese = reporting_paie_service.synthese_detaillee_par_statut(etat.resultats)
    libelles = {s.libelle: s for s in synthese}
    assert "Permanent" in libelles
    assert "Vacataire" in libelles
    assert libelles["Permanent"].total_prime_ap_pp == 500
    assert libelles["Vacataire"].total_dette == 200


def test_synthese_detaillee_par_sexe():
    e1 = _creer_enseignant(nom="A", prenom="A", sexe="M", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", sexe="F", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 30})

    etat = preparer_etat_comptable(p.id)
    synthese = reporting_paie_service.synthese_detaillee_par_sexe(etat.resultats)
    libelles = {s.libelle: s for s in synthese}
    assert libelles["Féminin"].total_gain_heures == 30000
    assert libelles["Masculin"].total_gain_heures == 10000


def test_synthese_vide_si_aucun_resultat():
    assert reporting_paie_service.synthese_detaillee_par_statut([]) == []


# ---------------------------------------------------------------------
# Rapprochement individuel
# ---------------------------------------------------------------------

def test_rapprochement_enseignant_coherent_est_ok():
    resultat = _resultat_factice(
        gain_heures=200000, prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        base_taxable=235000, taxe_5=11750, retenue_amicale=5000, dette=10000, net_a_percevoir=208250,
    )
    rapport = reporting_paie_service.rapprocher_enseignant(resultat)
    assert rapport.toutes_ok
    assert all(l.statut == StatutRapprochement.OK for l in rapport.lignes)
    assert all(l.ecart == 0 for l in rapport.lignes)


def test_rapprochement_enseignant_incoherent_detecte_ecart():
    resultat = _resultat_factice(base_taxable=9999)  # incohérent avec gain_heures=10000
    rapport = reporting_paie_service.rapprocher_enseignant(resultat)
    assert not rapport.toutes_ok
    ligne_base = rapport.lignes[0]
    assert ligne_base.statut == StatutRapprochement.ECART
    assert ligne_base.ecart == -1


def test_rapprochement_cas_reference_officiel():
    resultat = _resultat_factice(
        taux_horaire=2000, total_heures=100, gain_heures=200000, prime_ap_pp=20000,
        surveillance_secretariat=10000, indemnite_suggestion_admin=5000, base_taxable=235000,
        taxe_5=11750, retenue_amicale=5000, dette=10000, net_a_percevoir=208250,
    )
    rapport = reporting_paie_service.rapprocher_enseignant(resultat)
    assert rapport.toutes_ok
    ligne_net = [l for l in rapport.lignes if "Net" in l.element][0]
    assert ligne_net.montant_enregistre == 208250
    assert ligne_net.ecart == 0


# ---------------------------------------------------------------------
# Rapprochement global de période
# ---------------------------------------------------------------------

def test_rapprochement_periode_coherent():
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    etat = preparer_etat_comptable(p.id)
    rapport = reporting_paie_service.rapprocher_periode(etat)
    assert rapport.toutes_ok
    ligne_net = [l for l in rapport.lignes if "net" in l.element.lower()][0]
    assert ligne_net.montant_enregistre == 208250


def test_rapprochement_periode_incoherent_detecte():
    from services.comptabilite_service import EtatComptablePeriode
    from services.paie_service import TotauxPaieGroupe

    resultat = _resultat_factice(net_a_percevoir=9500)
    totaux_incoherents = TotauxPaieGroupe(
        total_heures=10.0, total_gain_heures=10000, total_net_a_percevoir=999999,  # incohérent
    )
    faux_periode = periode_service.creer_periode(mois=2, annee=2050)
    etat_factice = EtatComptablePeriode(
        periode=faux_periode, resultats=[resultat], totaux=totaux_incoherents, synthese_par_statut=[],
    )
    rapport = reporting_paie_service.rapprocher_periode(etat_factice)
    assert not rapport.toutes_ok


# ---------------------------------------------------------------------
# Classement des enseignants
# ---------------------------------------------------------------------

def test_classement_par_net_decroissant():
    e1 = _creer_enseignant(nom="A", prenom="A", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", taux_horaire=3000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)

    classement = reporting_paie_service.classer_enseignants(etat.resultats, "net_a_percevoir", decroissant=True)
    assert classement[0].nom == "B"  # taux plus élevé -> net plus élevé -> premier


def test_classement_croissant():
    e1 = _creer_enseignant(nom="A", prenom="A", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", taux_horaire=3000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)

    classement = reporting_paie_service.classer_enseignants(etat.resultats, "net_a_percevoir", decroissant=False)
    assert classement[0].nom == "A"


def test_classement_ne_modifie_pas_la_liste_originale():
    resultats = [_resultat_factice(net_a_percevoir=100), _resultat_factice(net_a_percevoir=200)]
    original = list(resultats)
    reporting_paie_service.classer_enseignants(resultats, "net_a_percevoir")
    assert resultats == original


def test_classement_critere_invalide_leve():
    with pytest.raises(ValueError):
        reporting_paie_service.classer_enseignants([], "critere_inconnu")


# ---------------------------------------------------------------------
# État des retenues
# ---------------------------------------------------------------------

def test_etat_retenues():
    resultat = _resultat_factice(taxe_5=100, retenue_amicale=50, dette=30, net_a_percevoir=9820)
    lignes = reporting_paie_service.etat_retenues([resultat])
    assert lignes[0].total_retenues == 180


# ---------------------------------------------------------------------
# Comparaison / analyse des variations
# ---------------------------------------------------------------------

def test_analyse_variations_hausse_detectee():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=3)
    p2 = _creer_periode_ouverte(mois=4)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 100})  # forte hausse

    comparaison = comparer_periodes(p1.id, p2.id)
    observations = reporting_paie_service.analyser_variations(comparaison)
    assert any("Hausse" in o for o in observations)


def test_analyse_variations_baisse_detectee():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=5)
    p2 = _creer_periode_ouverte(mois=6)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 100})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 10})  # forte baisse

    comparaison = comparer_periodes(p1.id, p2.id)
    observations = reporting_paie_service.analyser_variations(comparaison)
    assert any("Baisse" in o for o in observations)


def test_analyse_variations_egalite_aucune_observation():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=7)
    p2 = _creer_periode_ouverte(mois=8)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 10})

    comparaison = comparer_periodes(p1.id, p2.id)
    observations = reporting_paie_service.analyser_variations(comparaison)
    assert observations == []


def test_analyse_variations_periode_vide_geree_explicitement():
    """
    comparer_periodes (module 12) lève ComptabiliteError, de façon
    claire et catchable, pour une période sans aucun enseignant —
    jamais de NaN/Infinity/None affiché, jamais de plantage silencieux.
    La page (module 13) capture déjà cette exception proprement.
    """
    p1 = _creer_periode_ouverte(mois=9)  # aucune donnée -> aucun enseignant disponible
    p2 = _creer_periode_ouverte(mois=10)
    e1 = _creer_enseignant(nom="Solo", prenom="X", taux_horaire=1000)
    _saisir_donnees(p2.id, e1.id, heures_par_semaine={1: 10})

    with pytest.raises(ComptabiliteError):
        comparer_periodes(p1.id, p2.id)


def test_seuil_configurable():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=11)
    p2 = _creer_periode_ouverte(mois=12)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 11})  # +10% environ

    comparaison = comparer_periodes(p1.id, p2.id)
    observations_seuil_bas = reporting_paie_service.analyser_variations(comparaison, seuil_pourcent=1.0)
    observations_seuil_haut = reporting_paie_service.analyser_variations(comparaison, seuil_pourcent=99.0)
    assert len(observations_seuil_bas) >= len(observations_seuil_haut)


# ---------------------------------------------------------------------
# État de paie complet — cas de référence officiel
# ---------------------------------------------------------------------

def test_etat_paie_complet_cas_reference():
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    rapport = reporting_paie_service.construire_etat_paie_complet(p.id, etablissement="École Test", utilisateur="admin")
    assert rapport.etat_comptable.totaux.total_net_a_percevoir == 208250
    assert rapport.rapprochement.toutes_ok
    assert "conforme" in rapport.observations[0].lower()
    assert rapport.utilisateur == "admin"


def test_etat_paie_complet_periode_sans_enseignant_leve():
    p = _creer_periode_ouverte()
    with pytest.raises(ComptabiliteError):
        reporting_paie_service.construire_etat_paie_complet(p.id)


def test_etat_paie_complet_fonctionne_sur_periode_cloturee():
    """Le reporting reste possible (lecture seule) sur une période clôturée (module 12)."""
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)

    rapport = reporting_paie_service.construire_etat_paie_complet(p.id)
    assert rapport.etat_comptable.totaux.total_net_a_percevoir == 208250
    assert rapport.rapprochement.toutes_ok

    periode_relue = periode_service.obtenir_periode(p.id)
    assert periode_relue.statut.value == "cloturee"


# ---------------------------------------------------------------------
# Aucune formule de paie dupliquée
# ---------------------------------------------------------------------

def test_aucune_formule_de_paie_dans_reporting_service():
    source = inspect.getsource(reporting_paie_service)
    assert "* 0.05" not in source
    assert "TAUX_TAXE" not in source
    assert "taux_horaire *" not in source
    assert "gain_heures =" not in source


# ---------------------------------------------------------------------
# Filtres combinés (section 26)
# ---------------------------------------------------------------------

def test_filtrer_resultats_aucun_filtre():
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", sexe="M", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", statut="V", sexe="F", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)

    filtres = reporting_paie_service.filtrer_resultats(etat.resultats)
    assert len(filtres) == 2


def test_filtrer_resultats_par_statut_seul():
    from models.enums import StatutEnseignant
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", statut="V", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)

    filtres = reporting_paie_service.filtrer_resultats(etat.resultats, statut=StatutEnseignant.PERMANENT)
    assert len(filtres) == 1
    assert filtres[0].nom == "A"


def test_filtrer_resultats_par_sexe_seul():
    from models.enums import Sexe
    e1 = _creer_enseignant(nom="A", prenom="A", sexe="M", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", sexe="F", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)

    filtres = reporting_paie_service.filtrer_resultats(etat.resultats, sexe=Sexe.FEMME)
    assert len(filtres) == 1
    assert filtres[0].nom == "B"


def test_filtrer_resultats_statut_et_sexe_combines():
    from models.enums import Sexe, StatutEnseignant
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", sexe="M", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", statut="P", sexe="F", taux_horaire=1000)
    e3 = _creer_enseignant(nom="C", prenom="C", statut="V", sexe="M", taux_horaire=1000)
    p = _creer_periode_ouverte()
    for e in (e1, e2, e3):
        _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)

    filtres = reporting_paie_service.filtrer_resultats(
        etat.resultats, statut=StatutEnseignant.PERMANENT, sexe=Sexe.HOMME
    )
    assert len(filtres) == 1
    assert filtres[0].nom == "A"


def test_filtrer_resultats_aucune_correspondance():
    from models.enums import Sexe, StatutEnseignant
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", sexe="M", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)

    filtres = reporting_paie_service.filtrer_resultats(
        etat.resultats, statut=StatutEnseignant.VACATAIRE, sexe=Sexe.FEMME
    )
    assert filtres == []


def test_filtrer_resultats_ne_modifie_pas_la_liste_originale():
    from models.enums import StatutEnseignant
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)
    original = list(etat.resultats)

    reporting_paie_service.filtrer_resultats(etat.resultats, statut=StatutEnseignant.VACATAIRE)
    assert etat.resultats == original


# ---------------------------------------------------------------------
# Données vides (section 31) — jamais de NaN/Infinity/None affiché
# ---------------------------------------------------------------------

def test_periode_sans_retenue_ni_dette_ni_indemnite():
    """Tous les champs optionnels à zéro : aucune valeur None/NaN dans le résultat."""
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})  # heures seules, rien d'autre

    rapport = reporting_paie_service.construire_etat_paie_complet(p.id)
    resultat = rapport.etat_comptable.resultats[0]
    assert resultat.prime_ap_pp == 0
    assert resultat.retenue_amicale == 0
    assert resultat.dette == 0
    assert resultat.indemnite_suggestion_admin == 0
    assert rapport.rapprochement.toutes_ok  # aucune incohérence malgré les zéros


def test_synthese_par_groupe_sans_donnees_ne_plante_pas():
    assert reporting_paie_service.synthese_detaillee_par_sexe([]) == []
    assert reporting_paie_service.etat_retenues([]) == []


def test_classement_liste_vide_ne_plante_pas():
    assert reporting_paie_service.classer_enseignants([], "net_a_percevoir") == []
