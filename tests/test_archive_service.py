"""
Tests de services/archive_service.py (module 14).
"""

import json
import zipfile

import pytest

import database.connection as database_connection
from services import (
    archive_service,
    bulletin_service,
    controle_paie_service,
    donnees_paie_service,
    enseignant_service,
    periode_service,
)
from services.archive_service import ArchiveServiceError
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch, tmp_path):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    from services import bulletin_service as bs
    monkeypatch.setattr(bs, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")


def _periode_cloturee_avec_bulletin():
    e = enseignant_service.creer_enseignant(nom="Kamgang", prenom="Jean", sexe="M", statut="P", taux_horaire=2000)
    p = periode_service.creer_periode(mois=1, annee=2061)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
            retenue_amicale=5000, dette=10000),
    ])
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)
    bulletin_service.generer_bulletin_enseignant(p.id, e.id, utilisateur="admin")
    return periode_service.obtenir_periode(p.id)


# ---------------------------------------------------------------------
# Archivage
# ---------------------------------------------------------------------

def test_archivage_periode_cloturee_reussit(tmp_path):
    periode = _periode_cloturee_avec_bulletin()
    rapport = archive_service.archiver_periode(periode.id, utilisateur="admin", dossier_destination=tmp_path)
    assert rapport.chemin_archive.exists()
    assert rapport.nombre_documents == 1
    assert rapport.documents_manquants == []


def test_archivage_periode_non_cloturee_refuse(tmp_path):
    p = periode_service.creer_periode(mois=2, annee=2061)
    with pytest.raises(ArchiveServiceError, match="CLOTUREE"):
        archive_service.archiver_periode(p.id, dossier_destination=tmp_path)


def test_archivage_periode_ouverte_refuse(tmp_path):
    p = periode_service.creer_periode(mois=3, annee=2061)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    with pytest.raises(ArchiveServiceError):
        archive_service.archiver_periode(p.id, dossier_destination=tmp_path)


def test_archivage_periode_validee_seule_refuse(tmp_path):
    e = enseignant_service.creer_enseignant(nom="A", prenom="A", sexe="M", statut="P", taux_horaire=1000)
    p = periode_service.creer_periode(mois=4, annee=2061)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10})])
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    with pytest.raises(ArchiveServiceError):
        archive_service.archiver_periode(p.id, dossier_destination=tmp_path)


def test_archivage_ne_ecrase_jamais_une_archive_existante(tmp_path):
    periode = _periode_cloturee_avec_bulletin()
    rapport1 = archive_service.archiver_periode(periode.id, dossier_destination=tmp_path)
    rapport2 = archive_service.archiver_periode(periode.id, dossier_destination=tmp_path)
    assert rapport1.chemin_archive != rapport2.chemin_archive
    assert rapport1.chemin_archive.exists() and rapport2.chemin_archive.exists()


# ---------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------

def test_manifest_contient_les_informations_attendues(tmp_path):
    periode = _periode_cloturee_avec_bulletin()
    rapport = archive_service.archiver_periode(periode.id, etablissement="École Test", utilisateur="admin", dossier_destination=tmp_path)

    with zipfile.ZipFile(rapport.chemin_archive) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["etablissement"] == "École Test"
    assert manifest["periode"] == periode.libelle
    assert manifest["statut_periode"] == "cloturee"
    assert manifest["utilisateur"] == "admin"
    assert manifest["nombre_documents"] == 1
    assert len(manifest["documents"]) == 1
    assert "password" not in json.dumps(manifest).lower()
    assert "mot_de_passe" not in json.dumps(manifest).lower()


# ---------------------------------------------------------------------
# Vérification d'intégrité de l'archive
# ---------------------------------------------------------------------

def test_verification_archive_valide(tmp_path):
    periode = _periode_cloturee_avec_bulletin()
    rapport = archive_service.archiver_periode(periode.id, dossier_destination=tmp_path)
    resultat = archive_service.verifier_archive(rapport.chemin_archive)
    assert resultat.valide is True


def test_verification_archive_absente(tmp_path):
    resultat = archive_service.verifier_archive(tmp_path / "absente.zip")
    assert resultat.valide is False


def test_verification_archive_corrompue(tmp_path):
    fichier = tmp_path / "corrompu.zip"
    fichier.write_bytes(b"PAS UN ZIP VALIDE")
    resultat = archive_service.verifier_archive(fichier)
    assert resultat.valide is False


def test_verification_archive_sans_manifest(tmp_path):
    fichier = tmp_path / "sans_manifest.zip"
    with zipfile.ZipFile(fichier, "w") as z:
        z.writestr("Bulletins/test.docx", "contenu")
    resultat = archive_service.verifier_archive(fichier)
    assert resultat.valide is False
    assert "manifest" in resultat.message.lower()


def test_verification_detecte_hash_invalide(tmp_path):
    periode = _periode_cloturee_avec_bulletin()
    rapport = archive_service.archiver_periode(periode.id, dossier_destination=tmp_path)

    contenu_original = {}
    with zipfile.ZipFile(rapport.chemin_archive, "r") as archive:
        for nom in archive.namelist():
            contenu_original[nom] = archive.read(nom)

    chemin_nom = next(n for n in contenu_original if n.startswith("Bulletins/"))
    with zipfile.ZipFile(rapport.chemin_archive, "w") as archive:
        for nom, contenu in contenu_original.items():
            if nom == chemin_nom:
                archive.writestr(nom, b"CONTENU FALSIFIE")
            else:
                archive.writestr(nom, contenu)

    resultat = archive_service.verifier_archive(rapport.chemin_archive)
    assert resultat.valide is False
    assert len(resultat.fichiers_avec_hash_invalide) == 1


# ---------------------------------------------------------------------
# Extraction sécurisée (path traversal)
# ---------------------------------------------------------------------

def test_extraction_normale_reussit(tmp_path):
    zip_normal = tmp_path / "normal.zip"
    with zipfile.ZipFile(zip_normal, "w") as z:
        z.writestr("dossier/fichier.txt", "contenu")

    destination = tmp_path / "destination"
    extraits = archive_service.extraire_archive_securise(zip_normal, destination)
    assert len(extraits) == 1
    assert extraits[0].read_text() == "contenu"


def test_extraction_rejette_path_traversal(tmp_path):
    zip_malveillant = tmp_path / "malveillant.zip"
    with zipfile.ZipFile(zip_malveillant, "w") as z:
        z.writestr("../../../evil.txt", "malveillant")
        z.writestr("fichier_normal.txt", "normal")

    destination = tmp_path / "destination_securisee"
    extraits = archive_service.extraire_archive_securise(zip_malveillant, destination)

    assert len(extraits) == 1
    assert extraits[0].name == "fichier_normal.txt"
    for f in extraits:
        assert destination.resolve() in f.resolve().parents


def test_extraction_rejette_chemin_absolu(tmp_path):
    zip_malveillant = tmp_path / "absolu.zip"
    with zipfile.ZipFile(zip_malveillant, "w") as z:
        z.writestr("/etc/passwd_faux", "malveillant")

    destination = tmp_path / "destination2"
    extraits = archive_service.extraire_archive_securise(zip_malveillant, destination)
    for f in extraits:
        assert destination.resolve() in f.resolve().parents
