import sys
from pathlib import Path

# Permet d'importer les modules du projet (config, database, models)
# quand pytest est lancé depuis la racine de salaires_app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from database.initialization import init_database


@pytest.fixture
def db_path(tmp_path) -> Path:
    """Fournit un chemin de base SQLite temporaire, initialisé et isolé par test."""
    path = tmp_path / "test_app.db"
    init_database(db_path=path)
    return path


@pytest.fixture(autouse=True)
def licence_active_pour_les_tests(request, monkeypatch):
    """Les tests travaillent avec une licence valide, sauf ceux marqués « mode_demo »."""
    if "mode_demo" in request.keywords:
        return
    from services import licence_service

    monkeypatch.setattr(licence_service, "licence_active", lambda: True)
