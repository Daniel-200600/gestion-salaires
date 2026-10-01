"""
Tests de services/alert_detection_service.py (module 16).
"""

import pytest

import database.connection as database_connection
from models.enums import NiveauAlerte, StatutAlerte, StatutPeriode
from services import (
    alert_detection_service,
    alert_service,
    controle_paie_service,
    donnees_paie_service,
    enseignant_service,
    periode_service,
)
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch, tmp_path):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    from services import bulletin_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")


def _creer_enseignant(**overrides):
    donnees = {"nom": "Kamgang", "prenom": "Jean", "sexe": "M", "statut": "P", "taux_horaire": 2000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


# ---------------------------------------------------------------------
# Alertes enseignants
# ---------------------------------------------------------------------

def test_detection_taux_horaire_nul():
    _creer_enseignant(taux_horaire=0)
    rapport = alert_detection_service.detecter_alertes_enseignants()
    assert rapport.nombre_creees_ou_maj == 1
    alertes = alert_service.lister_alertes(type_alerte="TAUX_HORAIRE_NUL")
    assert len(alertes) == 1
    assert alertes[0].niveau == NiveauAlerte.AVERTISSEMENT


def test_pas_d_alerte_si_taux_horaire_normal():
    _creer_enseignant(taux_horaire=2000)
    rapport = alert_detection_service.detecter_alertes_enseignants()
    assert rapport.nombre_creees_ou_maj == 0


def test_detection_re_execution_ne_duplique_pas():
    _creer_enseignant(taux_horaire=0)
    alert_detection_service.detecter_alertes_enseignants()
    alert_detection_service.detecter_alertes_enseignants()
    assert len(alert_service.lister_alertes(type_alerte="TAUX_HORAIRE_NUL")) == 1


# ---------------------------------------------------------------------
# Alertes périodes — jamais une erreur pour un état normal
# ---------------------------------------------------------------------

def test_periode_brouillon_genere_une_info_pas_une_erreur():
    periode_service.creer_periode(mois=1, annee=2091)
    rapport = alert_detection_service.detecter_alertes_periodes()
    assert rapport.nombre_creees_ou_maj == 1
    alerte = alert_service.lister_alertes(type_alerte="PERIODE_BROUILLON")[0]
    assert alerte.niveau == NiveauAlerte.INFO


def test_periode_ouverte_ne_genere_pas_alerte_brouillon():
    p = periode_service.creer_periode(mois=2, annee=2091)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    rapport = alert_detection_service.detecter_alertes_periodes()
    assert rapport.nombre_creees_ou_maj == 0


# ---------------------------------------------------------------------
# Intégration module 09 — contrôle de paie
# ---------------------------------------------------------------------

def test_integration_controle_paie_periode_vide():
    p = periode_service.creer_periode(mois=3, annee=2091)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    rapport = alert_detection_service.detecter_alertes_controle_paie(p.id)
    assert rapport.nombre_creees_ou_maj >= 1
    alertes = alert_service.lister_alertes(periode_id=p.id, source="controle_paie")
    assert any("PERIODE_VIDE" in a.type_alerte for a in alertes)


def test_integration_controle_paie_aucune_anomalie_periode_saine():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=4, annee=2091)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10}, prime_ap_pp=500)]
    )
    rapport = alert_detection_service.detecter_alertes_controle_paie(p.id)
    assert rapport.nombre_creees_ou_maj == 0


def test_controle_paie_resolution_automatique_apres_correction():
    p = periode_service.creer_periode(mois=5, annee=2091)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    alert_detection_service.detecter_alertes_controle_paie(p.id)
    assert alert_service.lister_alertes(periode_id=p.id, source="controle_paie", statut=StatutAlerte.NOUVELLE)

    e = _creer_enseignant()
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10})]
    )
    alert_detection_service.detecter_alertes_controle_paie(p.id)
    alertes_periode_vide = [a for a in alert_service.lister_alertes(periode_id=p.id) if "PERIODE_VIDE" in a.type_alerte]
    assert all(a.statut == StatutAlerte.RESOLUE for a in alertes_periode_vide)


def test_alertes_respectent_le_verrouillage_periode_cloturee():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=6, annee=2091)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
            retenue_amicale=5000, dette=10000),
    ])
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)

    alert_detection_service.detecter_alertes_controle_paie(p.id)
    periode_relue = periode_service.obtenir_periode(p.id)
    assert periode_relue.statut == StatutPeriode.CLOTUREE


# ---------------------------------------------------------------------
# Intégration module 14 — documents
# ---------------------------------------------------------------------

def test_integration_documents_manquant(tmp_path):
    from services import document_service
    from models.enums import TypeDocument

    fichier = tmp_path / "bulletin.docx"
    fichier.write_bytes(b"contenu")
    document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    fichier.unlink()

    rapport = alert_detection_service.detecter_alertes_documents()
    assert rapport.nombre_creees_ou_maj == 1
    alertes = alert_service.lister_alertes(type_alerte="DOCUMENT_MANQUANT")
    assert len(alertes) == 1
    assert alertes[0].niveau == NiveauAlerte.ERREUR


def test_integration_documents_modifie(tmp_path):
    from services import document_service
    from models.enums import TypeDocument

    fichier = tmp_path / "bulletin.docx"
    fichier.write_bytes(b"contenu original")
    document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    fichier.write_bytes(b"contenu modifie apres coup")

    alert_detection_service.detecter_alertes_documents()
    alertes = alert_service.lister_alertes(type_alerte="DOCUMENT_MODIFIE")
    assert len(alertes) == 1


