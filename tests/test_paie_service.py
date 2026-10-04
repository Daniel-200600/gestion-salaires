"""
Tests du moteur de calcul de paie (services/paie_service.py).

Couvre : heures, rémunérations, taxe (et son arrondi), retenues, net,
cas limites, calcul groupé, indépendance et non-régression sur les
statuts de période.
"""

import pytest

import database.connection as database_connection
from services import donnees_paie_service, enseignant_service, paie_service, periode_service
from services.donnees_paie_service import DonneesPaieEnseignant
from services.paie_service import CalculPaieError

# Cas de référence officiel : vacataire, taxe de 5 %.
pytestmark = pytest.mark.taxe_historique


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _creer_enseignant(**overrides):
    donnees = {"nom": "Traore", "prenom": "Salif", "sexe": "M", "statut": "V", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=3, annee=2027):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


# ---------------------------------------------------------------------
# Heures
# ---------------------------------------------------------------------

def test_zero_heure_donne_gain_zero():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)  # aucune saisie
    assert resultat.total_heures == 0
    assert resultat.gain_heures == 0


def test_dix_heures_fois_mille_egale_dix_mille():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.total_heures == 10
    assert resultat.gain_heures == 10000


def test_somme_correcte_des_cinq_semaines():
    e = _creer_enseignant(taux_horaire=100)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10, 2: 15, 3: 12, 4: 16, 5: 14})
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.total_heures == 67
    assert resultat.semaine_1 == 10
    assert resultat.semaine_2 == 15
    assert resultat.semaine_3 == 12
    assert resultat.semaine_4 == 16
    assert resultat.semaine_5 == 14


def test_heures_decimales_correctement_traitees():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 7.5, 2: 2.5})
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.total_heures == 10.0
    assert resultat.gain_heures == 10000


# ---------------------------------------------------------------------
# Rémunérations
# ---------------------------------------------------------------------

def test_prime_ap_pp_incluse():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=5000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.base_taxable == 5000


def test_surveillance_secretariat_inclus():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, surveillance_secretariat=3000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.base_taxable == 3000


def test_indemnite_suggestion_admin_incluse():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, indemnite_suggestion_admin=2000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.base_taxable == 2000


def test_toutes_remunerations_a_zero():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.prime_ap_pp == 0
    assert resultat.surveillance_secretariat == 0
    assert resultat.indemnite_suggestion_admin == 0
    assert resultat.base_taxable == 0


# ---------------------------------------------------------------------
# Taxe (et son arrondi)
# ---------------------------------------------------------------------

def test_taxe_egale_base_taxable_fois_5_pourcent():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=100000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.base_taxable == 100000
    assert resultat.taxe_5 == 5000  # 100000 * 0.05


def test_arrondi_taxe_half_up_exact():
    """
    base_taxable = 10 -> taxe brute = 0,5 -> arrondi HALF_UP à 1
    (et non 0, ce qu'aurait donné le banker's rounding de round() natif).
    """
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=10)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.base_taxable == 10
    assert resultat.taxe_5 == 1


def test_arrondi_taxe_vers_le_bas():
    """base_taxable = 101 -> taxe brute = 5,05 -> arrondi à 5."""
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=101)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.taxe_5 == 5


def test_taxe_plusieurs_montants():
    cas = [
        (1000, 50),      # 1000 * 0.05 = 50
        (23500, 1175),   # 23500 * 0.05 = 1175
        (7, 0),          # 7 * 0.05 = 0.35 -> 0
        (30, 2),         # 30 * 0.05 = 1.5 -> 2 (HALF_UP)
    ]
    for base, taxe_attendue in cas:
        e = _creer_enseignant(taux_horaire=0)
        p = _creer_periode_ouverte(mois=(cas.index((base, taxe_attendue)) % 12) + 1, annee=2028)
        _saisir_donnees(p.id, e.id, prime_ap_pp=base)
        resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
        assert resultat.taxe_5 == taxe_attendue, f"base={base} attendu={taxe_attendue} obtenu={resultat.taxe_5}"


# ---------------------------------------------------------------------
# Retenues
# ---------------------------------------------------------------------

def test_retenue_amicale_deduite():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=10000, retenue_amicale=1000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir == resultat.base_taxable - resultat.taxe_5 - 1000


