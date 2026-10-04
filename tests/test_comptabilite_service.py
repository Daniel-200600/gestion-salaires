"""
Tests du service comptable (services/comptabilite_service.py).

Vérifie la préparation des données (sans jamais recalculer la paie),
l'agrégation des totaux, la séparation par statut, et la gestion des
cas limites (période vide, données manquantes, période non prête).
"""

import inspect

import pytest

import database.connection as database_connection
from services import (
    comptabilite_service,
    donnees_paie_service,
    enseignant_service,
    paie_service,
    periode_service,
)
from services.comptabilite_service import ComptabiliteError
from services.donnees_paie_service import DonneesPaieEnseignant

# Cas de référence officiel : vacataire, taxe de 5 %.
pytestmark = pytest.mark.taxe_historique


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Diarra", "prenom": "Moussa", "sexe": "M", "statut": "V", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=1, annee=2030):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


# ---------------------------------------------------------------------
# 1 & 2. Récupération correcte des enseignants et des résultats de paie
# ---------------------------------------------------------------------

def test_recuperation_correcte_enseignants_et_resultats():
    e1 = _creer_enseignant(nom="Diarra", prenom="Moussa", taux_horaire=1000)
    e2 = _creer_enseignant(nom="Kone", prenom="Aminata", taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 5})

    etat = comptabilite_service.preparer_etat_comptable(p.id)

    ids_resultats = {r.enseignant_id for r in etat.resultats}
    assert ids_resultats == {e1.id, e2.id}

    resultats_par_id = {r.enseignant_id: r for r in etat.resultats}
    assert resultats_par_id[e1.id].gain_heures == 10000
    assert resultats_par_id[e2.id].gain_heures == 10000  # 5 * 2000


# ---------------------------------------------------------------------
# 3. Calcul correct du nombre d'enseignants
# ---------------------------------------------------------------------

def test_nombre_enseignants_correct():
    enseignants = [_creer_enseignant(nom=f"Ens{i}", prenom=f"P{i}") for i in range(5)]
    p = _creer_periode_ouverte()
    for e in enseignants:
        _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})

    etat = comptabilite_service.preparer_etat_comptable(p.id)
    assert len(etat.resultats) == 5


# ---------------------------------------------------------------------
# 4. Agrégation correcte des totaux
# ---------------------------------------------------------------------

def test_agregation_totaux_correcte():
    e1 = _creer_enseignant(taux_horaire=1000)
    e2 = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10}, prime_ap_pp=1000, retenue_amicale=200)
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 20}, prime_ap_pp=2000, dette=300)

    etat = comptabilite_service.preparer_etat_comptable(p.id)

    assert etat.totaux.total_heures == 30
    assert etat.totaux.total_gain_heures == 10000 + 20000
    assert etat.totaux.total_prime_ap_pp == 1000 + 2000
    assert etat.totaux.total_retenue_amicale == 200
    assert etat.totaux.total_dette == 300
    assert etat.totaux.total_net_a_percevoir == sum(r.net_a_percevoir for r in etat.resultats)


# ---------------------------------------------------------------------
# 5. Séparation permanent/vacataire
# ---------------------------------------------------------------------

def test_separation_permanent_vacataire():
    e_permanent = _creer_enseignant(nom="Diarra", prenom="Moussa", statut="P", taux_horaire=1000)
    e_vacataire1 = _creer_enseignant(nom="Kone", prenom="Aminata", statut="V", taux_horaire=1000)
    e_vacataire2 = _creer_enseignant(nom="Traore", prenom="Ibrahim", statut="V", taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e_permanent.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e_vacataire1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e_vacataire2.id, heures_par_semaine={1: 10})

    etat = comptabilite_service.preparer_etat_comptable(p.id)
    synthese_par_statut = {item.statut.value: item for item in etat.synthese_par_statut}

    assert synthese_par_statut["P"].nombre == 1
    assert synthese_par_statut["V"].nombre == 2
    assert synthese_par_statut["V"].total_net == sum(
        r.net_a_percevoir for r in etat.resultats if r.statut.value == "V"
    )


# ---------------------------------------------------------------------
# 6. Gestion d'une période vide (aucun enseignant avec données)
# ---------------------------------------------------------------------