def test_integration_documents_orphelin(tmp_path):
    fichier_orphelin = tmp_path / "orphelin.docx"
    fichier_orphelin.write_bytes(b"jamais enregistre")

    alert_detection_service.detecter_alertes_documents(dossiers_a_scanner=[tmp_path])
    alertes = alert_service.lister_alertes(type_alerte="DOCUMENT_ORPHELIN")
    assert len(alertes) == 1
    assert alertes[0].niveau == NiveauAlerte.INFO


def test_document_resolu_automatiquement_une_fois_regenere(tmp_path):
    from services import document_service
    from models.enums import TypeDocument

    fichier = tmp_path / "bulletin.docx"
    fichier.write_bytes(b"contenu")
    document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    fichier.unlink()
    alert_detection_service.detecter_alertes_documents()
    assert alert_service.lister_alertes(type_alerte="DOCUMENT_MANQUANT")[0].statut == StatutAlerte.NOUVELLE

    fichier.write_bytes(b"contenu regenere")
    alert_detection_service.detecter_alertes_documents()
    assert alert_service.lister_alertes(type_alerte="DOCUMENT_MANQUANT")[0].statut == StatutAlerte.RESOLUE


# ---------------------------------------------------------------------
# Intégration module 10 — administration
# ---------------------------------------------------------------------

def test_integration_administration_aucune_sauvegarde(tmp_path, monkeypatch):
    from services import backup_service
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path / "backups_vide")

    rapport = alert_detection_service.detecter_alertes_administratives()
    assert rapport.nombre_creees_ou_maj >= 1
    assert alert_service.lister_alertes(type_alerte="AUCUNE_SAUVEGARDE")


def test_integration_administration_avec_sauvegarde_recente(tmp_path, monkeypatch, db_path):
    from services import backup_service
    dossier_backup = tmp_path / "backups"
    monkeypatch.setattr(backup_service, "BACKUP_DIR", dossier_backup)
    backup_service.creer_sauvegarde(db_path=db_path, backup_dir=dossier_backup)

    alert_detection_service.detecter_alertes_administratives()
    assert alert_service.lister_alertes(type_alerte="AUCUNE_SAUVEGARDE") == []
    assert alert_service.lister_alertes(type_alerte="SAUVEGARDE_ANCIENNE") == []


# ---------------------------------------------------------------------
# Intégration module 15 — import (alerte de synthèse, jamais par ligne)
# ---------------------------------------------------------------------

def test_alerte_import_creee_si_erreurs(db_path):
    from database.repositories import import_repository
    from models.import_journal import ImportJournal
    from models.enums import TypeImport, StatutImport

    journal = ImportJournal(
        nom_fichier="test.xlsx", type_import=TypeImport.ENSEIGNANTS, statut=StatutImport.TERMINE,
        nb_lignes=10, nb_creations=8, nb_erreurs=2, utilisateur="admin",
    )
    journal.id = import_repository.enregistrer_import(journal, db_path=db_path)

    alerte = alert_detection_service.detecter_alerte_import(journal, db_path=db_path)
    assert alerte is not None
    assert alerte.niveau == NiveauAlerte.AVERTISSEMENT


def test_aucune_alerte_import_si_pleinement_reussi():
    from models.import_journal import ImportJournal
    from models.enums import TypeImport, StatutImport

    journal = ImportJournal(
        nom_fichier="test.xlsx", type_import=TypeImport.ENSEIGNANTS, statut=StatutImport.TERMINE,
        nb_lignes=10, nb_creations=10, nb_erreurs=0, nb_rejetees=0, utilisateur="admin",
    )
    # Import pleinement réussi : la fonction retourne None AVANT toute écriture,
    # aucun besoin d'un import_id réel puisqu'aucune alerte n'est créée.
    alerte = alert_detection_service.detecter_alerte_import(journal)
    assert alerte is None


def test_alerte_import_echec_niveau_erreur(db_path):
    from database.repositories import import_repository
    from models.import_journal import ImportJournal
    from models.enums import TypeImport, StatutImport

    journal = ImportJournal(
        nom_fichier="test.xlsx", type_import=TypeImport.ENSEIGNANTS, statut=StatutImport.ECHEC,
        nb_lignes=10, utilisateur="admin",
    )
    journal.id = import_repository.enregistrer_import(journal, db_path=db_path)

    alerte = alert_detection_service.detecter_alerte_import(journal, db_path=db_path)
    assert alerte.niveau == NiveauAlerte.ERREUR


# ---------------------------------------------------------------------
# Orchestration complète
# ---------------------------------------------------------------------

def test_executer_toutes_detections():
    _creer_enseignant(taux_horaire=0)
    p = periode_service.creer_periode(mois=7, annee=2091)
    resultats = alert_detection_service.executer_toutes_detections(periode_id=p.id)
    assert "enseignants" in resultats
    assert "periodes" in resultats
    assert "controle_paie" in resultats
    assert resultats["enseignants"].nombre_creees_ou_maj == 1


# ---------------------------------------------------------------------
# Performance (section 42) — volume significatif, pas de doublons
# ---------------------------------------------------------------------

def test_performance_volume_important_sans_duplication():
    for i in range(60):
        _creer_enseignant(nom=f"Enseignant{i}", prenom="X", taux_horaire=0)

    rapport1 = alert_detection_service.detecter_alertes_enseignants()
    assert rapport1.nombre_creees_ou_maj == 60

    rapport2 = alert_detection_service.detecter_alertes_enseignants()
    assert rapport2.nombre_creees_ou_maj == 60
    assert len(alert_service.lister_alertes(type_alerte="TAUX_HORAIRE_NUL")) == 60
