"""
Résolution centralisée des chemins (module 20 — mise en production).

Sépare strictement deux notions distinctes, jusqu'ici confondues dans
`config/settings.py` (toutes deux calculées comme sous-dossiers du
code source) :

- **Ressources de l'application** (`resource_root`) : fichiers
  fournis avec le programme, en LECTURE SEULE une fois installé
  (`templates/bulletin_template.docx`, `database/schema.sql`). Une
  fois empaqueté avec PyInstaller, ces fichiers sont extraits dans un
  dossier temporaire désigné par `sys._MEIPASS` — jamais à côté de
  l'exécutable.

- **Données utilisateur** (`user_data_root`) : base SQLite,
  sauvegardes, documents générés, archives, logs, paramètres. Ces
  données doivent survivre aux mises à jour de l'application et
  rester accessibles en écriture — donc JAMAIS dans le dossier
  d'installation (qui peut être en lecture seule, ex.
  `Program Files` sous Windows) ni dans le dossier temporaire
  `_MEIPASS` (effacé à la fermeture en mode `--onefile`).

En développement (non empaqueté), les deux racines restent identiques
au comportement historique : le dossier racine du projet. Ce module
ne change donc RIEN au comportement des 923 tests existants, qui ne
s'exécutent jamais en environnement PyInstaller (`sys.frozen`
n'existe et n'est jamais vrai que dans un exécutable réellement gelé).
"""

import os
import sys
from pathlib import Path


def est_environnement_gele() -> bool:
    """Vrai uniquement à l'intérieur d'un exécutable produit par PyInstaller (ou équivalent)."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """
    Racine des ressources en lecture seule fournies avec l'application
    (templates, schéma SQL). Toujours `sys._MEIPASS` en environnement
    gelé ; sinon la racine du projet, exactement comme avant ce module.
    """
    if est_environnement_gele():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def user_data_root() -> Path:
    """
    Racine des données utilisateur (base, sauvegardes, documents,
    logs, paramètres) — toujours inscriptible et persistante.

    - Environnement gelé : dossier de données applicatives de l'OS
      (`%APPDATA%\\GestionPaie` sous Windows ; `~/.local/share/GestionPaie`
      ailleurs), créé s'il n'existe pas. Un dossier `data/` déjà présent
      à côté de l'exécutable (installation portable) est prioritaire
      s'il existe déjà, pour ne jamais fragmenter des données créées
      par une version antérieure de ce même exécutable.
    - Environnement de développement : `<racine_projet>/data`,
      comportement strictement identique à celui d'avant ce module.
    """
    if not est_environnement_gele():
        return Path(__file__).resolve().parent.parent / "data"

    dossier_portable = Path(sys.executable).resolve().parent / "data"
    if dossier_portable.exists():
        return dossier_portable

    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "GestionPaie"
