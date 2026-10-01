"""
Service utilisateur (module 11).

Logique métier de gestion des comptes utilisateurs : création,
modification (nom/prénom/rôle), activation/désactivation, changement
et réinitialisation de mot de passe. Le hachage lui-même est délégué à
utils/security.py ; l'accès aux données à
database/repositories/utilisateur_repository.py.

RÈGLE CRITIQUE (section 24) : le système doit toujours conserver au
moins un ADMIN actif. Toute opération qui désactiverait ou
rétrograderait le dernier ADMIN actif est refusée.
"""

import logging
from pathlib import Path
from typing import List, Optional, Union

from config.settings import PASSWORD_MIN_LENGTH
from database.connection import get_connection
from database.repositories import utilisateur_repository
from models.enums import RoleUtilisateur
from models.utilisateur import Utilisateur
from utils.security import hash_password, verify_password

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.utilisateur_service")


class UtilisateurValidationError(Exception):
    """Erreur de validation métier sur un utilisateur — message toujours compréhensible pour l'interface."""


class DernierAdminError(UtilisateurValidationError):
    """Levée quand une opération laisserait le système sans aucun ADMIN actif."""


def _valider_mot_de_passe(mot_de_passe: str) -> None:
    """
    Politique de mot de passe (section 31) : longueur minimale,
    jamais vide. Volontairement simple — pas de règle de complexité
    artificielle (majuscule/chiffre/symbole obligatoires), qui
    n'améliore pas nécessairement la sécurité réelle et complique
    l'usage pour une application locale d'établissement scolaire.
    """
    if not mot_de_passe:
        raise UtilisateurValidationError("Le mot de passe ne peut pas être vide.")
    if len(mot_de_passe) < PASSWORD_MIN_LENGTH:
        raise UtilisateurValidationError(
            f"Le mot de passe doit contenir au moins {PASSWORD_MIN_LENGTH} caractères."
        )


def _valider_username(username: str) -> str:
    username_nettoye = username.strip()
    if not username_nettoye:
        raise UtilisateurValidationError("Le nom d'utilisateur est obligatoire.")
    return username_nettoye


def creer_utilisateur(
    nom: str,
    prenom: str,
    username: str,
    mot_de_passe: str,
    role: RoleUtilisateur,
    actif: bool = True,
    confirmation_mot_de_passe: Optional[str] = None,
    db_path: DbPath = None,
) -> Utilisateur:
    """
    Crée un nouvel utilisateur. Le mot de passe est haché immédiatement
    (jamais stocké en clair, jamais journalisé). Lève
    UtilisateurValidationError si le nom d'utilisateur est déjà pris
    (insensible à la casse), si le mot de passe ne respecte pas la
    politique minimale, ou si `confirmation_mot_de_passe` est fourni
    et ne correspond pas exactement à `mot_de_passe`.
    """
    username_nettoye = _valider_username(username)
    if not nom.strip():
        raise UtilisateurValidationError("Le nom est obligatoire.")
    if not prenom.strip():
        raise UtilisateurValidationError("Le prénom est obligatoire.")
    _valider_mot_de_passe(mot_de_passe)
    if confirmation_mot_de_passe is not None and mot_de_passe != confirmation_mot_de_passe:
        raise UtilisateurValidationError("Le mot de passe et sa confirmation ne correspondent pas.")

    if utilisateur_repository.obtenir_par_username(username_nettoye, db_path=db_path) is not None:
        raise UtilisateurValidationError(f"Le nom d'utilisateur « {username_nettoye} » est déjà utilisé.")

    utilisateur = Utilisateur(
        nom=nom.strip(),
        prenom=prenom.strip(),
        username=username_nettoye,
        password_hash=hash_password(mot_de_passe),
        role=role,
        actif=actif,
    )
    utilisateur.id = utilisateur_repository.creer(utilisateur, db_path=db_path)
    logger.info("Utilisateur créé : %s (rôle %s)", username_nettoye, role.value)
    return utilisateur_repository.obtenir_par_id(utilisateur.id, db_path=db_path)


def lister_utilisateurs(inclure_inactifs: bool = True, db_path: DbPath = None) -> List[Utilisateur]:
    return utilisateur_repository.lister(inclure_inactifs=inclure_inactifs, db_path=db_path)


def obtenir_utilisateur(utilisateur_id: int, db_path: DbPath = None) -> Utilisateur:
    utilisateur = utilisateur_repository.obtenir_par_id(utilisateur_id, db_path=db_path)
    if utilisateur is None:
        raise UtilisateurValidationError(f"Aucun utilisateur avec l'id {utilisateur_id}.")
    return utilisateur


def modifier_utilisateur(
    utilisateur_id: int, nom: str, prenom: str, role: RoleUtilisateur, db_path: DbPath = None
) -> Utilisateur:
    """
    Modifie nom/prénom/rôle (jamais le mot de passe, ni le username —
    opérations séparées). Refuse de rétrograder le dernier ADMIN actif
    (section 24).
    """
    utilisateur = obtenir_utilisateur(utilisateur_id, db_path=db_path)
    if not nom.strip():
        raise UtilisateurValidationError("Le nom est obligatoire.")
    if not prenom.strip():
        raise UtilisateurValidationError("Le prénom est obligatoire.")

    if utilisateur.role == RoleUtilisateur.ADMIN and role != RoleUtilisateur.ADMIN and utilisateur.actif:
        _verifier_admin_restant_apres_exclusion(utilisateur_id, db_path=db_path)

    utilisateur_repository.modifier_informations(utilisateur_id, nom.strip(), prenom.strip(), role, db_path=db_path)
    logger.info("Utilisateur modifié : id=%s", utilisateur_id)
    return utilisateur_repository.obtenir_par_id(utilisateur_id, db_path=db_path)


