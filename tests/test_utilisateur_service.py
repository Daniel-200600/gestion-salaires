"""
Tests de services/utilisateur_service.py (module 11).
"""

import pytest

import database.connection as database_connection
from models.enums import RoleUtilisateur
from services import utilisateur_service
from services.utilisateur_service import DernierAdminError, UtilisateurValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_admin(username="admin1", **overrides):
    donnees = {
        "nom": "Mbarga", "prenom": "Alain", "username": username,
        "mot_de_passe": "MotDePasse123", "role": RoleUtilisateur.ADMIN,
    }
    donnees.update(overrides)
    return utilisateur_service.creer_utilisateur(**donnees)


def _creer_gestionnaire(username="gest1", **overrides):
    donnees = {
        "nom": "Ngono", "prenom": "Marie", "username": username,
        "mot_de_passe": "MotDePasse456", "role": RoleUtilisateur.GESTIONNAIRE_PAIE,
    }
    donnees.update(overrides)
    return utilisateur_service.creer_utilisateur(**donnees)


# ---------------------------------------------------------------------
# Création
# ---------------------------------------------------------------------

def test_creation_utilisateur():
    u = _creer_admin()
    assert u.id is not None
    assert u.username == "admin1"
    assert u.role == RoleUtilisateur.ADMIN
    assert u.actif is True


def test_mot_de_passe_jamais_stocke_en_clair():
    u = _creer_admin()
    assert "MotDePasse123" not in u.password_hash
    assert u.password_hash.startswith("scrypt$")


def test_username_unique_insensible_a_la_casse():
    _creer_admin(username="Admin1")
    with pytest.raises(UtilisateurValidationError, match="déjà utilisé"):
        _creer_admin(username="ADMIN1")


def test_username_obligatoire():
    with pytest.raises(UtilisateurValidationError, match="obligatoire"):
        _creer_admin(username="   ")


def test_nom_prenom_obligatoires():
    with pytest.raises(UtilisateurValidationError):
        _creer_admin(nom="")
    with pytest.raises(UtilisateurValidationError):
        _creer_admin(prenom="")


def test_mot_de_passe_trop_court_refuse():
    with pytest.raises(UtilisateurValidationError, match="caractères"):
        _creer_admin(mot_de_passe="court")


def test_mot_de_passe_vide_refuse():
    with pytest.raises(UtilisateurValidationError, match="vide"):
        _creer_admin(mot_de_passe="")


def test_confirmation_mot_de_passe_doit_correspondre():
    with pytest.raises(UtilisateurValidationError, match="correspondent"):
        utilisateur_service.creer_utilisateur(
            nom="Test", prenom="Test", username="test1", mot_de_passe="MotDePasse123",
            confirmation_mot_de_passe="MotDePasseDifferent", role=RoleUtilisateur.CONSULTATION,
        )


# ---------------------------------------------------------------------
# Modification
# ---------------------------------------------------------------------

def test_modification_utilisateur():
    u = _creer_gestionnaire()
    modifie = utilisateur_service.modifier_utilisateur(u.id, nom="Nouveau", prenom="Nom", role=RoleUtilisateur.ADMIN)
    assert modifie.nom == "Nouveau"
    assert modifie.role == RoleUtilisateur.ADMIN


def test_modification_ne_touche_jamais_le_mot_de_passe():
    u = _creer_gestionnaire()
    hash_avant = u.password_hash
    modifie = utilisateur_service.modifier_utilisateur(u.id, nom=u.nom, prenom=u.prenom, role=u.role)
    assert modifie.password_hash == hash_avant


# ---------------------------------------------------------------------
# Activation / désactivation
# ---------------------------------------------------------------------

def test_desactivation_et_reactivation():
    _creer_admin()  # garantit qu'il reste un admin actif après désactivation du gestionnaire
    u = _creer_gestionnaire()
    desactive = utilisateur_service.desactiver_utilisateur(u.id)
    assert desactive.actif is False

    reactive = utilisateur_service.activer_utilisateur(u.id)
    assert reactive.actif is True


# ---------------------------------------------------------------------
# Recherche / listing
# ---------------------------------------------------------------------

def test_recherche_par_id():
    u = _creer_admin()
    trouve = utilisateur_service.obtenir_utilisateur(u.id)
    assert trouve.username == u.username


def test_utilisateur_inexistant():
    with pytest.raises(UtilisateurValidationError):
        utilisateur_service.obtenir_utilisateur(9999)


def test_lister_utilisateurs():
    _creer_admin(username="a")
    _creer_gestionnaire(username="b")
    tous = utilisateur_service.lister_utilisateurs()
    assert len(tous) == 2


