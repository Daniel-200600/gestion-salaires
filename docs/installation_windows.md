# Installation Windows — Gestion des Salaires

**Avertissement honnête** : cet environnement de développement est Linux et ne dispose ni de Windows ni de PyInstaller. `GestionPaie.exe` n'a donc **pas été réellement construit ni testé sur Windows**. Ce document explique comment l'installer une fois que quelqu'un l'a construit (voir `docs/build_windows.md`), et documente précisément ce qui a été vérifié versus ce qui reste à valider.

## Ce qui a été réellement vérifié

- `launcher.py` (le point d'entrée destiné à l'exécutable) a été **exécuté avec succès** sur la machine de développement : il lance correctement le serveur Streamlit et sert l'application (HTTP 200 confirmé).
- La résolution de chemins (`config/paths.py`) a été testée pour les deux cas — développement normal et environnement "gelé" simulé (`sys.frozen = True`) — avec 8 tests automatisés dédiés, tous passants.
- `GestionPaie.spec` a été écrit et relu, mais **jamais exécuté** (nécessite PyInstaller sur une machine capable de produire un binaire Windows).

## Ce qui reste à valider par quelqu'un disposant d'un PC Windows

- La construction réelle de `GestionPaie.exe` (voir `docs/build_windows.md`).
- Le lancement par double-clic sur une machine Windows vierge (sans Python installé).
- La création effective d'un raccourci et d'un installateur (`GestionPaie_Setup.exe`) — aucun outil d'installateur (Inno Setup, NSIS...) n'est disponible dans cet environnement pour le produire.

## Procédure d'installation prévue (une fois l'exécutable construit)

1. Copier `GestionPaie.exe` (et le dossier `data/` s'il existe déjà, pour une réinstallation) dans un dossier de votre choix, par exemple `C:\GestionPaie\`.
2. Double-cliquer sur `GestionPaie.exe`.
3. Le navigateur par défaut s'ouvre automatiquement sur l'application (`http://localhost:8501`).
4. Au tout premier lancement, un formulaire de création du premier compte administrateur s'affiche — aucun mot de passe par défaut n'existe.
5. Les données (base SQLite, sauvegardes, documents, logs) sont automatiquement créées dans `%APPDATA%\GestionPaie\` (ou dans un dossier `data\` situé à côté de `GestionPaie.exe` si vous en créez un vous-même, pour une installation portable — voir `config/paths.py`).

## Désinstallation

Sans installateur dédié : supprimez simplement le dossier contenant `GestionPaie.exe`, puis, si vous souhaitez également supprimer les données, le dossier `%APPDATA%\GestionPaie\`.

## Dépannage

- **Rien ne se passe au double-clic** : lancez l'exécutable depuis une invite de commandes (`GestionPaie.exe`) pour voir un éventuel message d'erreur.
- **Le navigateur ne s'ouvre pas automatiquement** : ouvrez manuellement `http://localhost:8501`.
- **« Fichier principal introuvable »** : le packaging a omis `app.py` des ressources embarquées — reconstruire selon `docs/build_windows.md`.