def test_periode_sans_aucun_enseignant():
    p = _creer_periode_ouverte()  # aucune donnée saisie
    with pytest.raises(ComptabiliteError, match="Aucun enseignant"):
        comptabilite_service.preparer_etat_comptable(p.id)


def test_periode_brouillon_refusee():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=2, annee=2030)  # reste en brouillon
    with pytest.raises(ComptabiliteError, match="Brouillon"):
        comptabilite_service.preparer_etat_comptable(p.id)


def test_periode_inexistante():
    with pytest.raises(ComptabiliteError):
        comptabilite_service.preparer_etat_comptable(9999)


# ---------------------------------------------------------------------
# 7. Gestion d'une donnée manquante (enseignant demandé explicitement sans données)
# ---------------------------------------------------------------------

def test_enseignant_sans_donnees_dans_liste_explicite():
    """Un enseignant explicitement demandé mais sans aucune saisie retourne un résultat à zéro, pas une erreur."""
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    etat = comptabilite_service.preparer_etat_comptable(p.id, enseignant_ids=[e.id])
    assert len(etat.resultats) == 1
    assert etat.resultats[0].net_a_percevoir == 0


def test_enseignant_inexistant_dans_liste_explicite_isole_en_erreur():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})

    etat = comptabilite_service.preparer_etat_comptable(p.id, enseignant_ids=[e.id, 9999])
    assert len(etat.resultats) == 1
    assert 9999 in etat.erreurs


# ---------------------------------------------------------------------
# 8. Le service ne recalcule pas la paie (délègue à paie_service)
# ---------------------------------------------------------------------

def test_service_ne_recalcule_pas_la_paie():
    """
    Vérifie par inspection du code source qu'aucune formule de paie
    (multiplication du taux horaire, taxe 5 %, etc.) n'est écrite
    directement dans comptabilite_service : il doit uniquement
    déléguer à paie_service.calculer_paie_groupe /
    calculer_totaux_groupe.
    """
    source = inspect.getsource(comptabilite_service)
    assert "calculer_paie_groupe" in source
    assert "calculer_totaux_groupe" in source
    # Aucune trace d'une formule de paie recodée ici
    assert "* 0.05" not in source
    assert "taux_horaire *" not in source
    assert "TAUX_TAXE" not in source


def test_resultats_identiques_a_paie_service_direct():
    """L'état comptable doit produire EXACTEMENT les mêmes résultats qu'un appel direct à paie_service."""
    e = _creer_enseignant(taux_horaire=2000)
    p = _creer_periode_ouverte()
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )

    resultat_direct = paie_service.calculer_paie_enseignant(p.id, e.id)
    etat = comptabilite_service.preparer_etat_comptable(p.id)
    resultat_comptable = etat.resultats[0]

    assert resultat_comptable.net_a_percevoir == resultat_direct.net_a_percevoir == 208250
    assert resultat_comptable.taxe_5 == resultat_direct.taxe_5
    assert resultat_comptable.base_taxable == resultat_direct.base_taxable
    assert resultat_comptable.gain_heures == resultat_direct.gain_heures


# ---------------------------------------------------------------------
# Cas complémentaires
# ---------------------------------------------------------------------

def test_resultats_tries_par_nom_prenom():
    e_z = _creer_enseignant(nom="Zabo", prenom="Ali")
    e_a = _creer_enseignant(nom="Abou", prenom="Ali")
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e_z.id, heures_par_semaine={1: 1})
    _saisir_donnees(p.id, e_a.id, heures_par_semaine={1: 1})

    etat = comptabilite_service.preparer_etat_comptable(p.id)
    noms = [r.nom for r in etat.resultats]
    assert noms == sorted(noms)


def test_periode_ouverte_calculable_en_previsualisation():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    etat = comptabilite_service.preparer_etat_comptable(p.id)
    assert etat.periode.statut.value == "ouverte"


def test_periode_cloturee_calculable():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    p = periode_service.cloturer_periode(p.id)
    etat = comptabilite_service.preparer_etat_comptable(p.id)
    assert etat.resultats[0].gain_heures == 10000
