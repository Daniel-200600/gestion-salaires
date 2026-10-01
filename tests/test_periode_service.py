"""
Tests du module 03 : gestion des périodes de paie (service + repository).

Même convention que test_enseignant_service.py : le service et le
repository appellent get_connection() SANS argument explicite dans les
tests (usage normal). Le fixture `_rediriger_connexion_par_defaut`
redirige `database.connection.DB_PATH` vers la base temporaire créée
par le fixture `db_path` (tests/conftest.py).
"""

import pytest

import database.connection as database_connection
from models.enums import StatutPeriode
from services import periode_service
from services.periode_service import PeriodeValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _creer_periode_valide(**overrides):
    donnees = {"mois": 10, "annee": 2026}
    donnees.update(overrides)
    return periode_service.creer_periode(**donnees)


# ---------------------------------------------------------------------
# 1-2. Création d'une période valide / Août 2026
# ---------------------------------------------------------------------

def test_creation_periode_valide():
    periode = _creer_periode_valide()
    assert periode.id is not None
    assert periode.mois == 10
    assert periode.annee == 2026
    assert periode.libelle == "Octobre 2026"


def test_creation_periode_aout_2026():
    periode = periode_service.creer_periode(mois=8, annee=2026)
    assert periode.libelle == "Août 2026"
    assert periode.mois == 8
    assert periode.annee == 2026


# ---------------------------------------------------------------------
# 3-6. Refus des données invalides
# ---------------------------------------------------------------------

def test_refus_mois_zero():
    with pytest.raises(PeriodeValidationError):
        _creer_periode_valide(mois=0)


def test_refus_mois_13():
    with pytest.raises(PeriodeValidationError):
        _creer_periode_valide(mois=13)


def test_refus_annee_invalide():
    with pytest.raises(PeriodeValidationError):
        _creer_periode_valide(annee=1500)


def test_refus_annee_non_numerique():
    with pytest.raises(PeriodeValidationError):
        _creer_periode_valide(annee="abc")


def test_refus_periode_dupliquee():
    _creer_periode_valide(mois=8, annee=2026)
    with pytest.raises(PeriodeValidationError):
        _creer_periode_valide(mois=8, annee=2026)


# ---------------------------------------------------------------------
# 7. Statut initial BROUILLON
# ---------------------------------------------------------------------

def test_statut_initial_brouillon():
    periode = _creer_periode_valide()
    assert periode.statut == StatutPeriode.BROUILLON
    assert periode.date_cloture is None


# ---------------------------------------------------------------------
# 8-10. Transitions autorisées
# ---------------------------------------------------------------------

def test_transition_brouillon_vers_ouverte():
    periode = _creer_periode_valide()
    ouverte = periode_service.ouvrir_periode(periode.id)
    assert ouverte.statut == StatutPeriode.OUVERTE


def test_transition_ouverte_vers_validee():
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    validee = periode_service.valider_periode(periode.id)
    assert validee.statut == StatutPeriode.VALIDEE


def test_transition_validee_vers_cloturee():
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    periode_service.valider_periode(periode.id)
    cloturee = periode_service.cloturer_periode(periode.id)
    assert cloturee.statut == StatutPeriode.CLOTUREE


# ---------------------------------------------------------------------
# 11. Refus des transitions illégales
# ---------------------------------------------------------------------

def test_refus_validation_depuis_brouillon():
    """On ne peut pas valider une période qui n'a pas été ouverte."""
    periode = _creer_periode_valide()
    with pytest.raises(PeriodeValidationError):
        periode_service.valider_periode(periode.id)


def test_refus_cloture_depuis_brouillon():
    periode = _creer_periode_valide()
    with pytest.raises(PeriodeValidationError):
        periode_service.cloturer_periode(periode.id)


def test_refus_cloture_depuis_ouverte():
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    with pytest.raises(PeriodeValidationError):
        periode_service.cloturer_periode(periode.id)


