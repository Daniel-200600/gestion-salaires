"""
Paramètres globaux de l'application.

Toute valeur susceptible de changer (chemins, taux fixes, etc.) doit
passer par ce module plutôt que d'être codée en dur ailleurs.
Cela facilite notamment le futur empaquetage en application Windows.
"""

from decimal import Decimal
from pathlib import Path

from config.paths import resource_root, user_data_root

# ---------------------------------------------------------------------
# Identité et version de l'application (module 20, section 23)
# ---------------------------------------------------------------------
# Source UNIQUE du numéro de version — tout autre endroit qui doit
# l'afficher (page d'accueil, pied de page, README généré) importe
# cette constante plutôt que de la dupliquer.
NOM_APPLICATION = "Gestion des Salaires"
# Auteur et contact affichés sur la page « À propos ».
AUTEUR = "Daniel Tchomtchi"
CONTACT_AUTEUR = "tchomtchidaniel@gmail.com"
VERSION = "1.4.0"

# Racine des ressources de l'application (lecture seule une fois installée :
# templates, schéma SQL). Consciente de PyInstaller (module 20) — voir
# config/paths.py. En développement, identique à l'ancien calcul
# (dossier racine du projet) : aucun changement de comportement.
BASE_DIR = resource_root()

# Dossier et fichier de la base de données SQLite — racine des DONNÉES
# UTILISATEUR (inscriptible, persistante), distincte de BASE_DIR une fois
# l'application empaquetée. En développement, reste `<projet>/data` comme avant.
DATA_DIR = user_data_root()
DB_PATH = DATA_DIR / "app.db"

# Dossier des sauvegardes (utilisé plus tard par backup_service)
BACKUP_DIR = DATA_DIR / "backups"

# Dossier des journaux techniques (module 10)
LOGS_DIR = DATA_DIR / "logs"
LOG_FILE = LOGS_DIR / "app.log"

# Fichier de persistance des paramètres de l'établissement (module 10) —
# séparé de la base SQLite : ce sont des réglages d'application modifiables
# par l'administrateur, pas des données métier soumises à des contraintes
# référentielles.
PARAMETRES_PATH = DATA_DIR / "parametres_etablissement.json"
# Modèles de bulletin importés par l'administrateur (Word ou PDF).
MODELES_BULLETIN_DIR = DATA_DIR / "modeles_bulletin"

# Emplacement du schéma SQL de référence
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

# Identité visuelle (ressources en lecture seule, embarquées dans
# l'exécutable : voir GestionPaie.spec).
ASSETS_DIR = BASE_DIR / "assets"
FAVICON_PATH = ASSETS_DIR / "favicon.png"
FAVICON_ICO_PATH = ASSETS_DIR / "favicon.ico"
LOGO_HORIZONTAL_PATH = ASSETS_DIR / "logo_horizontal.png"
LOGO_SYMBOLE_PATH = ASSETS_DIR / "logo_symbole.png"
# Logo de l'établissement : fichier LOCAL, exclu de Git, utilisé seulement
# par `templates/build_template.py --etablissement` (en-tête du bulletin).
LOGO_ETABLISSEMENT_PATH = ASSETS_DIR / "logo_etablissement.png"
# Documentation intégrée à l'application (guides, politique, conditions).
DOCS_DIR = BASE_DIR / "docs"

# Modèles standard propres à l'établissement (en-tête et logo réels),
# produits par `templates/build_template.py --etablissement` dans le dossier
# de données (jamais publié) : ils remplacent les modèles neutres livrés
# dans templates/ lorsqu'ils existent.
MODELES_ETABLISSEMENT_DIR = DATA_DIR / "modeles_etablissement"


def chemin_modele_standard(nom_fichier: str) -> Path:
    """Modèle standard de l'établissement s'il a été produit, sinon le modèle neutre livré."""
    propre = MODELES_ETABLISSEMENT_DIR / nom_fichier
    return propre if propre.exists() else BASE_DIR / "templates" / nom_fichier

# Taux de taxe par défaut appliqué sur la base taxable (5 %).
# C'est la valeur initiale : l'administrateur peut définir un autre taux
# (ex. 5,5 %) dans Administration › Paramètres ; chaque période conserve
# son propre taux, figé à la validation (services/parametres_paie_service.py).
# Decimal, jamais float : ce taux est utilisé directement dans des
# calculs monétaires par services/paie_service.py (moteur de calcul de
# paie) et ne doit jamais introduire d'imprécision flottante.
TAUX_TAXE = Decimal("0.05")

# ---------------------------------------------------------------------
# En-tête institutionnelle du bulletin de solde (module 07)
# ---------------------------------------------------------------------
# Centralisé ici plutôt que codé en dur dans templates/build_template.py,
# afin qu'un changement d'établissement ne nécessite pas de modifier le
# script de génération du template. Valeurs neutres par défaut : chaque
# établissement remplace la région, les délégations et son nom.
ETABLISSEMENT_ENTETE_FR = [
    "REPUBLIQUE DU CAMEROUN",
    "Paix – Travail – Patrie",
    "REGION",
    "DELEGATION REGIONALE DES ENSEIGNEMENTS SECONDAIRES",
    "DELEGATION DEPARTEMENTALE",
    "NOM DE L'ETABLISSEMENT",
]
ETABLISSEMENT_ENTETE_EN = [
    "REPUBLIC OF CAMEROON",
    "Peace – Work – Fatherland",
    "REGION",
    "REGIONAL DELEGATION OF SECONDARY EDUCATION",
    "DIVISIONAL DELEGATION",
    "SCHOOL NAME",
]

# Lieu de signature du bulletin (modèle : "Done at Yaoundé on the / Fait
# à Yaoundé le:"). Non disponible ailleurs dans la base -> centralisé ici
# plutôt qu'inventé au niveau du template.
LIEU_SIGNATURE = "Yaoundé"

# Titre du signataire (modèle : "Le Coordonateur Général/The General
# Coordinator"). Le NOM du signataire n'est pas disponible dans la base
# et n'est délibérément pas inventé : seul le titre de fonction, déjà
# présent dans le modèle officiel, est reproduit.
TITRE_SIGNATAIRE_FR = "Le Coordonateur Général/"
TITRE_SIGNATAIRE_EN = "The General Coordinator"

# Nombre de semaines par période de paie
NB_SEMAINES_PAR_PERIODE = 5

# ---------------------------------------------------------------------
# Sécurité applicative (module 11) — aucun secret, uniquement des
# réglages de comportement.
# ---------------------------------------------------------------------
# Durée d'inactivité (en secondes) après laquelle la session est
# automatiquement invalidée. Valeur par défaut raisonnable (2 heures)
# pour un usage administratif local.
SESSION_TIMEOUT_SECONDES = 2 * 60 * 60

# Longueur minimale imposée à un mot de passe (politique simple,
# volontairement non artificiellement complexe — section 31).
PASSWORD_MIN_LENGTH = 8

# Nombre de tentatives de connexion échouées tolérées avant un délai
# d'attente temporaire, et durée de ce délai (secondes). Limitation
# raisonnable pour une application locale, pas un système anti-bruteforce
# complet (section 28).
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDES = 60


def ensure_data_dirs() -> None:
    """Crée les dossiers de données s'ils n'existent pas encore."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
