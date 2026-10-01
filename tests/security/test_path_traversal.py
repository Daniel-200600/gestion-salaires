"""
Tests de sécurité — path traversal et ZIP slip (module 19, section 13/14).

Consolide et complète les protections déjà testées individuellement
dans les modules 14 (archive_service), 15 (import_service) et 18
(automatisation_service) — vérifie qu'aucune régression n'a été
introduite et couvre quelques charges supplémentaires.
"""

import zipfile

import pytest

from utils.formatters import nettoyer_nom_fichier

CHARGES_PATH_TRAVERSAL = [
    "../../test.txt",
    "../../../database.db",
    "..\\..\\test.txt",
    "../../../../etc/passwd",
    "/etc/passwd",
    "C:\\Windows\\System32\\config",
]


# ---------------------------------------------------------------------
# Nettoyage de nom de fichier (section 33)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("charge", CHARGES_PATH_TRAVERSAL)
def test_nettoyage_nom_fichier_neutralise_les_separateurs(charge):
    """Aucun séparateur de chemin (/ ou \\) ne doit survivre au nettoyage — condition nécessaire à l'absence de path traversal."""
    resultat = nettoyer_nom_fichier(charge)
    assert "/" not in resultat
    assert "\\" not in resultat


def test_nettoyage_nom_fichier_noms_enseignants_realistes():
    """Section 33 : noms réels variés, aucun ne doit produire un chemin invalide ou dangereux."""
    noms = ["Jean", "Jean-Paul", "O'Connor", "François", "A/B", "Nom  avec   espaces", "X" * 300]
    for nom in noms:
        resultat = nettoyer_nom_fichier(nom)
        assert "/" not in resultat
        assert "\\" not in resultat
        assert resultat != ""


# ---------------------------------------------------------------------
# ZIP Slip — extraction sécurisée (module 14, réutilisée par 18)
# ---------------------------------------------------------------------

def test_zip_slip_chemin_relatif_rejete(tmp_path):
    from services import archive_service

    zip_malveillant = tmp_path / "malveillant.zip"
    with zipfile.ZipFile(zip_malveillant, "w") as z:
        z.writestr("../../../evil.txt", "contenu malveillant")
        z.writestr("fichier_legitime.txt", "contenu normal")

    destination = tmp_path / "destination"
    extraits = archive_service_module().extraire_archive_securise(zip_malveillant, destination)

    assert len(extraits) == 1
    assert extraits[0].name == "fichier_legitime.txt"
    for f in extraits:
        assert destination.resolve() in f.resolve().parents


def archive_service_module():
    from services import archive_service
    return archive_service


def test_zip_slip_chemin_absolu_rejete(tmp_path):
    archive_service = archive_service_module()

    zip_malveillant = tmp_path / "absolu.zip"
    with zipfile.ZipFile(zip_malveillant, "w") as z:
        z.writestr("/etc/evil_absolu.txt", "malveillant")

    destination = tmp_path / "destination2"
    extraits = archive_service.extraire_archive_securise(zip_malveillant, destination)
    for f in extraits:
        assert destination.resolve() in f.resolve().parents


def test_zip_slip_windows_style_rejete(tmp_path):
    """Un chemin de type Windows (C:\\...) intégré à un nom d'entrée ZIP ne doit jamais sortir du dossier de destination."""
    archive_service = archive_service_module()

    zip_malveillant = tmp_path / "windows.zip"
    with zipfile.ZipFile(zip_malveillant, "w") as z:
        z.writestr("..\\..\\evil_windows.txt", "malveillant")

    destination = tmp_path / "destination3"
    extraits = archive_service.extraire_archive_securise(zip_malveillant, destination)
    for f in extraits:
        assert destination.resolve() in f.resolve().parents


def test_archive_vide_ne_plante_pas(tmp_path):
    archive_service = archive_service_module()

    zip_vide = tmp_path / "vide.zip"
    with zipfile.ZipFile(zip_vide, "w"):
        pass

    destination = tmp_path / "destination4"
    extraits = archive_service.extraire_archive_securise(zip_vide, destination)
    assert extraits == []


def test_verification_archive_corrompue_ne_plante_pas(tmp_path):
    archive_service = archive_service_module()

    fichier_corrompu = tmp_path / "corrompu.zip"
    fichier_corrompu.write_bytes(b"CECI N'EST PAS UN ZIP" * 5)
    resultat = archive_service.verifier_archive(fichier_corrompu)
    assert resultat.valide is False


# ---------------------------------------------------------------------
# Import de fichiers — chemin jamais construit depuis le nom fourni par l'utilisateur (module 15)
# ---------------------------------------------------------------------

def test_import_fichier_nom_dangereux_ne_construit_pas_de_chemin_arbitraire(tmp_path):
    """
    Le nom affiché (`nom_fichier`) peut contenir des séquences de
    path traversal sans risque, car il n'est jamais utilisé pour
    construire un chemin sur disque — seul `chemin` (contrôlé par
    l'application) l'est. Vérifié directement sur l'API du service.
    """
    from services import import_service

    fichier = tmp_path / "reel.csv"
    fichier.write_text("Nom,Prenom\nA,B\n", encoding="utf-8")

    contenu = import_service.lire_fichier(fichier, nom_fichier="../../../etc/passwd.csv")
    assert contenu.nom_fichier == "../../../etc/passwd.csv"  # conservé pour affichage uniquement
    assert contenu.feuilles  # lecture réussie du VRAI fichier contrôlé, jamais un chemin dérivé du nom affiché
