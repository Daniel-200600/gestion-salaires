"""
Tests de sécurité — authentification (module 19, section 5/6/7/8).
"""

import pytest

import database.connection as database_connection
from models.enums import RoleUtilisateur
from services import auth_service, utilisateur_service
from utils.security import hash_password, verify_password


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})


def _creer_utilisateur(**overrides):
    donnees = dict(
        nom="Test", prenom="User", username="jtest", mot_de_passe="MotDePasse123!",
        confirmation_mot_de_passe="MotDePasse123!", role=RoleUtilisateur.GESTIONNAIRE_PAIE, actif=True,
    )
    donnees.update(overrides)
    return utilisateur_service.creer_utilisateur(**donnees)


# ---------------------------------------------------------------------
# Hachage de mots de passe (section 6)
# ---------------------------------------------------------------------

def test_hash_jamais_identique_a_deux_appels():
    h1 = hash_password("MotDePasse123!")
    h2 = hash_password("MotDePasse123!")
    assert h1 != h2


def test_verify_password_correct():
    h = hash_password("MotDePasse123!")
    assert verify_password("MotDePasse123!", h) is True


def test_verify_password_incorrect():
    h = hash_password("MotDePasse123!")
    assert verify_password("MauvaisMotDePasse", h) is False


def test_verify_password_hash_corrompu_ne_leve_pas():
    assert verify_password("peu importe", "ceci n'est pas un hash valide") is False


def test_verify_password_hash_vide_ne_leve_pas():
    assert verify_password("peu importe", "") is False


def test_verify_password_algorithme_inconnu_refuse():
    faux_hash = "md5$aaaa$bbbb"
    assert verify_password("peu importe", faux_hash) is False


def test_hash_ne_contient_jamais_le_mot_de_passe_en_clair():
    mot_de_passe = "SuperSecret42!"
    h = hash_password(mot_de_passe)
    assert mot_de_passe not in h


# ---------------------------------------------------------------------
# Connexion — messages génériques (section 7)
# ---------------------------------------------------------------------

def test_connexion_reussie():
    _creer_utilisateur(username="alice")
    resultat = auth_service.connecter("alice", "MotDePasse123!")
    assert resultat.reussie is True


def test_connexion_mauvais_mot_de_passe_meme_message_que_utilisateur_inexistant():
    _creer_utilisateur(username="bob")
    resultat_mauvais_mdp = auth_service.connecter("bob", "MauvaisMotDePasse")
    resultat_inexistant = auth_service.connecter("personne_du_tout", "peu importe")
    assert resultat_mauvais_mdp.message == resultat_inexistant.message


def test_connexion_utilisateur_desactive_refusee():
    u = _creer_utilisateur(username="charlie")
    utilisateur_service.desactiver_utilisateur(u.id)
    resultat = auth_service.connecter("charlie", "MotDePasse123!")
    assert resultat.reussie is False


# ---------------------------------------------------------------------
# Brute force (section 7)
# ---------------------------------------------------------------------

def test_verrouillage_apres_echecs_repetes():
    _creer_utilisateur(username="dave")
    from config.settings import MAX_LOGIN_ATTEMPTS

    for _ in range(MAX_LOGIN_ATTEMPTS):
        resultat = auth_service.connecter("dave", "mauvais_mdp")
        assert resultat.reussie is False

    resultat_bloque = auth_service.connecter("dave", "MotDePasse123!")
    assert resultat_bloque.reussie is False
    assert "tentative" in resultat_bloque.message.lower() or "réessayez" in resultat_bloque.message.lower()


def test_verrouillage_independant_par_utilisateur():
    _creer_utilisateur(username="eve")
    _creer_utilisateur(username="frank")
    from config.settings import MAX_LOGIN_ATTEMPTS

    for _ in range(MAX_LOGIN_ATTEMPTS):
        auth_service.connecter("eve", "mauvais_mdp")

    resultat_frank = auth_service.connecter("frank", "MotDePasse123!")
    assert resultat_frank.reussie is True


def test_reinitialisation_des_tentatives_apres_succes():
    _creer_utilisateur(username="grace")
    auth_service.connecter("grace", "mauvais_mdp")
    auth_service.connecter("grace", "mauvais_mdp")
    resultat_succes = auth_service.connecter("grace", "MotDePasse123!")
    assert resultat_succes.reussie is True

    resultat_echec = auth_service.connecter("grace", "mauvais_mdp")
    assert "trop de tentatives" not in resultat_echec.message.lower()


# ---------------------------------------------------------------------
# Audit — jamais de mot de passe journalisé (section 5/24)
# ---------------------------------------------------------------------

def test_audit_connexion_ne_contient_jamais_le_mot_de_passe(db_path):
    from database.connection import get_connection
    _creer_utilisateur(username="henri")
    mot_de_passe = "MotDePasseSecretUnique99!"
    auth_service.connecter("henri", mot_de_passe)
    auth_service.connecter("henri", "mauvais_" + mot_de_passe)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT details FROM audit_log WHERE entite = 'utilisateur' OR type_action LIKE 'connexion%'"
        ).fetchall()
    for ligne in lignes:
        assert mot_de_passe not in (ligne["details"] or "")


# ---------------------------------------------------------------------
# Revalidation de session (module 19 — correction de sécurité)
# ---------------------------------------------------------------------

def test_revalider_session_utilisateur_actif_retourne_utilisateur():
    u = _creer_utilisateur(username="isabelle")
    resultat = auth_service.revalider_session(u.id)
    assert resultat is not None
    assert resultat.actif is True


def test_revalider_session_utilisateur_desactive_retourne_none():
    """
    CORRECTION DE SÉCURITÉ (module 19) : avant cette correction, une
    session ouverte continuait à utiliser le rôle mis en cache lors
    de la connexion initiale, même après désactivation du compte par
    un administrateur. `revalider_session` est maintenant appelée à
    chaque page protégée (utils/session_auth.est_authentifie) pour
    empêcher exactement ce scénario.
    """
    u = _creer_utilisateur(username="jules")
    utilisateur_service.desactiver_utilisateur(u.id)
    resultat = auth_service.revalider_session(u.id)
    assert resultat is None


def test_revalider_session_utilisateur_supprime_retourne_none():
    resultat = auth_service.revalider_session(999999)
    assert resultat is None


def test_revalider_session_reflete_changement_de_role():
    u = _creer_utilisateur(username="karim", role=RoleUtilisateur.CONSULTATION)
    utilisateur_service.modifier_utilisateur(u.id, nom=u.nom, prenom=u.prenom, role=RoleUtilisateur.ADMIN)
    resultat = auth_service.revalider_session(u.id)
    assert resultat.role == RoleUtilisateur.ADMIN