def _verifier_admin_restant_apres_exclusion(utilisateur_id: int, db_path: DbPath) -> None:
    """Lève DernierAdminError si exclure cet utilisateur laisserait zéro ADMIN actif."""
    admins_restants = utilisateur_repository.compter_admins_actifs(db_path=db_path, exclure_id=utilisateur_id)
    if admins_restants == 0:
        raise DernierAdminError(
            "Impossible d'effectuer cette opération : le système doit toujours conserver "
            "au moins un administrateur actif."
        )


def desactiver_utilisateur(utilisateur_id: int, db_path: DbPath = None) -> Utilisateur:
    """Désactive un utilisateur (il reste conservé en base, jamais supprimé). Protège le dernier ADMIN actif."""
    utilisateur = obtenir_utilisateur(utilisateur_id, db_path=db_path)
    if utilisateur.role == RoleUtilisateur.ADMIN and utilisateur.actif:
        _verifier_admin_restant_apres_exclusion(utilisateur_id, db_path=db_path)

    utilisateur_repository.changer_statut_actif(utilisateur_id, actif=False, db_path=db_path)
    logger.info("Utilisateur désactivé : id=%s", utilisateur_id)
    return utilisateur_repository.obtenir_par_id(utilisateur_id, db_path=db_path)


def activer_utilisateur(utilisateur_id: int, db_path: DbPath = None) -> Utilisateur:
    obtenir_utilisateur(utilisateur_id, db_path=db_path)
    utilisateur_repository.changer_statut_actif(utilisateur_id, actif=True, db_path=db_path)
    logger.info("Utilisateur activé : id=%s", utilisateur_id)
    return utilisateur_repository.obtenir_par_id(utilisateur_id, db_path=db_path)


def changer_mot_de_passe(
    utilisateur_id: int, mot_de_passe_actuel: str, nouveau_mot_de_passe: str, db_path: DbPath = None
) -> None:
    """
    Changement de mot de passe PAR L'UTILISATEUR LUI-MÊME (section 30) :
    exige la vérification du mot de passe actuel avant modification.
    Pour une réinitialisation par un administrateur (sans connaître
    l'ancien mot de passe), voir `reinitialiser_mot_de_passe`.
    """
    utilisateur = obtenir_utilisateur(utilisateur_id, db_path=db_path)
    if not verify_password(mot_de_passe_actuel, utilisateur.password_hash):
        raise UtilisateurValidationError("Le mot de passe actuel est incorrect.")
    _valider_mot_de_passe(nouveau_mot_de_passe)

    utilisateur_repository.changer_mot_de_passe(utilisateur_id, hash_password(nouveau_mot_de_passe), db_path=db_path)
    logger.info("Mot de passe changé par l'utilisateur : id=%s", utilisateur_id)


def reinitialiser_mot_de_passe(utilisateur_id: int, nouveau_mot_de_passe: str, db_path: DbPath = None) -> None:
    """Réinitialisation par un ADMIN (aucune vérification de l'ancien mot de passe)."""
    obtenir_utilisateur(utilisateur_id, db_path=db_path)
    _valider_mot_de_passe(nouveau_mot_de_passe)

    utilisateur_repository.changer_mot_de_passe(utilisateur_id, hash_password(nouveau_mot_de_passe), db_path=db_path)
    logger.info("Mot de passe réinitialisé par un administrateur : id=%s", utilisateur_id)


# ---------------------------------------------------------------------
# Réinitialisation complète des comptes (correction finale)
# ---------------------------------------------------------------------
# ATTENTION : opération destructrice et volontairement irréversible sur
# la seule table `utilisateurs`. Aucune donnée métier (enseignants,
# périodes, paie, documents, alertes, imports, statistiques) n'est
# touchée — cette fonction ne fait qu'une seule chose. L'audit
# historique (`audit_log`) est intégralement conservé : sa colonne
# `utilisateur` est un simple TEXTE (nom d'utilisateur au moment de
# l'action), jamais une clé étrangère vers `utilisateurs.id` — la
# suppression de tous les comptes ne peut donc jamais violer une
# contrainte d'intégrité référentielle sur cette table.

def reinitialiser_tous_les_comptes(confirmation: bool, db_path: DbPath = None) -> int:
    """
    Supprime définitivement TOUS les comptes utilisateurs, ramenant
    l'application à l'état « première initialisation administrateur »
    (le formulaire de création du premier compte réapparaîtra au
    prochain accès — voir utils/session_auth.py, logique déjà
    existante et inchangée, qui se déclenche dès que la table
    `utilisateurs` est vide).

    Toute session Streamlit déjà ouverte devient automatiquement
    invalide dès l'appel suivant, sans aucune action supplémentaire :
    `auth_service.revalider_session()` (module 19) recherche
    l'utilisateur en base à chaque page protégée et purge la session
    si son compte n'existe plus.

    Args:
        confirmation: doit être explicitement True — aucune valeur par
            défaut permissive, pour ne jamais déclencher cette
            opération par accident.

    Returns:
        Le nombre de comptes supprimés.

    Raises:
        ValueError: si `confirmation` n'est pas exactement True.
    """
    if confirmation is not True:
        raise ValueError(
            "Réinitialisation refusée : confirmation explicite requise (confirmation=True)."
        )

    with get_connection(db_path) as conn:
        nombre_avant = conn.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0]
        conn.execute("DELETE FROM utilisateurs")
        conn.commit()

    logger.warning(
        "Réinitialisation complète des comptes utilisateurs effectuée : %d compte(s) supprimé(s). "
        "Données métier non affectées. Audit historique conservé.",
        nombre_avant,
    )
    return nombre_avant
