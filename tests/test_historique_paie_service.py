"""
Tests du service historique de paie (services/historique_paie_service.py).

Couvre : récupération d'un historique enseignant, plusieurs périodes,
absence de données, période clôturée, et l'absence de duplication de
formule de paie.
"""

import inspect

import pytest

import database.connection as database_connection
from services import donnees_paie_service, enseignant_service, historique_paie_service, periode_service
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Ateba", "prenom": "Sylvie", "sexe": "F", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois, annee=2034):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


# ---------------------------------------------------------------------
# Récupération d'un historique enseignant
# ---------------------------------------------------------------------

def test_historique_une_periode():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte(mois=1)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    historique = historique_paie_service.historique_enseignant(e.id)
    assert len(historique) == 1
    assert historique[0].resultat.gain_heures == 10000
    assert historique[0].periode_id == p.id


# ---------------------------------------------------------------------
# Plusieurs périodes, triées chronologiquement
# ---------------------------------------------------------------------

def test_historique_plusieurs_periodes_ordre_chronologique():
    e = _creer_enseignant(taux_horaire=1000)
    p_aout = _creer_periode_ouverte(mois=8)
    p_juin = _creer_periode_ouverte(mois=6)
    p_juillet = _creer_periode_ouverte(mois=7)

    _saisir_donnees(p_aout.id, e.id, heures_par_semaine={1: 30})
    _saisir_donnees(p_juin.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p_juillet.id, e.id, heures_par_semaine={1: 20})

    for p in (p_aout, p_juin, p_juillet):
        periode_service.valider_periode(p.id)

    historique = historique_paie_service.historique_enseignant(e.id)
    mois_ordonnes = [historique_paie_service.lister_periodes if False else None]  # no-op, garde la lisibilité
    libelles = [h.libelle_periode for h in historique]
    assert libelles == sorted(libelles, key=lambda lib: (2034, ["Juin", "Juillet", "Août"].index(lib.split()[0])))
    assert len(historique) == 3
    assert historique[0].resultat.gain_heures == 10000  # juin
    assert historique[1].resultat.gain_heures == 20000  # juillet
    assert historique[2].resultat.gain_heures == 30000  # août


def test_historique_selection_de_periodes_precises():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=1)
    p2 = _creer_periode_ouverte(mois=2)
    p3 = _creer_periode_ouverte(mois=3)
    for p, heures in ((p1, 10), (p2, 20), (p3, 30)):
        _saisir_donnees(p.id, e.id, heures_par_semaine={1: heures})
        periode_service.valider_periode(p.id)

    historique = historique_paie_service.historique_enseignant(e.id, periode_ids=[p1.id, p3.id])
    assert len(historique) == 2
    assert {h.periode_id for h in historique} == {p1.id, p3.id}


# ---------------------------------------------------------------------
# Absence de données
# ---------------------------------------------------------------------

def test_absence_de_donnees_periode_ignoree_par_defaut():
    e = _creer_enseignant()
    p = _creer_periode_ouverte(mois=1)
    periode_service.valider_periode(p.id)  # aucune saisie

    historique = historique_paie_service.historique_enseignant(e.id)
    assert historique == []


def test_absence_de_donnees_incluse_si_demande():
    e = _creer_enseignant()
    p = _creer_periode_ouverte(mois=1)
    periode_service.valider_periode(p.id)

    historique = historique_paie_service.historique_enseignant(e.id, inclure_periodes_sans_donnees=True)
    assert len(historique) == 1
    assert historique[0].resultat.net_a_percevoir == 0


def test_aucune_periode_du_tout():
    e = _creer_enseignant()
    historique = historique_paie_service.historique_enseignant(e.id)
    assert historique == []


# ---------------------------------------------------------------------
# Période clôturée
# ---------------------------------------------------------------------

def test_historique_inclut_periode_cloturee_sans_la_modifier():
    e = _creer_enseignant(taux_horaire=1000)
    p = _creer_periode_ouverte(mois=1)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    p = periode_service.cloturer_periode(p.id)

    historique = historique_paie_service.historique_enseignant(e.id)
    assert len(historique) == 1
    assert historique[0].resultat.gain_heures == 10000

    # La période reste bien clôturée après consultation (non modifiée).
    periode_relue = periode_service.obtenir_periode(p.id)
    assert periode_relue.statut.value == "cloturee"


