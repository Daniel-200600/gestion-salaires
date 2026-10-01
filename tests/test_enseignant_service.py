"""
Tests du module 02 : gestion des enseignants (service + repository).

Le service et le repository appellent get_connection() SANS argument
(usage normal en dehors des tests). Pour les isoler de la vraie base
de l'application, le fixture `_rediriger_connexion_par_defaut`
redirige `database.connection.DB_PATH` vers la base temporaire créée
par le fixture `db_path` (tests/conftest.py) — sans modifier ce
fixture existant.
"""

import inspect

import pytest

import database.connection as database_connection
import database.repositories.enseignant_repository as enseignant_repository
from services import enseignant_service
from services.enseignant_service import EnseignantValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _creer_enseignant_valide(**overrides):
    donnees = {
        "nom": "Traoré",
        "prenom": "Aminata",
        "sexe": "F",
        "statut": "P",
        "taux_horaire": 1500,
    }
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


# ---------------------------------------------------------------------
# 1. Création d'un enseignant valide
# ---------------------------------------------------------------------

def test_creation_enseignant_valide():
    enseignant = _creer_enseignant_valide()
    assert enseignant.id is not None
    assert enseignant.nom == "Traoré"
    assert enseignant.prenom == "Aminata"
    assert enseignant.actif is True
    assert enseignant.taux_horaire == 1500


# ---------------------------------------------------------------------
# 2-6. Refus des données invalides
# ---------------------------------------------------------------------

def test_refus_nom_vide():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(nom="")


def test_refus_nom_uniquement_espaces():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(nom="   ")


def test_refus_prenom_vide():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(prenom="")


def test_refus_sexe_invalide():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(sexe="X")


def test_refus_statut_invalide():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(statut="Q")


def test_refus_taux_negatif():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(taux_horaire=-100)


def test_refus_taux_fractionnaire():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(taux_horaire=1500.75)


def test_refus_taux_manquant():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(taux_horaire=None)


def test_refus_taux_non_numerique():
    with pytest.raises(EnseignantValidationError):
        _creer_enseignant_valide(taux_horaire="abc")


# ---------------------------------------------------------------------
# 7. Acceptation d'un taux entier
# ---------------------------------------------------------------------

def test_acceptation_taux_entier():
    enseignant = _creer_enseignant_valide(taux_horaire=2000)
    assert enseignant.taux_horaire == 2000
    assert isinstance(enseignant.taux_horaire, int)


def test_acceptation_taux_zero():
    enseignant = _creer_enseignant_valide(taux_horaire=0)
    assert enseignant.taux_horaire == 0


# ---------------------------------------------------------------------
# 8. Modification d'un enseignant
# ---------------------------------------------------------------------

def test_modification_enseignant():
    enseignant = _creer_enseignant_valide()
    modifie = enseignant_service.modifier_enseignant(
        enseignant_id=enseignant.id,
        nom="Traoré",
        prenom="Aminata",
        sexe="F",
        statut="V",
        taux_horaire=1800,
        email="aminata.traore@ecole.example",
    )
    assert modifie.statut.value == "V"
    assert modifie.taux_horaire == 1800
    assert modifie.email == "aminata.traore@ecole.example"
    # actif ne doit pas être affecté par une simple modification
    assert modifie.actif is True


def test_modification_rejette_donnees_invalides():
    enseignant = _creer_enseignant_valide()
    with pytest.raises(EnseignantValidationError):
        enseignant_service.modifier_enseignant(
            enseignant_id=enseignant.id,
            nom="",
            prenom="Aminata",
            sexe="F",
            statut="P",
            taux_horaire=1500,
        )


def test_modification_enseignant_inexistant():
    with pytest.raises(EnseignantValidationError):
        enseignant_service.modifier_enseignant(
            enseignant_id=9999,
            nom="Nom",
            prenom="Prenom",
            sexe="M",
            statut="P",
            taux_horaire=1000,
        )


# ---------------------------------------------------------------------
# 9-10. Désactivation / réactivation
# ---------------------------------------------------------------------

def test_desactivation_enseignant():
    enseignant = _creer_enseignant_valide()
    desactive = enseignant_service.desactiver_enseignant(enseignant.id)
    assert desactive.actif is False


def test_reactivation_enseignant():
    enseignant = _creer_enseignant_valide()
    enseignant_service.desactiver_enseignant(enseignant.id)
    reactive = enseignant_service.reactiver_enseignant(enseignant.id)
    assert reactive.actif is True


def test_desactivation_enseignant_inexistant():
    with pytest.raises(EnseignantValidationError):
        enseignant_service.desactiver_enseignant(9999)


def test_enseignant_desactive_absent_liste_par_defaut():
    enseignant = _creer_enseignant_valide()
    enseignant_service.desactiver_enseignant(enseignant.id)
    liste_active = enseignant_service.lister_enseignants()
    assert enseignant.id not in [e.id for e in liste_active]


# ---------------------------------------------------------------------
# 11-12. Recherche
# ---------------------------------------------------------------------

def test_recherche_par_nom():
    _creer_enseignant_valide(nom="Diallo", prenom="Moussa")
    _creer_enseignant_valide(nom="Kane", prenom="Ousmane")
    resultats = enseignant_service.rechercher_enseignants("diallo")
    assert len(resultats) == 1
    assert resultats[0].nom == "Diallo"


