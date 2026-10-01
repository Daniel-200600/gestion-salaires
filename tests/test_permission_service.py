"""
Tests de services/permission_service.py (module 11) : vérifie la
matrice de permissions pour chacun des trois rôles.
"""

from models.enums import RoleUtilisateur
from services import permission_service


def test_admin_a_toutes_les_permissions_administratives():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.ADMINISTRATION_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.UTILISATEUR_GERER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.BACKUP_CREER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.BACKUP_RESTAURER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.PARAMETRE_MODIFIER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.AUDIT_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.ENSEIGNANT_SUPPRIMER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.PERIODE_SUPPRIMER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.PAIE_VALIDER)
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.PAIE_CLOTURER)


def test_gestionnaire_paie_permissions_metier():
    role = RoleUtilisateur.GESTIONNAIRE_PAIE
    assert permission_service.a_permission(role, permission_service.ENSEIGNANT_CONSULTER)
    assert permission_service.a_permission(role, permission_service.PAIE_MODIFIER)
    assert permission_service.a_permission(role, permission_service.PAIE_CONTROLER)
    assert permission_service.a_permission(role, permission_service.BULLETIN_GENERER)
    assert permission_service.a_permission(role, permission_service.EXPORT_GENERER)
    assert permission_service.a_permission(role, permission_service.HISTORIQUE_CONSULTER)
    assert permission_service.a_permission(role, permission_service.PAIE_VALIDER)


def test_gestionnaire_paie_ne_peut_pas_administrer():
    role = RoleUtilisateur.GESTIONNAIRE_PAIE
    assert not permission_service.a_permission(role, permission_service.UTILISATEUR_GERER)
    assert not permission_service.a_permission(role, permission_service.BACKUP_RESTAURER)
    assert not permission_service.a_permission(role, permission_service.PARAMETRE_MODIFIER)
    assert not permission_service.a_permission(role, permission_service.ADMINISTRATION_CONSULTER)
    assert not permission_service.a_permission(role, permission_service.AUDIT_CONSULTER)


def test_gestionnaire_paie_ne_peut_pas_supprimer():
    role = RoleUtilisateur.GESTIONNAIRE_PAIE
    assert not permission_service.a_permission(role, permission_service.ENSEIGNANT_SUPPRIMER)
    assert not permission_service.a_permission(role, permission_service.PERIODE_SUPPRIMER)


def test_consultation_lecture_seule():
    role = RoleUtilisateur.CONSULTATION
    assert permission_service.a_permission(role, permission_service.ENSEIGNANT_CONSULTER)
    assert permission_service.a_permission(role, permission_service.PAIE_CONSULTER)
    assert permission_service.a_permission(role, permission_service.PERIODE_CONSULTER)
    assert permission_service.a_permission(role, permission_service.HISTORIQUE_CONSULTER)
    assert permission_service.a_permission(role, permission_service.BULLETIN_CONSULTER)
    assert permission_service.a_permission(role, permission_service.PAIE_CONTROLER)


def test_consultation_ne_peut_rien_modifier_ni_supprimer():
    role = RoleUtilisateur.CONSULTATION
    assert not permission_service.a_permission(role, permission_service.ENSEIGNANT_MODIFIER)
    assert not permission_service.a_permission(role, permission_service.ENSEIGNANT_SUPPRIMER)
    assert not permission_service.a_permission(role, permission_service.PAIE_MODIFIER)
    assert not permission_service.a_permission(role, permission_service.PAIE_VALIDER)
    assert not permission_service.a_permission(role, permission_service.PAIE_CLOTURER)
    assert not permission_service.a_permission(role, permission_service.BULLETIN_GENERER)
    assert not permission_service.a_permission(role, permission_service.EXPORT_GENERER)
    assert not permission_service.a_permission(role, permission_service.PERIODE_SUPPRIMER)


def test_consultation_ne_peut_pas_administrer():
    role = RoleUtilisateur.CONSULTATION
    assert not permission_service.a_permission(role, permission_service.ADMINISTRATION_CONSULTER)
    assert not permission_service.a_permission(role, permission_service.UTILISATEUR_GERER)
    assert not permission_service.a_permission(role, permission_service.BACKUP_CREER)
    assert not permission_service.a_permission(role, permission_service.BACKUP_RESTAURER)


def test_permission_inconnue_toujours_refusee_par_defaut():
    """Une permission qui n'existe pas dans la matrice ne doit jamais accorder d'accès par défaut."""
    assert not permission_service.a_permission(RoleUtilisateur.ADMIN, "permission.qui.nexiste.pas")


def test_permissions_du_role_admin_inclut_tout():
    permissions_admin = permission_service.permissions_du_role(RoleUtilisateur.ADMIN)
    assert permission_service.UTILISATEUR_GERER in permissions_admin
    assert permission_service.ENSEIGNANT_SUPPRIMER in permissions_admin


def test_permissions_du_role_consultation_est_un_sous_ensemble():
    permissions_consultation = permission_service.permissions_du_role(RoleUtilisateur.CONSULTATION)
    permissions_admin = permission_service.permissions_du_role(RoleUtilisateur.ADMIN)
    assert permissions_consultation.issubset(permissions_admin)


# ---------------------------------------------------------------------
# Permissions du reporting (module 13)
# ---------------------------------------------------------------------

def test_reporting_consulter_accessible_aux_trois_roles():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.REPORTING_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.REPORTING_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.REPORTING_CONSULTER)


def test_reporting_exporter_refuse_a_consultation():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.REPORTING_EXPORTER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.REPORTING_EXPORTER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.REPORTING_EXPORTER)


# ---------------------------------------------------------------------
# Permissions documentaires (module 14)
# ---------------------------------------------------------------------

def test_document_consulter_accessible_aux_trois_roles():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.DOCUMENT_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.DOCUMENT_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.DOCUMENT_CONSULTER)


def test_document_archiver_refuse_a_consultation():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.DOCUMENT_ARCHIVER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.DOCUMENT_ARCHIVER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.DOCUMENT_ARCHIVER)


def test_document_exporter_refuse_a_consultation():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.DOCUMENT_EXPORTER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.DOCUMENT_EXPORTER)
