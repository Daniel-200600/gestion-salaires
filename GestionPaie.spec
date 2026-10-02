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
    # Identité visuelle : favicon, logo (affichés dans le navigateur).
    (str(RACINE / "assets"), "assets"),
    # Configuration Streamlit de production (thème, barre d'outils).
    (str(RACINE / ".streamlit" / "config.toml"), ".streamlit"),
    # Documentation intégrée affichée dans l'application.
    (str(RACINE / "docs" / "guide_utilisateur.md"), "docs"),
    (str(RACINE / "docs" / "guide_administrateur.md"), "docs"),
    (str(RACINE / "docs" / "politique_confidentialite.md"), "docs"),
    (str(RACINE / "docs" / "conditions_utilisation.md"), "docs"),
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

exe = EXE(
    pyz,
    analyse.scripts,
    analyse.binaries,
    analyse.zipfiles,
    analyse.datas,
    [],
    name="GestionPaie",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RACINE / "assets" / "favicon.ico"),
)