def test_recherche_par_prenom():
    _creer_enseignant_valide(nom="Diallo", prenom="Moussa")
    _creer_enseignant_valide(nom="Kane", prenom="Ousmane")
    resultats = enseignant_service.rechercher_enseignants("ousmane")
    assert len(resultats) == 1
    assert resultats[0].prenom == "Ousmane"


def test_recherche_insensible_a_la_casse():
    _creer_enseignant_valide(nom="Camara", prenom="Ibrahim")
    resultats_majuscule = enseignant_service.rechercher_enseignants("CAMARA")
    resultats_minuscule = enseignant_service.rechercher_enseignants("camara")
    assert len(resultats_majuscule) == 1
    assert len(resultats_minuscule) == 1


def test_recherche_nom_complet():
    _creer_enseignant_valide(nom="Sow", prenom="Binta")
    resultats = enseignant_service.rechercher_enseignants("binta sow")
    assert len(resultats) == 1


def test_recherche_sans_resultat():
    _creer_enseignant_valide(nom="Ba", prenom="Cheikh")
    resultats = enseignant_service.rechercher_enseignants("inexistant")
    assert resultats == []


# ---------------------------------------------------------------------
# 13. Un enseignant désactivé reste dans l'historique des données
# ---------------------------------------------------------------------

def test_enseignant_desactive_reste_dans_historique():
    enseignant = _creer_enseignant_valide()
    enseignant_service.desactiver_enseignant(enseignant.id)

    # Toujours consultable individuellement
    toujours_present = enseignant_service.obtenir_enseignant(enseignant.id)
    assert toujours_present is not None
    assert toujours_present.actif is False

    # Toujours présent dans la liste complète (historique)
    liste_complete = enseignant_service.lister_enseignants(inclure_inactifs=True)
    assert enseignant.id in [e.id for e in liste_complete]

    # Toujours trouvable par recherche si on inclut les inactifs
    resultats = enseignant_service.rechercher_enseignants(enseignant.nom, inclure_inactifs=True)
    assert enseignant.id in [e.id for e in resultats]


# ---------------------------------------------------------------------
# 14. Aucune suppression physique n'est utilisée par le service
# ---------------------------------------------------------------------

def test_seule_la_fonction_dediee_supprime_physiquement():
    """
    Depuis l'ajout de la suppression définitive, une fonction DELETE
    existe désormais (`supprimer_enseignant_definitivement` /
    `enseignant_repository.supprimer_definitivement`), mais elle seule.
    Aucune des fonctions ordinaires (création, modification,
    désactivation, réactivation) ne doit jamais supprimer physiquement
    une ligne.
    """
    # La fonction dédiée existe bel et bien, avec ses garde-fous.
    assert hasattr(enseignant_service, "supprimer_enseignant_definitivement")
    assert hasattr(enseignant_repository, "supprimer_definitivement")

    # Aucune autre fonction du service ou du repository ne contient de DELETE.
    fonctions_sans_suppression_service = [
        enseignant_service.creer_enseignant,
        enseignant_service.obtenir_enseignant,
        enseignant_service.lister_enseignants,
        enseignant_service.rechercher_enseignants,
        enseignant_service.modifier_enseignant,
        enseignant_service.desactiver_enseignant,
        enseignant_service.reactiver_enseignant,
    ]
    for fonction in fonctions_sans_suppression_service:
        assert "DELETE FROM" not in inspect.getsource(fonction).upper()

    fonctions_sans_suppression_repository = [
        enseignant_repository.creer,
        enseignant_repository.obtenir_par_id,
        enseignant_repository.lister,
        enseignant_repository.rechercher,
        enseignant_repository.mettre_a_jour,
        enseignant_repository.changer_statut_actif,
    ]
    for fonction in fonctions_sans_suppression_repository:
        assert "DELETE FROM" not in inspect.getsource(fonction).upper()


def test_desactivation_reste_une_mise_a_jour_pas_une_suppression():
    """La désactivation continue d'utiliser exclusivement UPDATE, jamais DELETE."""
    source = inspect.getsource(enseignant_repository.changer_statut_actif)
    assert "UPDATE" in source.upper()
    assert "DELETE FROM" not in source.upper()


def test_desactivation_conserve_la_ligne_en_base():
    """La désactivation doit rester une simple mise à jour, jamais une suppression de ligne."""
    enseignant = _creer_enseignant_valide()
    avant = enseignant_service.lister_enseignants(inclure_inactifs=True)
    enseignant_service.desactiver_enseignant(enseignant.id)
    apres = enseignant_service.lister_enseignants(inclure_inactifs=True)
    assert len(avant) == len(apres)


# ---------------------------------------------------------------------
# Nettoyage des espaces (exigence explicite du cahier des charges)
# ---------------------------------------------------------------------

def test_nettoyage_espaces_superflus():
    enseignant = _creer_enseignant_valide(nom="  Koné   Fatoumata  ", prenom="  Aïssa  ")
    assert enseignant.nom == "Koné Fatoumata"
    assert enseignant.prenom == "Aïssa"
