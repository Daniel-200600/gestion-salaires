"""
Favicon, logo et configuration de production.
"""

import ast
import re
import tomllib
from pathlib import Path

from PIL import Image

from config import settings

RACINE = Path(__file__).resolve().parent.parent


def test_favicon_png_valide_et_carre():
    assert settings.FAVICON_PATH == settings.BASE_DIR / "assets" / "favicon.png"
    with Image.open(settings.FAVICON_PATH) as image:
        assert image.format == "PNG"
        assert image.width == image.height >= 32


def test_favicon_ico_multi_tailles_pour_l_executable():
    with Image.open(settings.FAVICON_ICO_PATH) as image:
        assert image.format == "ICO"
        tailles = image.info.get("sizes") or {image.size}
        assert {(16, 16), (32, 32), (48, 48)} <= set(tailles)


def test_logos_presents_et_legers():
    for chemin in (settings.LOGO_HORIZONTAL_PATH, settings.LOGO_SYMBOLE_PATH, settings.FAVICON_PATH):
        assert chemin.exists(), chemin
        assert chemin.stat().st_size < 100_000, f"{chemin.name} trop lourd"


def test_app_utilise_le_favicon_et_non_un_emoji():
    arbre = ast.parse((RACINE / "app.py").read_text(encoding="utf-8"))
    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "set_page_config"
    ]
    assert len(appels) == 1
    page_icon = next(k.value for k in appels[0].keywords if k.arg == "page_icon")
    assert "FAVICON_PATH" in ast.unparse(page_icon)
    assert not isinstance(page_icon, ast.Constant)


def test_logo_affiche_dans_l_application():
    contenu = (RACINE / "app.py").read_text(encoding="utf-8")
    assert "st.logo(" in contenu and "LOGO_HORIZONTAL_PATH" in contenu


def test_configuration_streamlit_de_production():
    with open(RACINE / ".streamlit" / "config.toml", "rb") as fichier:
        config = tomllib.load(fichier)
    assert config["client"]["toolbarMode"] == "viewer"  # pas de bouton « Deploy »
    assert config["client"]["showErrorLinks"] is False
    assert config["browser"]["gatherUsageStats"] is False
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", config["theme"]["primaryColor"])


def test_executable_embarque_favicon_documentation_et_configuration():
    spec = (RACINE / "GestionPaie.spec").read_text(encoding="utf-8")
    assert 'icon=str(RACINE / "assets" / "favicon.ico")' in spec
    for image in ("favicon.png", "favicon.ico", "logo_horizontal.png", "logo_symbole.png"):
        assert f'"{image}"' in spec
    # Le logo d'un établissement n'est jamais embarqué dans l'exécutable.
    lignes_de_code = [l for l in spec.splitlines() if not l.strip().startswith("#")]
    assert not any("logo_etablissement" in l for l in lignes_de_code)
    assert '".streamlit" / "config.toml"' in spec
    for document in ("guide_utilisateur.md", "guide_administrateur.md", "politique_confidentialite.md",
                     "conditions_utilisation.md"):
        assert document in spec


def test_lanceur_applique_la_configuration_de_production():
    import streamlit.config as configuration_streamlit

    import launcher

    configuration_streamlit.get_config_options()
    options = launcher.options_configuration_production()
    assert options["client.toolbarMode"] == "viewer"
    assert options["theme.primaryColor"]
    inconnues = [cle for cle in options if cle not in configuration_streamlit._config_options]
    assert inconnues == []
