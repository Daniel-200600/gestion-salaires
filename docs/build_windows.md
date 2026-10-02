# Procédure de build Windows — Gestion des Salaires

Procédure exécutée et vérifiée le 2 octobre 2026 (Windows 11, Python 3.11,
PyInstaller 6.22, Inno Setup 6) : exécutable construit, 21 pages ouvertes sans
erreur, installation, lancement et désinstallation testés.

## Prérequis (poste du développeur uniquement)

- Python 3.11 et les dépendances : `pip install -r requirements.txt`
- PyInstaller : `pip install pyinstaller`
- Inno Setup 6 (gratuit) : `winget install JRSoftware.InnoSetup`

Le poste de l'utilisateur n'a besoin ni de Python ni d'aucun de ces outils.

## 1. Vérifier les tests

```
python -m pytest -q
```

## 2. Construire l'exécutable

```
python -m PyInstaller --noconfirm GestionPaie.spec
```

Résultat : `dist\GestionPaie\` (mode dossier : `GestionPaie.exe` + `_internal\`).
Ne jamais laisser de dossier `data\` dans `dist\GestionPaie\` : l'application
passerait en mode portable et y rangerait ses données.

Points du fichier `GestionPaie.spec` à connaître :
- `app.py` et `ui_pages/` sont exécutés par Streamlit, pas importés : tous les
  modules de l'application sont déclarés (`collect_submodules`) ;
- les fichiers web et les métadonnées de Streamlit sont embarqués, sans ses
  exemples de développement (`streamlit/.agents`, chemins trop longs) ;
- le logo d'un établissement (`assets/logo_etablissement.png`) n'est jamais
  embarqué.

`launcher.py` charge les options Streamlit avant le démarrage
(`bootstrap.load_config_options`) et désactive `global.developmentMode` :
sans cela, l'exécutable affiche une page blanche (erreur 404).

## 3. Construire l'installateur

```
cd installer
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" GestionPaie.iss
```

Résultat : `dist_installer\Setup_GestionPaie_<version>.exe`. L'installateur
affiche le contrat de licence (`installer/LICENCE_UTILISATION.txt`), installe
l'application (pour l'utilisateur courant, ou pour tous les utilisateurs avec
droits administrateur), crée les raccourcis et un désinstalleur.

## Données de l'utilisateur

Base, sauvegardes, modèles de bulletin importés et modèles propres à
l'établissement : `%APPDATA%\GestionPaie\` (voir `config/paths.py`). Une mise à
jour ou une désinstallation n'y touche pas. L'en-tête, le logo et la signature de
l'établissement se règlent après installation, dans Administration › Paramètres :
aucun fichier à copier.

## Avertissement Windows

L'exécutable n'est pas signé : à la première installation, Windows SmartScreen
affiche « Windows a protégé votre ordinateur » (« Informations complémentaires »
puis « Exécuter quand même »). Un certificat de signature de code (payant)
supprime cet avertissement.
