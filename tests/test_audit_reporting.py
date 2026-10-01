"""
Tests des nouveaux événements d'audit du module 13
(REPORTING_EXPORTE, RAPPROCHEMENT_EXECUTE).
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from database.repositories import audit_log_repository
from models.audit_log import AuditLog
from models.enums import TypeActionAudit
from services import periode_service


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def test_audit_reporting_exporte_accepte(db_path):
    p = periode_service.creer_periode(mois=1, annee=2052)
    entree = AuditLog(
        type_action=TypeActionAudit.REPORTING_EXPORTE,
        entite="periode_paie", entite_id=p.id, utilisateur="admin",
        details=f"{p.libelle} — Etat_Paie_Janvier_2052.xlsx",
    )
    audit_log_repository.enregistrer(entree)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'reporting_exporte' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert len(lignes) == 1
    assert lignes[0]["utilisateur"] == "admin"


def test_audit_rapprochement_execute_accepte(db_path):
    p = periode_service.creer_periode(mois=2, annee=2052)
    entree = AuditLog(
        type_action=TypeActionAudit.RAPPROCHEMENT_EXECUTE,
        entite="periode_paie", entite_id=p.id, utilisateur="gestionnaire",
        details=f"{p.libelle} — OK",
    )
    audit_log_repository.enregistrer(entree)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'rapprochement_execute' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert len(lignes) == 1
    assert "OK" in lignes[0]["details"]
