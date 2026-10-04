"""
Tests de services/statistiques_service.py (module 17) — statistiques
générales et statistique descriptive de base.
"""

import pytest

import database.connection as database_connection
from services import controle_paie_service, donnees_paie_service, enseignant_service, periode_service, statistiques_service
from services.donnees_paie_service import DonneesPaieEnseignant

# Cas de référence officiel : vacataire, taxe de 5 %.
pytestmark = pytest.mark.taxe_historique


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Kamgang", "prenom": "Jean", "sexe": "M", "statut": "V", "taux_horaire": 2000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _periode_ouverte(mois=1, annee=2095):
    p = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(p.id)


def _saisir(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)])


# ---------------------------------------------------------------------
# Statistique descriptive — robustesse (section 10/21)
# ---------------------------------------------------------------------

def test_statistique_descriptive_liste_vide():
    stats = statistiques_service.calculer_statistique_descriptive([])
    assert stats.nombre == 0
    assert stats.moyenne is None
    assert stats.ecart_type is None


def test_statistique_descriptive_une_seule_valeur():
    stats = statistiques_service.calculer_statistique_descriptive([100.0])
    assert stats.nombre == 1
    assert stats.moyenne == 100.0
    assert stats.mediane == 100.0
    assert stats.ecart_type is None  # non défini mathématiquement pour n=1
    assert stats.premier_quartile is None  # nécessite au moins 4 observations


def test_statistique_descriptive_valeurs_identiques():
    stats = statistiques_service.calculer_statistique_descriptive([50.0, 50.0, 50.0, 50.0])
    assert stats.moyenne == 50.0
    assert stats.ecart_type == 0.0


def test_statistique_descriptive_calculs_corrects():
    stats = statistiques_service.calculer_statistique_descriptive([10.0, 20.0, 30.0, 40.0])
    assert stats.nombre == 4
    assert stats.total == 100.0
    assert stats.moyenne == 25.0
    assert stats.minimum == 10.0
    assert stats.maximum == 40.0
    assert stats.premier_quartile is not None
    assert stats.troisieme_quartile is not None


# ---------------------------------------------------------------------
# Statistiques générales (section 6)
# ---------------------------------------------------------------------

def test_statistiques_generales_effectifs():
    _creer_enseignant(nom="A", prenom="A", statut="P", sexe="M")
    _creer_enseignant(nom="B", prenom="B", statut="V", sexe="F")
    p = _periode_ouverte()
    stats = statistiques_service.statistiques_generales(p.id)
    assert stats.nombre_enseignants_total == 2
    assert stats.nombre_permanents == 1
    assert stats.nombre_vacataires == 1
    assert stats.nombre_hommes == 1
    assert stats.nombre_femmes == 1


def test_statistiques_generales_heures_remuneration():
    e = _creer_enseignant(taux_horaire=2000)
    p = _periode_ouverte()
    _saisir(p.id, e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20}, prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000, retenue_amicale=5000, dette=10000)
    stats = statistiques_service.statistiques_generales(p.id)
    assert stats.heures.moyenne == 100.0
    assert stats.total_net == 208250
    assert stats.total_taxe == 11750


def test_statistiques_generales_periode_sans_donnee_ne_plante_pas():
    _creer_enseignant()
    p = _periode_ouverte()
    stats = statistiques_service.statistiques_generales(p.id)
    assert stats.nombre_enseignants_total == 1
    assert stats.heures.nombre == 0
    assert stats.total_net == 0


def test_statistiques_generales_aucun_enseignant():
    p = _periode_ouverte()
    stats = statistiques_service.statistiques_generales(p.id)
    assert stats.nombre_enseignants_total == 0
    assert stats.heures.nombre == 0


# ---------------------------------------------------------------------
# Composantes de la paie (section 9)
# ---------------------------------------------------------------------

def test_analyser_composantes():
    e = _creer_enseignant(taux_horaire=2000)
    p = _periode_ouverte()
    _saisir(p.id, e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20}, prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000)
    from services.comptabilite_service import preparer_etat_comptable
    etat = preparer_etat_comptable(p.id)
    composantes = statistiques_service.analyser_composantes(etat.resultats)

    gain = next(c for c in composantes if c.libelle == "Gain horaire")
    assert gain.montant_total == 200000
    assert gain.part_pourcentage is not None


def test_analyser_composantes_liste_vide_ne_divise_pas_par_zero():
    composantes = statistiques_service.analyser_composantes([])
    for c in composantes:
        assert c.montant_total == 0
        assert c.part_pourcentage is None  # total brut nul -> jamais de division par zéro


# ---------------------------------------------------------------------
# Aucune formule de paie dupliquée
# ---------------------------------------------------------------------

def test_aucune_formule_de_paie_dans_statistiques_service():
    import inspect
    from services import statistiques_service as module
    source = inspect.getsource(module)
    assert "* 0.05" not in source
    assert "TAUX_TAXE" not in source
    assert "taux_horaire *" not in source
