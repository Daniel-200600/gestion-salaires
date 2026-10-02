"""
Lanceur autonome de l'application (module 20 — mise en production).

Ce fichier est le point d'entrée utilisé UNIQUEMENT pour produire
l'exécutable Windows (PyInstaller) — il ne remplace pas
`streamlit run app.py`, qui reste la méthode normale de lancement en
développement et n'est pas modifiée.

Lance Streamlit par programmation (`streamlit.web.bootstrap`) sur
`app.py`, résolu via `config.paths.resource_root()` pour fonctionner
identiquement en développement et une fois empaqueté (où `app.py` est
extrait par PyInstaller aux côtés de ce lanceur — voir
`GestionPaie.spec` et `docs/build_windows.md`).

Ouvre automatiquement le navigateur par défaut sur l'application, pour
un double-clic direct depuis l'exécutable sans étape supplémentaire
(section 19 du module 20).
"""

import sys
import urllib.request
import webbrowser
from pathlib import Path
from threading import Timer

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.paths import resource_root  # noqa: E402

PORT_PAR_DEFAUT = 8501
# Adresse locale uniquement : l'application n'est pas joignable depuis le
# réseau (voir aussi .streamlit/config.toml).
ADRESSE = "127.0.0.1"


def options_configuration_production() -> dict:
    """
    Lit `.streamlit/config.toml` embarqué avec l'application (thème,
    barre d'outils, statistiques d'usage désactivées) et le convertit en
    options Streamlit. Nécessaire pour l'exécutable : Streamlit ne
    cherche ce fichier que dans le dossier courant et le dossier
    personnel de l'utilisateur, pas dans le dossier des ressources.
    """
    chemin = resource_root() / ".streamlit" / "config.toml"
    if not chemin.exists():
        return {}
    try:
        import tomllib
    except ImportError:  # Python < 3.11 : la configuration par défaut de Streamlit s'applique
        return {}
    with open(chemin, "rb") as fichier:
        donnees = tomllib.load(fichier)
    options = {}
    for section, valeurs in donnees.items():
        for cle, valeur in valeurs.items():
            if isinstance(valeur, dict):
                for sous_cle, sous_valeur in valeur.items():
                    options[f"{section}.{cle}.{sous_cle}"] = sous_valeur
            else:
                options[f"{section}.{cle}"] = valeur
    return options


def _url(port: int) -> str:
    return f"http://{ADRESSE}:{port}"


def _ouvrir_navigateur(port: int) -> None:
    webbrowser.open(_url(port))


def application_deja_lancee(port: int = PORT_PAR_DEFAUT) -> bool:
    """Vrai si une instance de l'application répond déjà sur ce port."""
    try:
        with urllib.request.urlopen(f"{_url(port)}/_stcore/health", timeout=1) as reponse:
            return reponse.status == 200
    except OSError:
        return False


def main() -> None:
    from streamlit.web import bootstrap

    chemin_app = resource_root() / "app.py"
    if not chemin_app.exists():
        print(f"Erreur : fichier principal introuvable ({chemin_app}). Installation incomplète.")
        sys.exit(1)

    # Un second double-clic sur l'icône ne lance pas une seconde copie : il
    # rouvre simplement le navigateur sur l'application déjà lancée.
    if application_deja_lancee():
        _ouvrir_navigateur(PORT_PAR_DEFAUT)
        return

    Timer(1.5, _ouvrir_navigateur, args=(PORT_PAR_DEFAUT,)).start()

    options = {
        **options_configuration_production(),
        # Une fois empaqueté, Streamlit ne se trouve plus dans site-packages
        # et se croirait en mode développement : il ne servirait alors pas
        # son interface web (page blanche, erreur 404).
        "global.developmentMode": False,
        "server.port": PORT_PAR_DEFAUT,
        "server.address": ADRESSE,
        "server.headless": False,
        "browser.gatherUsageStats": False,
        "server.fileWatcherType": "none",
    }
    # Comme `streamlit run` : les options doivent être chargées AVANT le
    # démarrage, bootstrap.run() ne fait que surveiller leurs changements.
    bootstrap.load_config_options(flag_options=options)
    bootstrap.run(str(chemin_app), is_hello=False, args=[], flag_options=options)


if __name__ == "__main__":
    main()
