"""
Tests des nouveaux événements d'audit du module 14 (documents/archive).
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from database.repositories import audit_log_repository
from models.audit_log import AuditLog
from models.enums import TypeActionAudit


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


@pytest.mark.parametrize("type_action", [
    TypeActionAudit.DOCUMENT_ARCHIVE,
    TypeActionAudit.DOCUMENT_INTEGRITE_VERIFIEE,
    TypeActionAudit.DOCUMENT_SUPPRIME,
    TypeActionAudit.DOCUMENT_TELECHARGE,
    TypeActionAudit.ARCHIVE_CREEE,
    TypeActionAudit.ARCHIVE_RESTAUREE,
    TypeActionAudit.GENERATION_BULLETIN,
    TypeActionAudit.EXPORT_COMPTABLE,
])
def test_audit_type_accepte(db_path, type_action):
    entree = AuditLog(type_action=type_action, entite="test", entite_id=1, utilisateur="admin", details="test")
    audit_log_repository.enregistrer(entree)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = ?", (type_action.value,)
        ).fetchall()
    assert len(lignes) == 1
