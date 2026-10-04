"""
Tests de services/utilisateur_service.reinitialiser_tous_les_comptes
(correction finale — section 12 à 17 du cahier des charges).
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from models.enums import RoleUtilisateur
from services import (
    auth_service,
    controle_paie_service,
    donnees_paie_service,
    enseignant_service,
    periode_service,
    utilisateur_service,
)
from services.donnees_paie_service import DonneesPaieEnseignant

# Cas de référence officiel : vacataire, taxe de 5 %.
pytestmark = pytest.mark.taxe_historique


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})


def _creer_utilisateur(**overrides):
    donnees = dict(
        nom="Ancien", prenom="Compte", username="ancien_compte", mot_de_passe="AncienMotDePasse123!",
        confirmation_mot_de_passe="AncienMotDePasse123!", role=RoleUtilisateur.ADMIN, actif=True,
    )
    donnees.update(overrides)
    return utilisateur_service.creer_utilisateur(**donnees)


# ---------------------------------------------------------------------
# Confirmation explicite obligatoire
# ---------------------------------------------------------------------

def test_reinitialisation_refusee_sans_confirmation():
    _creer_utilisateur()
    with pytest.raises(ValueError):
        utilisateur_service.reinitialiser_tous_les_comptes(confirmation=False)


def test_reinitialisation_refusee_avec_confirmation_non_booleenne():
    _creer_utilisateur()
    with pytest.raises(ValueError):
        utilisateur_service.reinitialiser_tous_les_comptes(confirmation="oui")


def test_aucun_compte_supprime_si_refuse():
    _creer_utilisateur()
    try:
        utilisateur_service.reinitialiser_tous_les_comptes(confirmation=False)
    except ValueError:
        pass
    assert len(utilisateur_service.lister_utilisateurs()) == 1


# ---------------------------------------------------------------------
# Réinitialisation réussie — comptes (section 13/19)
# ---------------------------------------------------------------------

def test_reinitialisation_supprime_tous_les_comptes():
    _creer_utilisateur(username="a")
    _creer_utilisateur(username="b", role=RoleUtilisateur.CONSULTATION)
    nb = utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)
    assert nb == 2
    assert utilisateur_service.lister_utilisateurs() == []


def test_ancien_compte_ne_peut_plus_se_connecter_apres_reinitialisation():
    _creer_utilisateur(username="old_admin")
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)
    resultat = auth_service.connecter("old_admin", "AncienMotDePasse123!")
    assert resultat.reussie is False


def test_ancien_mot_de_passe_ne_fonctionne_plus_meme_avec_bon_nom_utilisateur():
    _creer_utilisateur(username="old_admin")
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)
    utilisateur_service.creer_utilisateur(
        nom="Nouveau", prenom="Compte", username="old_admin", mot_de_passe="NouveauMotDePasse456!",
        confirmation_mot_de_passe="NouveauMotDePasse456!", role=RoleUtilisateur.ADMIN, actif=True,
    )
    resultat_ancien_mdp = auth_service.connecter("old_admin", "AncienMotDePasse123!")
    assert resultat_ancien_mdp.reussie is False


# ---------------------------------------------------------------------
# Invalidation de session (section 16) — via revalider_session (module 19)
# ---------------------------------------------------------------------

def test_session_invalidee_automatiquement_apres_reinitialisation():
    u = _creer_utilisateur()
    avant = auth_service.revalider_session(u.id)
    assert avant is not None

    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)

    apres = auth_service.revalider_session(u.id)
    assert apres is None


# ---------------------------------------------------------------------
# Retour à l'état « première initialisation » (section 13/14)
# ---------------------------------------------------------------------

def test_premier_administrateur_peut_etre_recree_apres_reinitialisation():
    _creer_utilisateur()
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)

    assert utilisateur_service.lister_utilisateurs() == []

    utilisateur_service.creer_utilisateur(
        nom="Nouveau", prenom="Admin", username="nouvel_admin", mot_de_passe="NouveauMotDePasse123!",
        confirmation_mot_de_passe="NouveauMotDePasse123!", role=RoleUtilisateur.ADMIN, actif=True,
    )
    resultat = auth_service.connecter("nouvel_admin", "NouveauMotDePasse123!")
    assert resultat.reussie is True


def test_nouveau_mot_de_passe_correctement_hashe_scrypt(db_path):
    utilisateur_service.creer_utilisateur(
        nom="N", prenom="A", username="verif_hash", mot_de_passe="MotDePasseVerif123!",
        confirmation_mot_de_passe="MotDePasseVerif123!", role=RoleUtilisateur.ADMIN, actif=True,
    )
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT password_hash FROM utilisateurs WHERE username = ?", ("verif_hash",)).fetchone()
    assert row["password_hash"].startswith("scrypt$")
    assert "MotDePasseVerif123!" not in row["password_hash"]


# ---------------------------------------------------------------------
# Préservation des données métier (section 12/17) — le cœur de l'exigence
# ---------------------------------------------------------------------

def test_enseignants_preserves_apres_reinitialisation_comptes():
    e = enseignant_service.creer_enseignant(nom="Kamgang", prenom="Jean", sexe="M", statut="V", taux_horaire=2000)
    _creer_utilisateur()
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)

    e_relu = enseignant_service.obtenir_enseignant(e.id)
    assert e_relu.nom == "Kamgang"


def test_periodes_et_donnees_paie_preservees_apres_reinitialisation_comptes():
    e = enseignant_service.creer_enseignant(nom="Kamgang", prenom="Jean", sexe="M", statut="V", taux_horaire=2000)
    p = periode_service.creer_periode(mois=8, annee=2026)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
            retenue_amicale=5000, dette=10000),
    ])
    _creer_utilisateur()

    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)

    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir == 208250


def test_integrite_sqlite_ok_apres_reinitialisation(db_path):
    _creer_utilisateur()
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)
    with get_connection(db_path) as conn:
        resultat = conn.execute("PRAGMA integrity_check").fetchone()
    assert resultat[0] == "ok"


# ---------------------------------------------------------------------
# Conservation de l'audit historique (section 15)
# ---------------------------------------------------------------------

def test_audit_historique_conserve_apres_reinitialisation(db_path):
    _creer_utilisateur(username="admin_avant_reset")
    auth_service.connecter("admin_avant_reset", "AncienMotDePasse123!")

    with get_connection(db_path) as conn:
        total_avant = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert total_avant > 0

    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)

    with get_connection(db_path) as conn:
        total_apres = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert total_apres == total_avant


def test_aucune_violation_de_contrainte_referentielle():
    """audit_log.utilisateur est un simple TEXTE (pas une FK) : la suppression des comptes ne doit jamais lever d'IntegrityError."""
    _creer_utilisateur(username="admin_texte")
    auth_service.connecter("admin_texte", "AncienMotDePasse123!")
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)  # ne doit lever aucune exception


