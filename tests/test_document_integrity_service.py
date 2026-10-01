"""
Tests de services/document_integrity_service.py (module 14).
"""

import pytest

import database.connection as database_connection
from models.enums import StatutDocument, TypeDocument
from services import document_integrity_service, document_service


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _fichier_temp(tmp_path, nom="document.docx", contenu=b"contenu"):
    chemin = tmp_path / nom
    chemin.write_bytes(contenu)
    return chemin


# ---------------------------------------------------------------------
# Les 4 statuts
# ---------------------------------------------------------------------

def test_document_valide(tmp_path):
    fichier = _fichier_temp(tmp_path)
    doc = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    assert document_integrity_service.verifier_integrite(doc) == StatutDocument.VALIDE


def test_document_manquant(tmp_path):
    fichier = _fichier_temp(tmp_path)
    doc = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    fichier.unlink()
    assert document_integrity_service.verifier_integrite(doc) == StatutDocument.MANQUANT


def test_document_modifie(tmp_path):
    fichier = _fichier_temp(tmp_path, contenu=b"original")
    doc = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    fichier.write_bytes(b"modifie apres coup")
    assert document_integrity_service.verifier_integrite(doc) == StatutDocument.MODIFIE


def test_document_sans_hash_enregistre_reste_valide_si_present(tmp_path):
    """Un document sans hash mesuré à l'origine ne doit jamais être signalé MODIFIE par erreur."""
    from models.document import Document
    fichier = _fichier_temp(tmp_path)
    doc = Document(type_document=TypeDocument.BULLETIN, nom_fichier=fichier.name, chemin=str(fichier), hash_fichier=None)
    assert document_integrity_service.verifier_integrite(doc) == StatutDocument.VALIDE


def test_etat_leger_ne_recalcule_pas_le_hash(tmp_path):
    """etat_leger doit rester VALIDE tant que le fichier existe, sans jamais lire son contenu."""
    fichier = _fichier_temp(tmp_path, contenu=b"peu importe")
    doc = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    fichier.write_bytes(b"contenu totalement different")
    assert document_integrity_service.etat_leger(doc) == StatutDocument.VALIDE


def test_etat_leger_manquant(tmp_path):
    fichier = _fichier_temp(tmp_path)
    doc = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)
    fichier.unlink()
    assert document_integrity_service.etat_leger(doc) == StatutDocument.MANQUANT


# ---------------------------------------------------------------------
# Documents orphelins
# ---------------------------------------------------------------------

def test_detection_orphelin(tmp_path):
    dossier = tmp_path / "dossier_scanne"
    dossier.mkdir()
    fichier_enregistre = dossier / "enregistre.docx"
    fichier_enregistre.write_bytes(b"connu du registre")
    document_service.enregistrer_document(TypeDocument.BULLETIN, fichier_enregistre)

    fichier_orphelin = dossier / "orphelin.docx"
    fichier_orphelin.write_bytes(b"jamais enregistre")

    rapport = document_integrity_service.verifier_integrite_complete(dossiers_a_scanner=[dossier])
    assert len(rapport.documents_orphelins) == 1
    assert rapport.documents_orphelins[0].name == "orphelin.docx"


def test_aucun_orphelin_si_tout_enregistre(tmp_path):
    dossier = tmp_path / "dossier_scanne"
    dossier.mkdir()
    fichier = dossier / "connu.docx"
    fichier.write_bytes(b"connu")
    document_service.enregistrer_document(TypeDocument.BULLETIN, fichier)

    rapport = document_integrity_service.verifier_integrite_complete(dossiers_a_scanner=[dossier])
    assert rapport.documents_orphelins == []


def test_scan_dossier_absent_ne_plante_pas(tmp_path):
    rapport = document_integrity_service.verifier_integrite_complete(dossiers_a_scanner=[tmp_path / "absent"])
    assert rapport.documents_orphelins == []


# ---------------------------------------------------------------------
# Rapport complet
# ---------------------------------------------------------------------

def test_rapport_complet_compte_correctement(tmp_path):
    f1 = _fichier_temp(tmp_path, "valide.docx")
    document_service.enregistrer_document(TypeDocument.BULLETIN, f1)

    f2 = _fichier_temp(tmp_path, "manquant.docx")
    document_service.enregistrer_document(TypeDocument.BULLETIN, f2)
    f2.unlink()

    rapport = document_integrity_service.verifier_integrite_complete()
    assert rapport.nombre_documents == 2
    assert rapport.nombre_valides == 1
    assert rapport.nombre_manquants == 1


def test_rapport_vide_si_aucun_document():
    rapport = document_integrity_service.verifier_integrite_complete()
    assert rapport.nombre_documents == 0
    assert rapport.nombre_valides == 0
    assert rapport.nombre_manquants == 0
    assert rapport.documents_orphelins == []
