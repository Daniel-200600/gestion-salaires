"""
Tests de services/auth_service.py (module 11).
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from models.enums import RoleUtilisateur
from services import auth_service, utilisateur_service
from services.auth_service import MESSAGE_IDENTIFIANTS_INCORRECTS


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    # Isole le compteur de tentatives en mémoire entre les tests.
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})


def _creer_utilisateur(username="user1", mot_de_passe="MotDePasse123", role=RoleUtilisateur.ADMIN, actif=True):
    return utilisateur_service.creer_utilisateur(
        nom="Test", prenom="Utilisateur", username=username, mot_de_passe=mot_de_passe, role=role, actif=actif
    )


# ---------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------

def test_connexion_reussie():
    _creer_utilisateur()
    resultat = auth_service.connecter("user1", "MotDePasse123")
    assert resultat.reussie is True
    assert resultat.utilisateur is not None
    assert resultat.utilisateur.username == "user1"


def test_mauvais_username():
    _creer_utilisateur()
    resultat = auth_service.connecter("inconnu", "MotDePasse123")
    assert resultat.reussie is False
    assert resultat.message == MESSAGE_IDENTIFIANTS_INCORRECTS


def test_mauvais_mot_de_passe():
    _creer_utilisateur()
    resultat = auth_service.connecter("user1", "MauvaisMotDePasse")
    assert resultat.reussie is False
    assert resultat.message == MESSAGE_IDENTIFIANTS_INCORRECTS


def test_meme_message_pour_username_et_mot_de_passe_incorrects():
    """Ne révèle jamais lequel des deux est incorrect (section 12)."""
    _creer_utilisateur()
    resultat_mauvais_user = auth_service.connecter("inconnu", "peu importe")
    resultat_mauvais_mdp = auth_service.connecter("user1", "MauvaisMotDePasse")
    assert resultat_mauvais_user.message == resultat_mauvais_mdp.message


def test_utilisateur_desactive_ne_peut_pas_se_connecter():
    u = _creer_utilisateur(role=RoleUtilisateur.GESTIONNAIRE_PAIE)
    utilisateur_service.desactiver_utilisateur(u.id)
    resultat = auth_service.connecter("user1", "MotDePasse123")
    assert resultat.reussie is False


# ---------------------------------------------------------------------
# Dernière connexion
# ---------------------------------------------------------------------

def test_derniere_connexion_mise_a_jour_si_reussie():
    u = _creer_utilisateur()
    assert u.derniere_connexion is None
    auth_service.connecter("user1", "MotDePasse123")
    relu = utilisateur_service.obtenir_utilisateur(u.id)
    assert relu.derniere_connexion is not None


def test_derniere_connexion_non_modifiee_si_echec():
    u = _creer_utilisateur()
    auth_service.connecter("user1", "MauvaisMotDePasse")
    relu = utilisateur_service.obtenir_utilisateur(u.id)
    assert relu.derniere_connexion is None


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def test_audit_connexion_reussie(db_path):
    _creer_utilisateur()
    auth_service.connecter("user1", "MotDePasse123")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'connexion_reussie'").fetchall()
    assert len(lignes) == 1


def test_audit_connexion_echouee(db_path):
    _creer_utilisateur()
    auth_service.connecter("user1", "MauvaisMotDePasse")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'connexion_echouee'").fetchall()
    assert len(lignes) == 1


def test_audit_ne_contient_jamais_le_mot_de_passe(db_path):
    _creer_utilisateur()
    auth_service.connecter("user1", "MotDePasseSecretUnique999")
    auth_service.connecter("user1", "MauvaisMotDePasseXYZ")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT details FROM audit_log").fetchall()
    for ligne in lignes:
        assert "MotDePasseSecretUnique999" not in (ligne["details"] or "")
        assert "MauvaisMotDePasseXYZ" not in (ligne["details"] or "")


def test_audit_deconnexion(db_path):
    u = _creer_utilisateur()
    auth_service.deconnecter(u.id, u.username)
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'deconnexion'").fetchall()
    assert len(lignes) == 1


# ---------------------------------------------------------------------
# Limitation des tentatives répétées (section 28)
# ---------------------------------------------------------------------

def test_verrouillage_apres_trop_de_tentatives():
    from config.settings import MAX_LOGIN_ATTEMPTS
    _creer_utilisateur()

    for _ in range(MAX_LOGIN_ATTEMPTS):
        resultat = auth_service.connecter("user1", "MauvaisMotDePasse")
        assert resultat.reussie is False

    # La tentative suivante, même avec le BON mot de passe, doit être bloquée.
    resultat_verrouille = auth_service.connecter("user1", "MotDePasse123")
    assert resultat_verrouille.reussie is False
    assert "tentatives" in resultat_verrouille.message.lower()


def test_tentatives_reinitialisees_apres_connexion_reussie():
    _creer_utilisateur()
    auth_service.connecter("user1", "MauvaisMotDePasse")
    auth_service.connecter("user1", "MauvaisMotDePasse")
    resultat = auth_service.connecter("user1", "MotDePasse123")
    assert resultat.reussie is True
    cle = auth_service._cle("user1")
    assert auth_service._tentatives_echouees.get(cle, []) == []
