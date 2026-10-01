"""
Service d'authentification (module 11).

Gère la vérification des identifiants, la mise à jour de la dernière
connexion, la limitation simple des tentatives répétées (section 28),
et la journalisation systématique dans l'audit métier — sans jamais
dépendre de Streamlit (entièrement testable en isolation, section 8).

La gestion de session (st.session_state) reste du ressort de
utils/session_auth.py, seul module du projet autorisé à connaître à
la fois l'authentification ET Streamlit.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

from config.settings import LOGIN_LOCKOUT_SECONDES, MAX_LOGIN_ATTEMPTS
from database.repositories import audit_log_repository, utilisateur_repository
from models.audit_log import AuditLog
from models.enums import TypeActionAudit
from models.utilisateur import Utilisateur
from utils.security import verify_password

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.auth_service")

MESSAGE_IDENTIFIANTS_INCORRECTS = "Nom d'utilisateur ou mot de passe incorrect."


@dataclass
class ResultatConnexion:
    reussie: bool
    message: str
    utilisateur: Optional[Utilisateur] = None


# Compteur de tentatives échouées en mémoire de processus : {username_normalise: [horodatages]}.
# Volontairement simple (pas de table dédiée, pas de dépendance
# externe) — une application locale mono-processus n'a pas besoin de
# plus, conformément à la consigne de ne pas construire un système de
# cybersécurité complexe (section 28). Réinitialisé si l'application
# redémarre : limite documentée, acceptée pour cet usage.
_tentatives_echouees: Dict[str, List[float]] = {}


def _cle(username: str) -> str:
    return (username or "").strip().lower()


def _purger_anciennes_tentatives(cle: str) -> None:
    limite = time.time() - LOGIN_LOCKOUT_SECONDES
    _tentatives_echouees[cle] = [t for t in _tentatives_echouees.get(cle, []) if t > limite]


def _verrouille(cle: str) -> Optional[int]:
    """Retourne le nombre de secondes restant avant déverrouillage, ou None si pas verrouillé."""
    _purger_anciennes_tentatives(cle)
    tentatives = _tentatives_echouees.get(cle, [])
    if len(tentatives) < MAX_LOGIN_ATTEMPTS:
        return None
    plus_ancienne = min(tentatives)
    attente_restante = int(LOGIN_LOCKOUT_SECONDES - (time.time() - plus_ancienne))
    return attente_restante if attente_restante > 0 else None


def _enregistrer_echec(cle: str) -> None:
    _tentatives_echouees.setdefault(cle, []).append(time.time())


def _reinitialiser_tentatives(cle: str) -> None:
    _tentatives_echouees.pop(cle, None)


def _journaliser(type_action: TypeActionAudit, utilisateur_id: Optional[int], details: str, db_path: DbPath = None) -> None:
    entree = AuditLog(type_action=type_action, entite="utilisateur", entite_id=utilisateur_id, details=details)
    audit_log_repository.enregistrer(entree, db_path=db_path)


def connecter(username: str, mot_de_passe: str, db_path: DbPath = None) -> ResultatConnexion:
    """
    Tente une connexion. Ne révèle JAMAIS si c'est le nom d'utilisateur
    ou le mot de passe qui est incorrect (section 12), et ne journalise
    jamais le mot de passe lui-même (section 26/32).
    """
    cle = _cle(username)

    attente = _verrouille(cle)
    if attente is not None:
        message = f"Trop de tentatives échouées. Réessayez dans {attente} seconde(s)."
        logger.warning("Connexion bloquée temporairement pour '%s' (%ss restantes).", cle, attente)
        return ResultatConnexion(reussie=False, message=message)

    utilisateur = utilisateur_repository.obtenir_par_username(username, db_path=db_path) if cle else None

    mot_de_passe_valide = utilisateur is not None and verify_password(mot_de_passe, utilisateur.password_hash)
    compte_utilisable = utilisateur is not None and utilisateur.actif

    if utilisateur is None or not mot_de_passe_valide or not compte_utilisable:
        _enregistrer_echec(cle)
        # Le nom d'utilisateur n'est PAS journalisé nommément s'il n'existe
        # pas (éviterait de confirmer son existence) ; s'il existe, on
        # journalise seulement l'id, jamais le mot de passe saisi.
        _journaliser(
            TypeActionAudit.CONNEXION_ECHOUEE,
            utilisateur.id if utilisateur is not None else None,
            f"Tentative échouée pour '{cle}'" if utilisateur is None else f"Tentative échouée : {utilisateur.username}",
            db_path,
        )
        logger.info("Échec de connexion pour '%s'.", cle)
        return ResultatConnexion(reussie=False, message=MESSAGE_IDENTIFIANTS_INCORRECTS)

    _reinitialiser_tentatives(cle)
    utilisateur_repository.mettre_a_jour_derniere_connexion(utilisateur.id, db_path=db_path)
    _journaliser(TypeActionAudit.CONNEXION_REUSSIE, utilisateur.id, f"Connexion réussie : {utilisateur.username}", db_path)
    logger.info("Connexion réussie : %s (id=%s)", utilisateur.username, utilisateur.id)

    utilisateur_a_jour = utilisateur_repository.obtenir_par_id(utilisateur.id, db_path=db_path)
    return ResultatConnexion(reussie=True, message="Connexion réussie.", utilisateur=utilisateur_a_jour)


def deconnecter(utilisateur_id: Optional[int], username: Optional[str] = None, db_path: DbPath = None) -> None:
    """Journalise une déconnexion. La purge de st.session_state reste du ressort de utils/session_auth.py."""
    _journaliser(TypeActionAudit.DECONNEXION, utilisateur_id, f"Déconnexion : {username or ''}".strip(), db_path)
    logger.info("Déconnexion : id=%s", utilisateur_id)


def revalider_session(utilisateur_id: int, db_path: DbPath = None) -> Optional["object"]:
    """
    Revérifie l'état réel d'un utilisateur en base (module 19,
    hardening) : une session ouverte ne doit jamais continuer à
    fonctionner avec des privilèges obsolètes ou pour un compte
    désactivé entre-temps par un administrateur — le cache en session
    (rôle, nom) doit toujours être rafraîchi depuis la base à chaque
    page protégée, jamais seulement fait confiance depuis la connexion
    initiale.

    Retourne l'utilisateur à jour si le compte existe toujours et est
    actif, sinon None (la session appelante doit alors être purgée et
    l'utilisateur renvoyé à l'écran de connexion).
    """
    utilisateur = utilisateur_repository.obtenir_par_id(utilisateur_id, db_path=db_path)
    if utilisateur is None or not utilisateur.actif:
        return None
    return utilisateur
