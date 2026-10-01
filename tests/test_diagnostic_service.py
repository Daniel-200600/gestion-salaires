"""
Tests de services/diagnostic_service.py (module 10).
"""

import pytest

from database.initialization import init_database
from services import diagnostic_service, enseignant_service, periode_service
from services.diagnostic_service import EtatSysteme


@pytest.fixture
def environnement_complet(tmp_path, monkeypatch):
    """Base + dossiers de données entièrement isolés dans tmp_path, avec un template présent."""
    db_path = tmp_path / "app.db"
    init_database(db_path=db_path)

    exports_dir = tmp_path / "exports"
    bulletins_dir = exports_dir / "bulletins"
    backups_dir = tmp_path / "backups"
    exports_dir.mkdir()
    bulletins_dir.mkdir()
    backups_dir.mkdir()

    monkeypatch.setattr(diagnostic_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(diagnostic_service, "BACKUP_DIR", backups_dir)
    monkeypatch.setattr(diagnostic_service, "EXPORT_DIR", exports_dir)
    monkeypatch.setattr(diagnostic_service, "EXPORT_DIR_BULLETINS", bulletins_dir)

    from services import backup_service
    monkeypatch.setattr(backup_service, "BACKUP_DIR", backups_dir)

    # Le vrai template officiel existe déjà dans le projet.
    return db_path


# ---------------------------------------------------------------------
# Base valide / inaccessible
# ---------------------------------------------------------------------

def test_diagnostic_base_valide(environnement_complet):
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.base_accessible is True
    assert diag.integrite.valide is True


def test_diagnostic_base_inaccessible(tmp_path):
    diag = diagnostic_service.diagnostiquer_systeme(db_path=tmp_path / "absente.db")
    assert diag.base_accessible is False
    assert diag.etat_global == EtatSysteme.ROUGE


def test_diagnostic_base_corrompue(tmp_path):
    fichier_corrompu = tmp_path / "corrompu.db"
    fichier_corrompu.write_bytes(b"PAS UNE BASE SQLITE")
    diag = diagnostic_service.diagnostiquer_systeme(db_path=fichier_corrompu)
    assert diag.base_accessible is False
    assert diag.etat_global == EtatSysteme.ROUGE


# ---------------------------------------------------------------------
# Vérification des tables (dérivées du schéma réel)
# ---------------------------------------------------------------------

def test_diagnostic_toutes_tables_presentes(environnement_complet):
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.toutes_tables_presentes is True
    noms_tables = {t.nom for t in diag.tables}
    assert "enseignants" in noms_tables
    assert "periodes_paie" in noms_tables
    assert "audit_log" in noms_tables


def test_diagnostic_table_manquante_detectee(environnement_complet):
    import sqlite3
    conn = sqlite3.connect(environnement_complet)
    conn.execute("DROP TABLE retenues")
    conn.commit()
    conn.close()

    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    table_retenues = next(t for t in diag.tables if t.nom == "retenues")
    assert table_retenues.presente is False
    assert diag.toutes_tables_presentes is False
    assert diag.etat_global == EtatSysteme.ROUGE


# ---------------------------------------------------------------------
# Dénombrements
# ---------------------------------------------------------------------

def test_diagnostic_denombrements_corrects(environnement_complet):
    enseignant_service.creer_enseignant(
        nom="A", prenom="A", sexe="M", statut="P", taux_horaire=1000, db_path=environnement_complet
    )
    enseignant_service.creer_enseignant(
        nom="B", prenom="B", sexe="F", statut="V", taux_horaire=1000, db_path=environnement_complet
    )
    periode_service.creer_periode(mois=1, annee=2031, db_path=environnement_complet)

    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.nombre_enseignants == 2
    assert diag.nombre_periodes == 1
    assert diag.nombre_lignes_audit == 0
    assert diag.nombre_bulletins == 0


# ---------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------

def test_diagnostic_template_present(environnement_complet):
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.template_bulletin_present is True


def test_diagnostic_template_manquant_detecte(environnement_complet, monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic_service, "TEMPLATE_PATH", tmp_path / "absent.docx")
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.template_bulletin_present is False
    assert diag.etat_global == EtatSysteme.ROUGE


# ---------------------------------------------------------------------
# Dossiers essentiels
# ---------------------------------------------------------------------

def test_diagnostic_dossier_manquant_detecte(environnement_complet, monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic_service, "EXPORT_DIR", tmp_path / "exports_absent")
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.dossiers_essentiels_ok is False
    assert "exports" in diag.dossiers_manquants


# ---------------------------------------------------------------------
# État global
# ---------------------------------------------------------------------

def test_diagnostic_etat_vert_si_tout_ok_et_sauvegarde_presente(environnement_complet):
    from services import backup_service
    backup_service.creer_sauvegarde(db_path=environnement_complet)

    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.etat_global == EtatSysteme.VERT


def test_diagnostic_etat_orange_si_aucune_sauvegarde(environnement_complet):
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.nombre_sauvegardes == 0
    assert diag.etat_global == EtatSysteme.ORANGE


def test_formater_taille():
    assert diagnostic_service.formater_taille(500) == "500.0 o"
    assert "Ko" in diagnostic_service.formater_taille(2048)
    assert "Mo" in diagnostic_service.formater_taille(5_000_000)


# ---------------------------------------------------------------------
# Système d'authentification (module 11, section 37)
# ---------------------------------------------------------------------

def test_diagnostic_denombrements_utilisateurs(environnement_complet):
    from models.enums import RoleUtilisateur
    from services import utilisateur_service

    admin = utilisateur_service.creer_utilisateur(
        nom="A", prenom="A", username="admin1", mot_de_passe="MotDePasse123",
        role=RoleUtilisateur.ADMIN, db_path=environnement_complet,
    )
    inactif = utilisateur_service.creer_utilisateur(
        nom="B", prenom="B", username="user2", mot_de_passe="MotDePasse456",
        role=RoleUtilisateur.CONSULTATION, db_path=environnement_complet,
    )
    utilisateur_service.desactiver_utilisateur(inactif.id, db_path=environnement_complet)

    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.nombre_utilisateurs == 2
    assert diag.nombre_utilisateurs_actifs == 1
    assert diag.nombre_admins_actifs == 1


def test_diagnostic_ne_contient_jamais_de_mot_de_passe(environnement_complet):
    from models.enums import RoleUtilisateur
    from services import utilisateur_service
    import dataclasses

    utilisateur_service.creer_utilisateur(
        nom="A", prenom="A", username="admin1", mot_de_passe="MotDePasseSecret123",
        role=RoleUtilisateur.ADMIN, db_path=environnement_complet,
    )
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    texte_diagnostic = str(dataclasses.asdict(diag) if dataclasses.is_dataclass(diag) else diag)
    assert "MotDePasseSecret123" not in texte_diagnostic
    assert "scrypt$" not in texte_diagnostic


# ---------------------------------------------------------------------
# Registre documentaire (module 14, section 15)
# ---------------------------------------------------------------------

def test_diagnostic_compte_les_documents(environnement_complet, tmp_path):
    from models.enums import TypeDocument
    from services import document_service

    fichier = tmp_path / "doc.docx"
    fichier.write_bytes(b"contenu")
    document_service.enregistrer_document(TypeDocument.BULLETIN, fichier, db_path=environnement_complet)

    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.nombre_documents == 1
    assert diag.documents_manquants == 0


def test_diagnostic_detecte_document_manquant(environnement_complet, tmp_path):
    from models.enums import TypeDocument
    from services import document_service

    fichier = tmp_path / "doc.docx"
    fichier.write_bytes(b"contenu")
    document_service.enregistrer_document(TypeDocument.BULLETIN, fichier, db_path=environnement_complet)
    fichier.unlink()

    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.documents_manquants == 1


def test_diagnostic_zero_document_si_registre_vide(environnement_complet):
    diag = diagnostic_service.diagnostiquer_systeme(db_path=environnement_complet)
    assert diag.nombre_documents == 0
    assert diag.documents_manquants == 0