# ---------------------------------------------------------------------
# Second administrateur et protection du dernier admin après reset (section 19)
# ---------------------------------------------------------------------

def test_second_administrateur_peut_etre_cree_apres_reinitialisation():
    _creer_utilisateur()
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)

    utilisateur_service.creer_utilisateur(
        nom="A", prenom="A", username="admin1", mot_de_passe="MotDePasse123!",
        confirmation_mot_de_passe="MotDePasse123!", role=RoleUtilisateur.ADMIN, actif=True,
    )
    utilisateur_service.creer_utilisateur(
        nom="B", prenom="B", username="admin2", mot_de_passe="MotDePasse123!",
        confirmation_mot_de_passe="MotDePasse123!", role=RoleUtilisateur.ADMIN, actif=True,
    )
    assert len(utilisateur_service.lister_utilisateurs()) == 2


def test_protection_dernier_admin_toujours_active_apres_reinitialisation():
    _creer_utilisateur()
    utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)

    nouvel_admin = utilisateur_service.creer_utilisateur(
        nom="Seul", prenom="Admin", username="seul_admin", mot_de_passe="MotDePasse123!",
        confirmation_mot_de_passe="MotDePasse123!", role=RoleUtilisateur.ADMIN, actif=True,
    )
    with pytest.raises(Exception):
        utilisateur_service.desactiver_utilisateur(nouvel_admin.id)
