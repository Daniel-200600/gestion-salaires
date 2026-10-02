# -*- mode: python ; coding: utf-8 -*-
"""
Spécification PyInstaller pour produire GestionPaie.exe (module 20).

IMPORTANT — honnêteté sur les limites de cet environnement : ce
fichier a été écrit et relu attentivement, et `launcher.py` a été
testé avec succès (serveur Streamlit fonctionnel, HTTP 200) sur la
machine Linux de développement — mais AUCUN exécutable Windows n'a pu
être réellement produit ni testé ici, faute d'un environnement Windows
et de PyInstaller lui-même disponibles dans ce conteneur. Voir
docs/build_windows.md pour la procédure exacte à exécuter sur une
machine Windows disposant de Python et PyInstaller.

Usage (sur une machine Windows, une fois PyInstaller installé) :
    pyinstaller GestionPaie.spec
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

RACINE = Path(SPECPATH)  # noqa: F821 — SPECPATH est injecté par PyInstaller à l'exécution du spec

block_cipher = None

# Ressources en LECTURE SEULE nécessaires au fonctionnement : le template
# Word, le schéma SQL, et l'arborescence Streamlit multipage (app.py +
# ui_pages/), sans lesquelles l'application ne peut ni générer de bulletin ni
# afficher sa navigation. Jamais les données utilisateur (data/), qui ne
# doivent jamais être embarquées dans l'exécutable (voir config/paths.py).
donnees_incluses = [
    (str(RACINE / "app.py"), "."),
    (str(RACINE / "ui_pages"), "ui_pages"),
    (str(RACINE / "templates" / "bulletin_template.docx"), "templates"),
    # Modèle PDF standard du bulletin et description de ses zones.
    (str(RACINE / "templates" / "bulletin_modele_standard.pdf"), "templates"),
    (str(RACINE / "templates" / "bulletin_modele_standard.json"), "templates"),
    (str(RACINE / "database" / "schema.sql"), "database"),
    # Identité visuelle de l'application (jamais le logo d'un établissement :
    # assets/logo_etablissement.png reste hors de l'exécutable).
    *[(str(RACINE / "assets" / nom), "assets") for nom in (
        "favicon.png", "favicon.ico", "apple-touch-icon.png", "logo_horizontal.png", "logo_symbole.png")],
    # Configuration Streamlit de production (thème, barre d'outils).
    (str(RACINE / ".streamlit" / "config.toml"), ".streamlit"),
    # Documentation intégrée affichée dans l'application.
    (str(RACINE / "docs" / "guide_utilisateur.md"), "docs"),
    (str(RACINE / "docs" / "guide_administrateur.md"), "docs"),
    (str(RACINE / "docs" / "politique_confidentialite.md"), "docs"),
    (str(RACINE / "docs" / "conditions_utilisation.md"), "docs"),
    (str(RACINE / "docs" / "a_propos.md"), "docs"),
]
# Streamlit lit ses propres fichiers (interface web, métadonnées de paquet)
# à l'exécution : ils doivent être embarqués explicitement.
# Sans les exemples et « skills » de développement livrés avec Streamlit
# (streamlit/.agents/...) : inutiles, et leurs chemins très profonds
# dépassent la limite de 260 caractères de Windows à l'installation.
donnees_incluses += [
    (source, destination) for source, destination in collect_data_files("streamlit")
    if ".agents" not in Path(source).parts
] + copy_metadata("streamlit")

# app.py et ui_pages/ sont exécutés par Streamlit, pas importés : PyInstaller
# ne voit donc pas les modules qu'ils utilisent. On les déclare tous.
modules_application = [
    module for paquet in ("config", "database", "exports", "models", "services", "templates", "utils")
    for module in collect_submodules(paquet)
]

analyse = Analysis(
    [str(RACINE / "launcher.py")],
    pathex=[str(RACINE)],
    binaries=[],
    datas=donnees_incluses,
    hiddenimports=[
        # Streamlit et ses dépendances de rendu utilisent de l'import
        # dynamique que l'analyse statique de PyInstaller ne détecte pas
        # toujours automatiquement — listés explicitement par précaution.
        "streamlit",
        "streamlit.web.bootstrap",
        "streamlit.runtime.scriptrunner.magic_funcs",
        "openpyxl",
        "docx",
        "pandas",
        # Bulletins PDF (modèles PDF importés et modèle PDF standard).
        "pymupdf",
        # Vérification des clés de licence (services/licence_service.py).
        "cryptography",
        *modules_application,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analyse.pure, analyse.zipped_data, cipher=block_cipher)

# Mode « dossier » (onedir) : démarrage rapide, sans décompression à chaque
# lancement ; c'est ce dossier que l'installateur (installer/GestionPaie.iss)
# copie sur le poste.
exe = EXE(
    pyz,
    analyse.scripts,
    [],
    exclude_binaries=True,
    name="GestionPaie",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RACINE / "assets" / "favicon.ico"),
)

coll = COLLECT(
    exe,
    analyse.binaries,
    analyse.zipfiles,
    analyse.datas,
    strip=False,
    upx=False,
    name="GestionPaie",
)