def test_dette_deduite():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=10000, dette=2000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir == resultat.base_taxable - resultat.taxe_5 - 2000


def test_retenue_amicale_et_dette_deduites():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=10000, retenue_amicale=1000, dette=2000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir == resultat.base_taxable - resultat.taxe_5 - 3000


def test_retenues_a_zero():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, prime_ap_pp=10000)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.retenue_amicale == 0
    assert resultat.dette == 0
    assert resultat.net_a_percevoir == resultat.base_taxable - resultat.taxe_5


# ---------------------------------------------------------------------
# NET — cas complet, calcul manuel attendu (exemple de l'énoncé)
# ---------------------------------------------------------------------

def test_cas_complet_exemple_enonce():
    """
    Heures = 100, Taux = 2000 -> Gain = 200000
    Prime AP/PP = 20000, Surveillance = 10000, Indemnité = 5000 -> Base = 235000
    Taxe = 11750
    Retenue amicale = 5000, Dette = 10000 -> Net = 208250
    """
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)

    assert resultat.total_heures == 100
    assert resultat.gain_heures == 200000
    assert resultat.base_taxable == 235000
    assert resultat.taxe_5 == 11750
    assert resultat.net_a_percevoir == 208250


def test_cas_complet_deuxieme_exemple():
    """Second cas manuel, avec des heures inégales et un taux différent."""
    e = _creer_enseignant(taux_horaire=1500)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 8, 2: 9, 3: 10, 4: 7, 5: 6},  # total = 40
        prime_ap_pp=15000, surveillance_secretariat=5000, indemnite_suggestion_admin=2500,
        retenue_amicale=3000, dette=0,
    )
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)

    gain_attendu = 40 * 1500  # 60000
    base_attendue = gain_attendu + 15000 + 5000 + 2500  # 82500
    taxe_attendue = round(82500 * 0.05)  # 4125, exact
    net_attendu = base_attendue - taxe_attendue - 3000  # 75375

    assert resultat.gain_heures == gain_attendu == 60000
    assert resultat.base_taxable == base_attendue == 82500
    assert resultat.taxe_5 == taxe_attendue == 4125
    assert resultat.net_a_percevoir == net_attendu == 75375


# ---------------------------------------------------------------------
# Cas limites
# ---------------------------------------------------------------------

def test_taux_horaire_zero():
    e = _creer_enseignant(taux_horaire=0)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 100})
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.gain_heures == 0


def test_heures_zero_taux_non_zero():
    e = _creer_enseignant(taux_horaire=5000)
    p = _creer_periode_ouverte()
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.gain_heures == 0


def test_tous_complements_a_zero():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.base_taxable == resultat.gain_heures


def test_montant_suffisamment_eleve():
    e = _creer_enseignant(taux_horaire=50000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 40, 2: 40, 3: 40, 4: 40, 5: 40},  # 200h
        prime_ap_pp=500000, surveillance_secretariat=300000, indemnite_suggestion_admin=100000,
    )
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.gain_heures == 200 * 50000  # 10 000 000
    assert resultat.base_taxable == 10_000_000 + 900_000
    assert resultat.taxe_5 == round(10_900_000 * 0.05)


def test_enseignant_inexistant():
    p = _creer_periode_ouverte()
    with pytest.raises(CalculPaieError):
        paie_service.calculer_paie_enseignant(p.id, 9999)


def test_periode_inexistante():
    e = _creer_enseignant()
    with pytest.raises(CalculPaieError):
        paie_service.calculer_paie_enseignant(9999, e.id)


def test_periode_brouillon_refusee():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=6, annee=2028)  # reste en brouillon
    with pytest.raises(CalculPaieError):
        paie_service.calculer_paie_enseignant(p.id, e.id)


def test_donnees_manquantes_ne_leve_pas_erreur():
    """Un enseignant existant sans aucune saisie pour la période donne un résultat entièrement à zéro."""
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.total_heures == 0
    assert resultat.gain_heures == 0
    assert resultat.base_taxable == 0
    assert resultat.taxe_5 == 0
    assert resultat.net_a_percevoir == 0


def test_periode_validee_calculable():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.gain_heures == 10000


def test_periode_cloturee_calculable_sur_donnees_figees():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    p = periode_service.cloturer_periode(p.id)
    resultat = paie_service.calculer_paie_enseignant(p.id, e.id)
    assert resultat.gain_heures == 10000


