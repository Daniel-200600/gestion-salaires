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


@pytest.fixture(autouse=True)
def taux_de_taxe_historique(request, monkeypatch):
    """
    Tests marqués « taxe_historique » : taux par défaut de 5 %, celui du cas de
    référence officiel (100 h à 2 000 FCFA -> taxe 11 750, net 208 250), pour
    vérifier que chaque service restitue exactement les montants du moteur de
    calcul. Le taux de 5,5 % et la règle « vacataires uniquement » sont
    vérifiés dans tests/test_taxe_vacataires.py.
    """
    if "taxe_historique" not in request.keywords:
        return
    from decimal import Decimal

    from services import parametres_paie_service

    monkeypatch.setattr(parametres_paie_service, "TAUX_TAXE", Decimal("0.05"))