def test_refus_ouverture_deux_fois():
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    with pytest.raises(PeriodeValidationError):
        periode_service.ouvrir_periode(periode.id)


def test_refus_retour_arriere_validee_vers_ouverte():
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    periode_service.valider_periode(periode.id)
    with pytest.raises(PeriodeValidationError):
        periode_service.ouvrir_periode(periode.id)


# ---------------------------------------------------------------------
# 12. Impossibilité de modifier une période clôturée
# ---------------------------------------------------------------------

def test_impossible_modifier_periode_cloturee():
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    periode_service.valider_periode(periode.id)
    periode_service.cloturer_periode(periode.id)
    with pytest.raises(PeriodeValidationError):
        periode_service.modifier_periode(periode.id, mois=11, annee=2026)


def test_impossible_modifier_periode_ouverte():
    """Le mois/l'année ne doivent plus être modifiables une fois la période ouverte."""
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    with pytest.raises(PeriodeValidationError):
        periode_service.modifier_periode(periode.id, mois=11, annee=2026)


def test_modification_autorisee_en_brouillon():
    periode = _creer_periode_valide(mois=10, annee=2026)
    modifiee = periode_service.modifier_periode(periode.id, mois=11, annee=2026)
    assert modifiee.mois == 11
    assert modifiee.libelle == "Novembre 2026"


# ---------------------------------------------------------------------
# 13-14. Date de clôture
# ---------------------------------------------------------------------

def test_date_cloture_renseignee_lors_cloture():
    periode = _creer_periode_valide()
    periode_service.ouvrir_periode(periode.id)
    periode_service.valider_periode(periode.id)
    cloturee = periode_service.cloturer_periode(periode.id)
    assert cloturee.date_cloture is not None


def test_date_cloture_absente_avant_cloture():
    periode = _creer_periode_valide()
    assert periode.date_cloture is None

    ouverte = periode_service.ouvrir_periode(periode.id)
    assert ouverte.date_cloture is None

    validee = periode_service.valider_periode(periode.id)
    assert validee.date_cloture is None


# ---------------------------------------------------------------------
# 15. Liste des périodes triée correctement
# ---------------------------------------------------------------------

def test_liste_periodes_triee_correctement():
    """Tri par année puis mois décroissants (la période la plus récente en premier)."""
    periode_service.creer_periode(mois=3, annee=2026)
    periode_service.creer_periode(mois=8, annee=2026)
    periode_service.creer_periode(mois=1, annee=2027)
    periode_service.creer_periode(mois=12, annee=2025)

    periodes = periode_service.lister_periodes()
    libelles = [p.libelle for p in periodes]

    assert libelles == ["Janvier 2027", "Août 2026", "Mars 2026", "Décembre 2025"]


def test_filtre_par_annee():
    periode_service.creer_periode(mois=3, annee=2026)
    periode_service.creer_periode(mois=8, annee=2026)
    periode_service.creer_periode(mois=1, annee=2027)

    resultats = periode_service.lister_periodes(annee=2026)
    assert len(resultats) == 2
    assert all(p.annee == 2026 for p in resultats)


def test_filtre_par_statut():
    p1 = periode_service.creer_periode(mois=3, annee=2026)
    periode_service.creer_periode(mois=8, annee=2026)
    periode_service.ouvrir_periode(p1.id)

    resultats_ouvertes = periode_service.lister_periodes(statut=StatutPeriode.OUVERTE)
    resultats_brouillon = periode_service.lister_periodes(statut=StatutPeriode.BROUILLON)

    assert len(resultats_ouvertes) == 1
    assert resultats_ouvertes[0].id == p1.id
    assert len(resultats_brouillon) == 1


# ---------------------------------------------------------------------
# Divers : période introuvable
# ---------------------------------------------------------------------

def test_periode_introuvable():
    with pytest.raises(PeriodeValidationError):
        periode_service.obtenir_periode(9999)


def test_ouverture_periode_introuvable():
    with pytest.raises(PeriodeValidationError):
        periode_service.ouvrir_periode(9999)