def test_calcul_ne_modifie_aucune_donnee_source():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10, 2: 5}, prime_ap_pp=2000)

    avant = heures_avant = None
    from services import heures_service as hs
    avant = hs.obtenir_heures_enseignant(p.id, e.id)

    paie_service.calculer_paie_enseignant(p.id, e.id)  # calcul, ne doit rien modifier

    apres = hs.obtenir_heures_enseignant(p.id, e.id)
    assert avant == apres


# ---------------------------------------------------------------------
# Calcul groupé
# ---------------------------------------------------------------------

def test_groupe_un_seul_enseignant():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    groupe = paie_service.calculer_paie_groupe(p.id, [e.id])
    assert len(groupe.resultats) == 1
    assert groupe.resultats[0].gain_heures == 10000
    assert groupe.erreurs == {}


def test_groupe_deux_enseignants():
    e1 = _creer_enseignant(nom="Traore", prenom="Salif", taux_horaire=1000)
    e2 = _creer_enseignant(nom="Diallo", prenom="Aicha", taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 5})

    groupe = paie_service.calculer_paie_groupe(p.id, [e1.id, e2.id])
    resultats_par_id = {r.enseignant_id: r for r in groupe.resultats}
    assert len(groupe.resultats) == 2
    assert resultats_par_id[e1.id].gain_heures == 10000
    assert resultats_par_id[e2.id].gain_heures == 10000  # 5 * 2000


def test_groupe_plusieurs_enseignants():
    enseignants = [_creer_enseignant(nom=f"Ens{i}", prenom=f"P{i}", taux_horaire=1000) for i in range(10)]
    p = _creer_periode_ouverte()
    for e in enseignants:
        _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})

    groupe = paie_service.calculer_paie_groupe(p.id, [e.id for e in enseignants])
    assert len(groupe.resultats) == 10
    assert all(r.gain_heures == 10000 for r in groupe.resultats)


def test_groupe_resultats_independants():
    e1 = _creer_enseignant(nom="Traore", prenom="Salif", taux_horaire=1000)
    e2 = _creer_enseignant(nom="Diallo", prenom="Aicha", taux_horaire=5000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 1}, prime_ap_pp=100)
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 200}, prime_ap_pp=999999)

    groupe = paie_service.calculer_paie_groupe(p.id, [e1.id, e2.id])
    resultats_par_id = {r.enseignant_id: r for r in groupe.resultats}

    # e1 doit rester inchangé par le calcul (potentiellement lourd) de e2
    assert resultats_par_id[e1.id].gain_heures == 1000
    assert resultats_par_id[e1.id].prime_ap_pp == 100
    assert resultats_par_id[e2.id].gain_heures == 1_000_000


def test_groupe_erreur_sur_un_enseignant_sans_corruption_des_autres():
    e1 = _creer_enseignant(nom="Traore", prenom="Salif", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})

    groupe = paie_service.calculer_paie_groupe(p.id, [e1.id, 9999])  # 9999 = inexistant

    assert len(groupe.resultats) == 1
    assert groupe.resultats[0].enseignant_id == e1.id
    assert groupe.resultats[0].gain_heures == 10000
    assert 9999 in groupe.erreurs


# ---------------------------------------------------------------------
# Totaux groupés
# ---------------------------------------------------------------------

def test_totaux_groupe_corrects():
    e1 = _creer_enseignant(nom="Traore", prenom="Salif", taux_horaire=1000)
    e2 = _creer_enseignant(nom="Diallo", prenom="Aicha", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10}, prime_ap_pp=1000, retenue_amicale=500)
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 20}, prime_ap_pp=2000, dette=300)

    groupe = paie_service.calculer_paie_groupe(p.id, [e1.id, e2.id])
    totaux = paie_service.calculer_totaux_groupe(groupe.resultats)

    assert totaux.total_heures == 30
    assert totaux.total_gain_heures == 10000 + 20000
    assert totaux.total_primes == 1000 + 2000
    assert totaux.total_retenues == 500 + 300
    assert totaux.total_net_a_percevoir == sum(r.net_a_percevoir for r in groupe.resultats)


def test_totaux_groupe_liste_vide():
    totaux = paie_service.calculer_totaux_groupe([])
    assert totaux.total_heures == 0
    assert totaux.total_net_a_percevoir == 0
