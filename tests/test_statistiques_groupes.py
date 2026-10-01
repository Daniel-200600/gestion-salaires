"""
Tests de statistiques par groupe, croisement statut×sexe, détection
de valeurs atypiques et analyse individuelle (module 17).
"""

import pytest

import database.connection as database_connection
from services import (
    controle_paie_service,
    donnees_paie_service,
    enseignant_service,
    periode_service,
    statistiques_service,
)
from services.comptabilite_service import preparer_etat_comptable
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "X", "prenom": "X", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _periode_ouverte(mois=1, annee=2097):
    p = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(p.id)


def _saisir(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)])


# ---------------------------------------------------------------------
# Croisement statut × sexe (section 7)
# ---------------------------------------------------------------------

def test_croisement_statut_sexe():
    e1 = _creer_enseignant(nom="A", prenom="A", statut="P", sexe="M")
    e2 = _creer_enseignant(nom="B", prenom="B", statut="P", sexe="F")
    e3 = _creer_enseignant(nom="C", prenom="C", statut="V", sexe="M")
    p = _periode_ouverte()
    for e in (e1, e2, e3):
        _saisir(p.id, e.id, heures_par_semaine={1: 10})

    etat = preparer_etat_comptable(p.id)
    groupes = statistiques_service.synthese_croisee_statut_sexe(etat.resultats)
    libelles = {g.libelle: g.nombre for g in groupes}
    assert libelles["Permanent — Masculin"] == 1
    assert libelles["Permanent — Féminin"] == 1
    assert libelles["Vacataire — Masculin"] == 1


def test_croisement_groupe_vide_ne_plante_pas():
    assert statistiques_service.synthese_croisee_statut_sexe([]) == []


# ---------------------------------------------------------------------
# Détection de valeurs atypiques — IQR (section 11)
# ---------------------------------------------------------------------

def test_outlier_detecte_avec_donnees_suffisantes():
    ids = []
    for i, taux in enumerate([1000, 1100, 1050, 1080, 50000]):
        e = _creer_enseignant(nom=f"E{i}", prenom="X", taux_horaire=taux)
        ids.append(e.id)
    p = _periode_ouverte()
    for eid in ids:
        _saisir(p.id, eid, heures_par_semaine={1: 10})

    etat = preparer_etat_comptable(p.id)
    outliers = statistiques_service.detecter_valeurs_atypiques(etat.resultats, "taux_horaire")
    assert len(outliers) == 1
    assert outliers[0].niveau == "À vérifier"


def test_aucun_outlier_si_valeurs_homogenes():
    ids = []
    for i, taux in enumerate([1000, 1010, 1020, 1030, 1040]):
        e = _creer_enseignant(nom=f"E{i}", prenom="X", taux_horaire=taux)
        ids.append(e.id)
    p = _periode_ouverte()
    for eid in ids:
        _saisir(p.id, eid, heures_par_semaine={1: 10})

    etat = preparer_etat_comptable(p.id)
    outliers = statistiques_service.detecter_valeurs_atypiques(etat.resultats, "taux_horaire")
    assert outliers == []


def test_outlier_donnees_insuffisantes_retourne_liste_vide():
    """Moins de 4 observations : aucune détection plutôt qu'un faux positif."""
    e = _creer_enseignant()
    p = _periode_ouverte()
    _saisir(p.id, e.id, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)
    assert statistiques_service.detecter_valeurs_atypiques(etat.resultats, "taux_horaire") == []


def test_outlier_champ_invalide_leve():
    with pytest.raises(ValueError):
        statistiques_service.detecter_valeurs_atypiques([], "champ_inexistant")


def test_outlier_terminologie_prudente():
    """Le niveau ne doit jamais qualifier la valeur d'erreur — seulement une invitation à vérifier."""
    ids = []
    for i, taux in enumerate([1000, 1100, 1050, 1080, 99999]):
        e = _creer_enseignant(nom=f"F{i}", prenom="X", taux_horaire=taux)
        ids.append(e.id)
    p = _periode_ouverte()
    for eid in ids:
        _saisir(p.id, eid, heures_par_semaine={1: 10})
    etat = preparer_etat_comptable(p.id)
    outliers = statistiques_service.detecter_valeurs_atypiques(etat.resultats, "taux_horaire")
    for o in outliers:
        assert "erreur" not in o.niveau.lower()


# ---------------------------------------------------------------------
# Analyse individuelle (section 12)
# ---------------------------------------------------------------------

def test_comparaison_enseignant_au_groupe():
    e1 = _creer_enseignant(nom="A", prenom="A", taux_horaire=1000)
    e2 = _creer_enseignant(nom="B", prenom="B", taux_horaire=3000)
    p = _periode_ouverte()
    _saisir(p.id, e1.id, heures_par_semaine={1: 10})
    _saisir(p.id, e2.id, heures_par_semaine={1: 10})

    etat = preparer_etat_comptable(p.id)
    resultat_e2 = next(r for r in etat.resultats if r.nom == "B")
    ecarts = statistiques_service.comparer_enseignant_au_groupe(resultat_e2, etat.resultats)

    ecart_taux = next(e for e in ecarts if e.libelle == "Taux horaire")
    assert ecart_taux.valeur_enseignant == 3000
    assert ecart_taux.ecart_absolu > 0  # au-dessus de la moyenne du groupe
    assert ecart_taux.ecart_pourcentage is not None


def test_comparaison_groupe_vide_retourne_liste_vide():
    from models.resultat_paie import ResultatPaie
    from models.enums import Sexe, StatutEnseignant
    resultat_factice = ResultatPaie(
        enseignant_id=1, periode_id=1, nom="Test", prenom="Test", sexe=Sexe.HOMME, statut=StatutEnseignant.PERMANENT,
        taux_horaire=1000, semaine_1=0, semaine_2=0, semaine_3=0, semaine_4=0, semaine_5=0, total_heures=0,
        gain_heures=0, prime_ap_pp=0, surveillance_secretariat=0, indemnite_suggestion_admin=0,
        base_taxable=0, taxe_5=0, retenue_amicale=0, dette=0, net_a_percevoir=0,
    )
    assert statistiques_service.comparer_enseignant_au_groupe(resultat_factice, []) == []


def test_comparaison_moyenne_groupe_nulle_pas_de_division_par_zero():
    """Si la moyenne du groupe est nulle pour un champ, l'écart % doit rester None."""
    e1 = _creer_enseignant(nom="A", prenom="A", taux_horaire=1000)
    p = _periode_ouverte()
    _saisir(p.id, e1.id, heures_par_semaine={1: 0})  # 0 heure -> gain nul
    etat = preparer_etat_comptable(p.id)
    if etat.resultats:
        ecarts = statistiques_service.comparer_enseignant_au_groupe(etat.resultats[0], etat.resultats)
        ecart_gain = next((e for e in ecarts if e.libelle == "Gain"), None)
        if ecart_gain and ecart_gain.valeur_groupe == 0:
            assert ecart_gain.ecart_pourcentage is None
