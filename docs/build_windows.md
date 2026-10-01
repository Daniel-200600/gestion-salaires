# Procédure de build Windows — Gestion des Salaires

**Honnêteté préalable** : cette procédure n'a pas pu être exécutée dans l'environnement de développement (Linux, sans PyInstaller ni Windows). Elle est écrite avec précision à partir de la configuration réelle du projet (`GestionPaie.spec`, `launcher.py`, `config/paths.py`), mais doit être vérifiée par une exécution réelle sur une machine Windows avant toute diffusion.

## Prérequis

- Windows 10/11
- Python 3.11 ou 3.12 (la même version majeure que celle utilisée en développement)
- Les dépendances du projet : `pip install -r requirements.txt`
- PyInstaller : `pip install pyinstaller`

## Étapes

1. Copier l'intégralité du dossier `salaires_app/` sur la machine Windows (ou cloner/extraire `salaires_app_production_finale.zip`).

2. Ouvrir une invite de commandes dans ce dossier et installer les dépendances :
   ```
   pip install -r requirements.txt
   pip install pyinstaller
   ```

3. Vérifier que les tests passent sur cette machine avant de construire quoi que ce soit :
   ```
   python -m pytest -q
   ```
   Résultat attendu : `931 passed, 3 skipped`.

4. Lancer la construction à partir du fichier de spécification déjà préparé :
   ```
   pyinstaller GestionPaie.spec
   ```
   Ceci doit produire `dist\GestionPaie.exe` (mode dossier unique — `console=False` dans le spec, donc sans fenêtre console visible).

5. **Tester immédiatement** l'exécutable produit :
   - Double-cliquer sur `dist\GestionPaie.exe`.
   - Vérifier que le navigateur s'ouvre sur `http://localhost:8501`.
   - Vérifier que le formulaire de création du premier administrateur s'affiche.
   - Créer un enseignant, une période, saisir des heures, générer un bulletin — vérifier que le fichier `.docx` est bien produit.
   - Vérifier l'emplacement réel des données créées (devrait être `%APPDATA%\GestionPaie\`, jamais dans le dossier temporaire d'extraction PyInstaller).

6. Si l'exécutable fonctionne, `dist\GestionPaie.exe` est la version livrable. Le dossier `build\` généré par PyInstaller est un dossier de travail intermédiaire, à ne pas distribuer.

## Icône (optionnelle)

`GestionPaie.spec` a `icon=None` — aucun logo institutionnel n'a été fourni (module 20, section 6, respecté à la lettre : ne jamais inventer un logo officiel). Pour ajouter un logo de l'établissement plus tard, placer un fichier `.ico` dans le projet et référencer son chemin dans `icon=` du spec, puis reconstruire.

## Création d'un installateur (`GestionPaie_Setup.exe`)

Aucun outil d'installateur (Inno Setup, NSIS, WiX) n'est disponible dans l'environnement de développement pour en produire un — cette étape n'a donc **pas été réalisée**. Une fois `GestionPaie.exe` validé (étape 5), un installateur simple peut être produit avec [Inno Setup](https://jrsoftware.org/isinfo.php) (gratuit) :

1. Installer Inno Setup sur la machine Windows.
2. Créer un script `.iss` minimal pointant vers `dist\GestionPaie.exe` comme fichier principal, avec création d'un raccourci menu Démarrer et bureau.
3. Compiler le script pour produire `GestionPaie_Setup.exe`.
4. Tester l'installation et la désinstallation sur une machine Windows propre.

Cette étape reste à réaliser et à tester par quelqu'un disposant de l'environnement Windows adéquat.

## Dépannage du build

- **`ModuleNotFoundError` au lancement de l'exe** : ajouter le module manquant à `hiddenimports` dans `GestionPaie.spec`, reconstruire.
- **Page blanche / navigation Streamlit absente** : vérifier que le dossier `pages/` a bien été inclus dans `datas` (déjà prévu dans le spec) et qu'il est extrait à côté de `app.py`.
- **Bulletin non généré / template introuvable** : vérifier que `templates/bulletin_template.docx` a bien été inclus dans `datas` (déjà prévu dans le spec).
