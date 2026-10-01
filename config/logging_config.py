"""
Configuration du logging technique de l'application (module 10).

Distinct de l'audit métier (database.repositories.audit_log_repository,
table `audit_log`) : ce module gère les LOGS TECHNIQUES (erreurs,
diagnostics, sauvegardes/restaurations, opérations de maintenance),
jamais les actions métier elles-mêmes (déjà tracées par l'audit).

Écrit dans un fichier journal (config.settings.LOG_FILE) avec rotation
automatique pour ne jamais grossir indéfiniment, et jamais de mot de
passe ni de donnée personnelle sensible dans les messages.
"""

import logging
from logging.handlers import RotatingFileHandler

from config.settings import LOG_FILE, ensure_data_dirs

_NOM_LOGGER_RACINE = "salaires_app"
_TAILLE_MAX_OCTETS = 1_000_000  # 1 Mo par fichier
_NOMBRE_FICHIERS_CONSERVES = 3

_configure = False


def configurer_logging() -> None:
    """
    Configure le logger racine de l'application. Idempotent : peut être
    appelée plusieurs fois sans dupliquer les handlers (utile car
    appelée depuis plusieurs pages Streamlit qui se rechargent souvent).
    """
    global _configure
    if _configure:
        return

    ensure_data_dirs()

    logger_racine = logging.getLogger(_NOM_LOGGER_RACINE)
    logger_racine.setLevel(logging.INFO)

    gestionnaire = RotatingFileHandler(
        LOG_FILE, maxBytes=_TAILLE_MAX_OCTETS, backupCount=_NOMBRE_FICHIERS_CONSERVES, encoding="utf-8"
    )
    gestionnaire.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger_racine.addHandler(gestionnaire)

    _configure = True


def obtenir_logger(nom: str) -> logging.Logger:
    """
    Retourne un logger enfant du logger racine de l'application (ex :
    `obtenir_logger("backup_service")`). Configure automatiquement le
    logging s'il ne l'était pas encore.
    """
    configurer_logging()
    return logging.getLogger(f"{_NOM_LOGGER_RACINE}.{nom}")


def lire_dernieres_lignes(nombre_lignes: int = 200) -> list:
    """
    Lit les `nombre_lignes` dernières lignes du fichier de log courant,
    sans jamais charger un fichier volumineux entièrement en mémoire :
    lecture en flux depuis la fin (buffer borné).

    Retourne une liste vide si le fichier n'existe pas encore (aucune
    entrée journalisée).
    """
    if not LOG_FILE.exists():
        return []

    # Lecture bornée : on ne conserve jamais plus que nombre_lignes en
    # mémoire, quelle que soit la taille réelle du fichier sur disque.
    from collections import deque

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as fichier:
        dernieres = deque(fichier, maxlen=nombre_lignes)
    return list(dernieres)
