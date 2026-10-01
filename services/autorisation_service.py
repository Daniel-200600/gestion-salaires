"""
Contrôle d'autorisation côté service pour les opérations sensibles.

La matrice des permissions (services/permission_service.py) reste la
source de vérité unique. Ce module ajoute une vérification effectuée
DANS le service appelé, et non seulement dans la page : le rôle est
relu en base à partir de l'identifiant de l'utilisateur qui agit, au
moment de l'opération. Un rôle falsifié dans la session, un compte
désactivé ou supprimé entre-temps, ou un appel direct à la fonction
sans passer par l'interface sont donc refusés.

Aucune donnée d'authentification (mot de passe, hash) n'est lue ni
renvoyée par ce module au-delà de ce que fournit déjà
`auth_service.revalider_session`.
"""

from pathlib import Path
from typing import Optional, Union

from models.utilisateur import Utilisateur
from services import auth_service, permission_service

DbPath = Optional[Union[str, Path]]


class AutorisationRefuseeError(PermissionError):
    """Opération refusée : utilisateur inconnu, désactivé ou sans la permission requise."""


def exiger_permission_utilisateur(
    utilisateur_id: Optional[int], permission: str, db_path: DbPath = None
) -> Utilisateur:
    """
    Vérifie, à partir de l'état réel en base, que l'utilisateur
    `utilisateur_id` existe, est actif et possède `permission`.

    Returns:
        L'utilisateur à jour (utile pour journaliser son nom).

    Raises:
        AutorisationRefuseeError: dans tous les autres cas.
    """
    if utilisateur_id is None:
        raise AutorisationRefuseeError("Opération refusée : aucun utilisateur authentifié.")

    utilisateur = auth_service.revalider_session(utilisateur_id, db_path=db_path)
    if utilisateur is None:
        raise AutorisationRefuseeError("Opération refusée : compte introuvable ou désactivé.")

    if not permission_service.a_permission(utilisateur.role, permission):
        raise AutorisationRefuseeError(
            "Opération refusée : votre rôle ne dispose pas des droits nécessaires pour cette action."
        )
    return utilisateur