def test_lister_exclut_inactifs_si_demande():
    _creer_admin(username="a")
    u2 = _creer_gestionnaire(username="b")
    utilisateur_service.desactiver_utilisateur(u2.id)
    actifs_seulement = utilisateur_service.lister_utilisateurs(inclure_inactifs=False)
    assert len(actifs_seulement) == 1


# ---------------------------------------------------------------------
# Changement de rôle
# ---------------------------------------------------------------------

def test_changement_de_role():
    _creer_admin(username="admin_protege")
    u = _creer_gestionnaire()
    modifie = utilisateur_service.modifier_utilisateur(u.id, nom=u.nom, prenom=u.prenom, role=RoleUtilisateur.ADMIN)
    assert modifie.role == RoleUtilisateur.ADMIN


# ---------------------------------------------------------------------
# Protection du dernier ADMIN actif (section 24)
# ---------------------------------------------------------------------

def test_dernier_admin_ne_peut_pas_etre_desactive():
    admin = _creer_admin()
    with pytest.raises(DernierAdminError):
        utilisateur_service.desactiver_utilisateur(admin.id)
    assert utilisateur_service.obtenir_utilisateur(admin.id).actif is True


def test_dernier_admin_ne_peut_pas_etre_retrograde():
    admin = _creer_admin()
    with pytest.raises(DernierAdminError):
        utilisateur_service.modifier_utilisateur(
            admin.id, nom=admin.nom, prenom=admin.prenom, role=RoleUtilisateur.CONSULTATION
        )
    assert utilisateur_service.obtenir_utilisateur(admin.id).role == RoleUtilisateur.ADMIN


def test_desactivation_admin_autorisee_si_un_autre_admin_actif_existe():
    admin1 = _creer_admin(username="admin1")
    _creer_admin(username="admin2")
    desactive = utilisateur_service.desactiver_utilisateur(admin1.id)
    assert desactive.actif is False


def test_retrogradation_admin_autorisee_si_un_autre_admin_actif_existe():
    admin1 = _creer_admin(username="admin1")
    _creer_admin(username="admin2")
    modifie = utilisateur_service.modifier_utilisateur(
        admin1.id, nom=admin1.nom, prenom=admin1.prenom, role=RoleUtilisateur.CONSULTATION
    )
    assert modifie.role == RoleUtilisateur.CONSULTATION


def test_desactivation_admin_deja_inactif_ne_declenche_pas_la_protection():
    """Un admin déjà inactif ne compte pas dans le calcul : retrograder le dernier actif doit échouer."""
    admin1 = _creer_admin(username="admin1")
    admin2 = _creer_admin(username="admin2")
    utilisateur_service.desactiver_utilisateur(admin2.id)
    with pytest.raises(DernierAdminError):
        utilisateur_service.desactiver_utilisateur(admin1.id)


# ---------------------------------------------------------------------
# Changement de mot de passe (par l'utilisateur lui-même)
# ---------------------------------------------------------------------

def test_changement_mot_de_passe_reussi():
    u = _creer_admin()
    utilisateur_service.changer_mot_de_passe(u.id, "MotDePasse123", "NouveauMotDePasse456")
    relu = utilisateur_service.obtenir_utilisateur(u.id)
    from utils.security import verify_password
    assert verify_password("NouveauMotDePasse456", relu.password_hash)


def test_changement_mot_de_passe_ancien_incorrect_refuse():
    u = _creer_admin()
    with pytest.raises(UtilisateurValidationError, match="incorrect"):
        utilisateur_service.changer_mot_de_passe(u.id, "MauvaisAncien", "NouveauMotDePasse456")


def test_changement_mot_de_passe_nouveau_trop_court_refuse():
    u = _creer_admin()
    with pytest.raises(UtilisateurValidationError):
        utilisateur_service.changer_mot_de_passe(u.id, "MotDePasse123", "court")


# ---------------------------------------------------------------------
# Réinitialisation par un administrateur
# ---------------------------------------------------------------------

def test_reinitialisation_mot_de_passe_par_admin():
    u = _creer_gestionnaire()
    utilisateur_service.reinitialiser_mot_de_passe(u.id, "MotDePasseReinitialise1")
    relu = utilisateur_service.obtenir_utilisateur(u.id)
    from utils.security import verify_password
    assert verify_password("MotDePasseReinitialise1", relu.password_hash)


def test_reinitialisation_ne_necessite_pas_ancien_mot_de_passe():
    """Contrairement à changer_mot_de_passe, aucune vérification de l'ancien mot de passe n'est requise."""
    u = _creer_gestionnaire()
    utilisateur_service.reinitialiser_mot_de_passe(u.id, "AutreMotDePasse789")
