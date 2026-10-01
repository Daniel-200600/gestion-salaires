"""
Tests de sécurité — autorisation/permissions (module 19, section 9/10).

Vérifie que TOUTE permission connue de la matrice centrale a un
comportement cohérent pour les 3 rôles, et que CONSULTATION est
toujours strictement le rôle le moins privilégié (jamais une
permission accordée à CONSULTATION mais refusée à GESTIONNAIRE_PAIE
ou ADMIN).
"""

import pytest

from models.enums import RoleUtilisateur
from services import permission_service


def _toutes_les_permissions():
    """Extrait dynamiquement toutes les constantes de permission du module (chaînes 'x.y')."""
    permissions = []
    for nom in dir(permission_service):
        valeur = getattr(permission_service, nom)
        if isinstance(valeur, str) and "." in valeur and nom.isupper():
            permissions.append(valeur)
    return permissions


# ---------------------------------------------------------------------
# Cohérence globale de la matrice (section 9)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("permission", _toutes_les_permissions())
def test_admin_a_toujours_acces(permission):
    """ADMIN doit avoir accès à absolument toutes les permissions connues — aucune exception silencieuse."""
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission), (
        f"ADMIN devrait avoir la permission {permission!r}."
    )


@pytest.mark.parametrize("permission", _toutes_les_permissions())
def test_consultation_jamais_plus_large_que_gestionnaire(permission):
    """Toute permission accordée à CONSULTATION doit l'être aussi à GESTIONNAIRE_PAIE (hiérarchie cohérente)."""
    if permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission):
        assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission), (
            f"{permission!r} accordée à CONSULTATION mais refusée à GESTIONNAIRE_PAIE — hiérarchie incohérente."
        )


def test_role_inconnu_ou_none_refuse_par_defaut():
    """a_permission ne doit jamais lever pour un rôle absent — le refus est le comportement sûr par défaut."""
    for permission in _toutes_les_permissions()[:5]:
        assert permission_service.a_permission(None, permission) is False


# ---------------------------------------------------------------------
# Permissions opérationnelles sensibles explicitement vérifiées (section 9)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("permission_name", [
    "PAIE_MODIFIER", "PERIODE_VALIDER", "PERIODE_CLOTURER", "ENSEIGNANT_SUPPRIMER",
    "DOCUMENT_ARCHIVER", "IMPORT_DONNEES", "AUTOMATISATION_EXECUTER", "UTILISATEUR_GERER",
    "SAUVEGARDE_RESTAURER",
])
def test_permission_sensible_refusee_a_consultation_si_elle_existe(permission_name):
    """
    Les opérations sensibles listées ci-dessus, lorsqu'elles existent
    dans la matrice actuelle, ne doivent jamais être accordées à
    CONSULTATION. Un nom absent de la matrice (permission nommée
    différemment) est ignoré plutôt que de faire échouer le test —
    ce test vérifie une propriété de sécurité, pas la présence
    littérale d'un nom.
    """
    valeur = getattr(permission_service, permission_name, None)
    if valeur is None:
        pytest.skip(f"{permission_name} n'existe pas dans cette version de permission_service.")
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, valeur)
