"""
Tests de services/document_service.py et
database/repositories/document_repository.py (module 14).
"""

import pytest

import database.connection as database_connection
from models.enums import TypeDocument
from services import document_service, enseignant_service, periode_service


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Kamgang", "prenom": "Test", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode(mois=1, annee=2060):
    return periode_service.creer_periode(mois=mois, annee=annee)


def _fichier_temp(tmp_path, nom="document.docx", contenu=b"contenu de test"):
    chemin = tmp_path / nom
    chemin.write_bytes(contenu)
    return chemin


# ---------------------------------------------------------------------
# Création / lecture du registre
# ---------------------------------------------------------------------

def test_creation_document(tmp_path):
    p = _creer_periode()
    fichier = _fichier_temp(tmp_path)
    doc = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier, periode_id=p.id, utilisateur="admin")
    assert doc is not None
    assert doc.id is not None
    assert doc.nom_fichier == "document.docx"
    assert doc.taille == len(b"contenu de test")


def test_lecture_document_par_id(tmp_path):
    p = _creer_periode()
    fichier = _fichier_temp(tmp_path)
    doc = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier, periode_id=p.id)
    relu = document_service.obtenir_document(doc.id)
    assert relu.nom_fichier == doc.nom_fichier


def test_document_inexistant_retourne_none():
    assert document_service.obtenir_document(999999) is None


# ---------------------------------------------------------------------
# Recherche / filtrage
# ---------------------------------------------------------------------

def test_recherche_par_periode(tmp_path):
    p1 = _creer_periode(mois=1)
    p2 = _creer_periode(mois=2)
    document_service.enregistrer_document(TypeDocument.BULLETIN, _fichier_temp(tmp_path, "a.docx"), periode_id=p1.id)
    document_service.enregistrer_document(TypeDocument.BULLETIN, _fichier_temp(tmp_path, "b.docx"), periode_id=p2.id)

    resultats = document_service.rechercher_documents(periode_id=p1.id)
    assert len(resultats) == 1
    assert resultats[0].nom_fichier == "a.docx"


def test_recherche_par_enseignant(tmp_path):
    e1 = _creer_enseignant(nom="A", prenom="A")
    e2 = _creer_enseignant(nom="B", prenom="B")
    document_service.enregistrer_document(TypeDocument.BULLETIN, _fichier_temp(tmp_path, "a.docx"), enseignant_id=e1.id)
    document_service.enregistrer_document(TypeDocument.BULLETIN, _fichier_temp(tmp_path, "b.docx"), enseignant_id=e2.id)

    resultats = document_service.rechercher_documents(enseignant_id=e1.id)
    assert len(resultats) == 1
    assert resultats[0].enseignant_id == e1.id


def test_recherche_par_type(tmp_path):
    document_service.enregistrer_document(TypeDocument.BULLETIN, _fichier_temp(tmp_path, "a.docx"))
    document_service.enregistrer_document(TypeDocument.EXPORT_EXCEL, _fichier_temp(tmp_path, "b.xlsx"))

    resultats = document_service.rechercher_documents(type_document=TypeDocument.EXPORT_EXCEL)
    assert len(resultats) == 1
    assert resultats[0].nom_fichier == "b.xlsx"


def test_recherche_par_terme_insensible_a_la_casse(tmp_path):
    document_service.enregistrer_document(TypeDocument.BULLETIN, _fichier_temp(tmp_path, "Bulletin_KAMGANG_Aout.docx"))

    resultats = document_service.rechercher_documents(terme_recherche="kamgang")
    assert len(resultats) == 1


def test_recherche_combinee(tmp_path):
    p = _creer_periode()
    e = _creer_enseignant()
    document_service.enregistrer_document(
        TypeDocument.BULLETIN, _fichier_temp(tmp_path, "match.docx"), periode_id=p.id, enseignant_id=e.id
    )
    document_service.enregistrer_document(TypeDocument.BULLETIN, _fichier_temp(tmp_path, "autre.docx"), periode_id=p.id)

    resultats = document_service.rechercher_documents(periode_id=p.id, enseignant_id=e.id)
    assert len(resultats) == 1
    assert resultats[0].nom_fichier == "match.docx"


def test_recherche_sans_resultat():
    assert document_service.rechercher_documents(terme_recherche="inexistant_xyz") == []


# ---------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------

def test_hash_correct_pour_fichier_inchange(tmp_path):
    fichier = _fichier_temp(tmp_path)
    h1 = document_service.calculer_hash_fichier(fichier)
    h2 = document_service.calculer_hash_fichier(fichier)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hexdigest


def test_hash_differe_si_fichier_modifie(tmp_path):
    fichier = _fichier_temp(tmp_path, contenu=b"version 1")
    h1 = document_service.calculer_hash_fichier(fichier)
    fichier.write_bytes(b"version 2")
    h2 = document_service.calculer_hash_fichier(fichier)
    assert h1 != h2


def test_hash_none_pour_document_manquant(tmp_path):
    assert document_service.calculer_hash_fichier(tmp_path / "absent.docx") is None


# ---------------------------------------------------------------------
# Enregistrement best-effort
# ---------------------------------------------------------------------

def test_enregistrement_avec_periode_inexistante_ne_leve_pas(tmp_path):
    fichier = _fichier_temp(tmp_path)
    resultat = document_service.enregistrer_document(TypeDocument.BULLETIN, fichier, periode_id=999999)
    assert resultat is None  # échoue proprement (FK), mais ne lève jamais


def test_enregistrement_sans_periode_ni_enseignant(tmp_path):
    fichier = _fichier_temp(tmp_path)
    doc = document_service.enregistrer_document(TypeDocument.EXPORT_EXCEL, fichier)
    assert doc is not None
    assert doc.periode_id is None
    assert doc.enseignant_id is None
