"""
Service de gestion des paramètres de l'établissement (module 10).

Persistance dans un fichier JSON (config.settings.PARAMETRES_PATH),
délibérément séparée de la base SQLite : ce sont des réglages
d'application modifiables par l'administrateur, pas des données
métier soumises à des contraintes référentielles. Survivent à un
redémarrage de l'application — contrairement à st.session_state, qui
ne fait que le temps d'une session navigateur.

IMPORTANT : ce module ne touche JAMAIS aux paramètres métier figés
(TAUX_TAXE, formules de paie) — ceux-ci restent exclusivement dans
config/settings.py et services/paie_service.py, non modifiables depuis
l'interface.
"""

import dataclasses
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from config.settings import PARAMETRES_PATH

logger = logging.getLogger("salaires_app.parametres_service")


@dataclass
class ParametresEtablissement:
    """Informations administratives générales de l'établissement (module 10, section 6)."""

    nom_etablissement: str = ""
    adresse: str = ""
    telephone: str = ""
    email: str = ""
    annee_scolaire: str = ""
    devise: str = "FCFA"
    nom_responsable: str = ""
    fonction_responsable: str = ""


def charger_parametres(chemin: Optional[Path] = None) -> ParametresEtablissement:
    """
    Charge les paramètres persistés. Retourne les valeurs par défaut
    (chaînes vides, devise "FCFA") si le fichier n'existe pas encore,
    est vide, ou est corrompu — jamais d'exception propagée à
    l'appelant pour un simple problème de lecture de configuration.
    """
    chemin_effectif = chemin if chemin is not None else PARAMETRES_PATH

    if not chemin_effectif.exists():
        return ParametresEtablissement()

    try:
        contenu = chemin_effectif.read_text(encoding="utf-8")
        if not contenu.strip():
            return ParametresEtablissement()
        donnees = json.loads(contenu)
    except (json.JSONDecodeError, OSError) as erreur:
        logger.warning("Impossible de lire les paramètres (%s) — valeurs par défaut utilisées.", erreur)
        return ParametresEtablissement()

    if not isinstance(donnees, dict):
        logger.warning("Fichier de paramètres au format inattendu — valeurs par défaut utilisées.")
        return ParametresEtablissement()

    # Ignore silencieusement toute clé inconnue (fichier écrit par une
    # version future, par exemple) : ne fait jamais échouer le chargement.
    champs_valides = {champ.name for champ in dataclasses.fields(ParametresEtablissement)}
    donnees_filtrees = {cle: valeur for cle, valeur in donnees.items() if cle in champs_valides}

    try:
        return ParametresEtablissement(**donnees_filtrees)
    except TypeError as erreur:
        logger.warning("Paramètres invalides (%s) — valeurs par défaut utilisées.", erreur)
        return ParametresEtablissement()


def enregistrer_parametres(parametres: ParametresEtablissement, chemin: Optional[Path] = None) -> None:
    """Persiste les paramètres sur disque (JSON lisible, indenté). Crée le dossier parent si nécessaire."""
    chemin_effectif = chemin if chemin is not None else PARAMETRES_PATH
    chemin_effectif.parent.mkdir(parents=True, exist_ok=True)
    chemin_effectif.write_text(json.dumps(asdict(parametres), ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Paramètres de l'établissement enregistrés.")