def test_periode_brouillon_exclue_de_lhistorique():
    e = _creer_enseignant()
    periode_service.creer_periode(mois=9, annee=2034)  # reste en brouillon
    historique = historique_paie_service.historique_enseignant(e.id)
    assert historique == []


# ---------------------------------------------------------------------
# Totaux de l'historique
# ---------------------------------------------------------------------

def test_totaux_historique_corrects():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=1)
    p2 = _creer_periode_ouverte(mois=2)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 20})
    periode_service.valider_periode(p1.id)
    periode_service.valider_periode(p2.id)

    historique = historique_paie_service.historique_enseignant(e.id)
    totaux = historique_paie_service.totaux_historique(historique)
    assert totaux.total_gain_heures == 30000
    assert totaux.total_heures == 30


def test_totaux_historique_vide():
    totaux = historique_paie_service.totaux_historique([])
    assert totaux.total_net_a_percevoir == 0


# ---------------------------------------------------------------------
# Isolation entre enseignants
# ---------------------------------------------------------------------

def test_historique_isole_par_enseignant():
    e1 = _creer_enseignant(nom="Ateba", prenom="Sylvie", taux_horaire=1000)
    e2 = _creer_enseignant(nom="Biya", prenom="Rene", taux_horaire=5000)
    p = _creer_periode_ouverte(mois=1)
    _saisir_donnees(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir_donnees(p.id, e2.id, heures_par_semaine={1: 10})
    periode_service.valider_periode(p.id)

    historique_e1 = historique_paie_service.historique_enseignant(e1.id)
    historique_e2 = historique_paie_service.historique_enseignant(e2.id)

    assert historique_e1[0].resultat.gain_heures == 10000
    assert historique_e2[0].resultat.gain_heures == 50000


# ---------------------------------------------------------------------
# Aucune duplication de formule de paie
# ---------------------------------------------------------------------

def test_aucune_formule_de_paie_dans_historique_service():
    from services import historique_paie_service as module
    source = inspect.getsource(module)
    assert "* 0.05" not in source
    assert "TAUX_TAXE" not in source
    assert "taux_horaire *" not in source


# ---------------------------------------------------------------------
# Comparaison entre deux périodes (module 09)
# ---------------------------------------------------------------------

def test_comparer_periodes_ecarts_corrects():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=1)
    p2 = _creer_periode_ouverte(mois=2)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 20})
    periode_service.valider_periode(p1.id)
    periode_service.valider_periode(p2.id)

    comparaison = historique_paie_service.comparer_periodes(p1.id, p2.id)

    indicateur_gain = next(i for i in comparaison.indicateurs if i.libelle == "Total gains")
    assert indicateur_gain.valeur_a == 10000
    assert indicateur_gain.valeur_b == 20000
    assert indicateur_gain.variation_absolue == 10000
    assert indicateur_gain.variation_pourcentage == 100.0


def test_comparer_periodes_pourcentage_none_si_reference_nulle():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=1)
    p2 = _creer_periode_ouverte(mois=2)
    _saisir_donnees(p1.id, e.id, prime_ap_pp=0)  # aucune heure, gain=0
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 10})
    periode_service.valider_periode(p1.id)
    periode_service.valider_periode(p2.id)

    comparaison = historique_paie_service.comparer_periodes(p1.id, p2.id)
    indicateur_gain = next(i for i in comparaison.indicateurs if i.libelle == "Total gains")
    assert indicateur_gain.valeur_a == 0
    assert indicateur_gain.variation_pourcentage is None


def test_comparer_periodes_identifie_bien_les_periodes():
    e = _creer_enseignant(taux_horaire=1000)
    p1 = _creer_periode_ouverte(mois=3)
    p2 = _creer_periode_ouverte(mois=4)
    _saisir_donnees(p1.id, e.id, heures_par_semaine={1: 10})
    _saisir_donnees(p2.id, e.id, heures_par_semaine={1: 10})
    periode_service.valider_periode(p1.id)
    periode_service.valider_periode(p2.id)

    comparaison = historique_paie_service.comparer_periodes(p1.id, p2.id)
    assert comparaison.periode_a.id == p1.id
    assert comparaison.periode_b.id == p2.id


def test_comparer_periodes_sans_donnees_leve_erreur():
    from services.comptabilite_service import ComptabiliteError
    p1 = _creer_periode_ouverte(mois=5)
    p2 = _creer_periode_ouverte(mois=6)
    with pytest.raises(ComptabiliteError):
        historique_paie_service.comparer_periodes(p1.id, p2.id)
