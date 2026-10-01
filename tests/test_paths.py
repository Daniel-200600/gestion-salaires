"""
Tests de config/paths.py (module 20 — production).
"""

import sys

import pytest

from config import paths


@pytest.fixture(autouse=True)
def _nettoyer_etat_frozen():
    """Isole chaque test des attributs `sys.frozen`/`sys._MEIPASS` qu'un test précédent aurait pu poser."""
    frozen_avant = getattr(sys, "frozen", None)
    meipass_avant = getattr(sys, "_MEIPASS", None)
    executable_avant = sys.executable
    yield
    if frozen_avant is None:
        if hasattr(sys, "frozen"):
            del sys.frozen
    else:
        sys.frozen = frozen_avant
    if meipass_avant is None:
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
    else:
        sys._MEIPASS = meipass_avant
    sys.executable = executable_avant


def test_environnement_developpement_non_gele():
    assert paths.est_environnement_gele() is False


def test_dev_resource_root_et_user_data_root_meme_racine():
    assert paths.resource_root() == paths.user_data_root().parent


def test_dev_user_data_root_est_dossier_data_du_projet():
    assert paths.user_data_root().name == "data"


def test_environnement_gele_detecte(tmp_path):
    sys.frozen = True
    assert paths.est_environnement_gele() is True


def test_gele_resource_root_utilise_meipass(tmp_path):
    sys.frozen = True
    sys._MEIPASS = str(tmp_path / "_MEIfake")
    assert paths.resource_root() == tmp_path / "_MEIfake"


def test_gele_user_data_root_jamais_dans_meipass(tmp_path):
    sys.frozen = True
    sys._MEIPASS = str(tmp_path / "_MEIfake")
    sys.executable = str(tmp_path / "dist" / "GestionPaie.exe")
    resultat = paths.user_data_root()
    assert "_MEIfake" not in str(resultat)


def test_gele_user_data_root_privilegie_dossier_portable_existant(tmp_path):
    dossier_dist = tmp_path / "dist"
    dossier_dist.mkdir()
    (dossier_dist / "data").mkdir()
    sys.frozen = True
    sys.executable = str(dossier_dist / "GestionPaie.exe")

    resultat = paths.user_data_root()
    assert resultat == dossier_dist / "data"


def test_gele_user_data_root_dossier_os_si_pas_de_portable(tmp_path):
    dossier_dist = tmp_path / "dist_sans_data"
    dossier_dist.mkdir()
    sys.frozen = True
    sys.executable = str(dossier_dist / "GestionPaie.exe")

    resultat = paths.user_data_root()
    assert str(dossier_dist) not in str(resultat)
    assert "GestionPaie" in str(resultat)
