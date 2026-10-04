"""
En-tête, logo et signature du bulletin réglés depuis l'interface
(services/identite_etablissement_service.py).
"""

import io
import sqlite3

import pytest
from docx import Document

import database.connection as database_connection
from config import settings
from models.enums import RoleUtilisateur
from services import administration_service, identite_etablissement_service as service, modele_bulletin_service
from services import auth_service, utilisateur_service
from services.autorisation_service import AutorisationRefuseeError
from services.identite_etablissement_service import IdentiteEtablissementError
from templates import build_template

ENTETE_FR = ["REPUBLIQUE DU CAMEROUN", "Paix – Travail – Patrie", "REGION DU LITTORAL", "COLLEGE BILINGUE EXEMPLE"]
ENTETE_EN = ["REPUBLIC OF CAMEROON", "Peace – Work – Fatherland", "LITTORAL REGION", "EXAMPLE BILINGUAL COLLEGE"]


@pytest.fixture(autouse=True)
def _environnement(db_path, monkeypatch, tmp_path):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    monkeypatch.setattr(settings, "MODELES_ETABLISSEMENT_DIR", tmp_path / "modeles_etablissement")
    monkeypatch.setattr(build_template, "trouver_libreoffice", lambda: None)  # rapide : Word seulement


def _logo(couleur=(31, 58, 110)) -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (60, 40), couleur).save(tampon, format="PNG")
    return tampon.getvalue()


def _enregistrer(**autres):
    valeurs = dict(entete_fr=ENTETE_FR, entete_en=ENTETE_EN, lieu_signature="Douala",
                   titre_signataire_fr="Le Principal/", titre_signataire_en="The Principal")
    valeurs.update(autres)
    return service.enregistrer_identite(**valeurs)


def _texte_et_images(chemin):
    document = Document(chemin)
    return document.element.xml, len(document.inline_shapes)


def test_sans_reglage_l_en_tete_neutre_est_utilise():
    assert service.obtenir_identite() is None
    assert service.identite_ou_neutre() == build_template.IDENTITE_NEUTRE


def test_identite_enregistree_relue_et_modele_word_produit():
    rapport = _enregistrer(logo=_logo())
    identite = service.obtenir_identite()
    assert list(identite.entete_fr) == ENTETE_FR and list(identite.entete_en) == ENTETE_EN
    assert identite.lieu_signature == "Douala" and identite.logo == _logo()
    xml, images = _texte_et_images(rapport.modele_word)
    assert "COLLEGE BILINGUE EXEMPLE" in xml and "EXAMPLE BILINGUAL COLLEGE" in xml
    assert "Fait à Douala le:" in xml and "Le Principal/The Principal" in xml
    assert images == 1


def test_le_modele_de_l_etablissement_est_utilise_immediatement():
    rapport = _enregistrer()
    assert modele_bulletin_service.modele_standard_word().chemin == rapport.modele_word
    texte = modele_bulletin_service.apercu_modele(modele_bulletin_service.modele_standard_word())
    assert b"PK" == texte[:2]  # un bulletin d'essai complet est produit


def test_le_logo_est_conserve_remplace_ou_retire():
    _enregistrer(logo=_logo())
    _enregistrer(lieu_signature="Bafoussam")
    assert service.obtenir_identite().logo == _logo()
    _enregistrer(logo=_logo((200, 0, 0)))
    assert service.obtenir_identite().logo == _logo((200, 0, 0))
    rapport = _enregistrer(retirer_logo=True)
    assert service.obtenir_identite().logo is None
    assert _texte_et_images(rapport.modele_word)[1] == 0


@pytest.mark.parametrize("modification, message", [
    ({"entete_fr": ["", "  "]}, "au moins une ligne"),
    ({"entete_en": [f"LIGNE {i}" for i in range(9)]}, "8 lignes"),
    ({"entete_fr": ["X" * 91]}, "trop longue"),
    ({"lieu_signature": " "}, "lieu de signature"),
    ({"logo": b"GIF89a pas une image acceptee"}, "PNG ou JPEG"),
    ({"logo": b"\x89PNG\r\n\x1a\n" + b"0" * 50}, "endommagé"),
    ({"logo": b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)}, "2 Mo"),
])
def test_valeurs_refusees(modification, message):
    with pytest.raises(IdentiteEtablissementError, match=message):
        _enregistrer(**modification)
    assert service.obtenir_identite() is None


def test_sans_libreoffice_le_modele_pdf_reste_neutre(tmp_path):
    dossier = settings.MODELES_ETABLISSEMENT_DIR
    dossier.mkdir(parents=True)
    (dossier / build_template.CHEMIN_MODELE_PDF.name).write_bytes(b"%PDF ancien")
    (dossier / build_template.CHEMIN_ZONES_PDF.name).write_text("[]", encoding="utf-8")

    rapport = _enregistrer()

    assert rapport.modele_pdf is None and "LibreOffice" in rapport.avertissement_pdf
    assert not (dossier / build_template.CHEMIN_MODELE_PDF.name).exists()
    assert modele_bulletin_service.modele_standard_pdf().chemin.parent.name == "templates"


def test_modeles_reconstruits_s_ils_manquent():
    rapport = _enregistrer()
    rapport.modele_word.unlink()
    assert service.assurer_modeles_etablissement() is not None
    assert rapport.modele_word.exists()
    assert service.assurer_modeles_etablissement() is None  # déjà présents : rien à faire


def test_aucune_reconstruction_sans_identite():
    assert service.assurer_modeles_etablissement() is None
    assert not settings.MODELES_ETABLISSEMENT_DIR.exists()


def test_retour_a_l_en_tete_neutre():
    rapport = _enregistrer(logo=_logo())
    service.revenir_a_l_entete_neutre()
    assert service.obtenir_identite() is None and not rapport.modele_word.exists()
    assert modele_bulletin_service.modele_standard_word().chemin.parent.name == "templates"


def test_chaque_modification_est_journalisee(db_path):
    _enregistrer(utilisateur="admin.paie")
    service.revenir_a_l_entete_neutre(utilisateur="admin.paie")
    with sqlite3.connect(db_path) as conn:
        lignes = conn.execute(
            "SELECT utilisateur, details FROM audit_log WHERE entite = 'identite_etablissement' ORDER BY id"
        ).fetchall()
    assert [u for u, _ in lignes] == ["admin.paie", "admin.paie"]
    assert "COLLEGE BILINGUE EXEMPLE" in lignes[0][1] and "neutre" in lignes[1][1]


def test_reglage_reserve_a_l_administrateur(monkeypatch):
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})
    admin = utilisateur_service.creer_utilisateur("A", "Admin", "admin.id", "Motdepasse-Solide-1", RoleUtilisateur.ADMIN)
    gestion = utilisateur_service.creer_utilisateur(
        "G", "Gestion", "gestion.id", "Motdepasse-Solide-1", RoleUtilisateur.GESTIONNAIRE_PAIE
    )
    arguments = (ENTETE_FR, ENTETE_EN, "Douala", "Le Principal/", "The Principal")
    with pytest.raises(AutorisationRefuseeError):
        administration_service.definir_identite_etablissement(gestion.id, *arguments)
    with pytest.raises(AutorisationRefuseeError):
        administration_service.revenir_a_l_entete_neutre(None)
    assert service.obtenir_identite() is None
    administration_service.definir_identite_etablissement(admin.id, *arguments)
    assert service.obtenir_identite().lieu_signature == "Douala"


def test_modele_pdf_de_l_etablissement_avec_libreoffice(monkeypatch):
    monkeypatch.undo()  # vrai LibreOffice, s'il est installé
    executable = build_template.trouver_libreoffice()
    if executable is None:
        pytest.skip("LibreOffice absent : modèle PDF non testable")
    import tempfile
    from pathlib import Path

    import pymupdf

    from database.initialization import init_database

    base = Path(tempfile.mkdtemp()) / "app.db"
    init_database(db_path=base)
    monkeypatch.setattr(database_connection, "DB_PATH", base)
    monkeypatch.setattr(settings, "MODELES_ETABLISSEMENT_DIR", base.parent / "modeles_etablissement")

    rapport = _enregistrer(logo=_logo())

    assert rapport.avertissement_pdf is None and rapport.modele_pdf.exists()
    texte = " ".join(page.get_text() for page in pymupdf.open(rapport.modele_pdf))
    assert "COLLEGE BILINGUE EXEMPLE" in texte and "Douala" in texte
    assert modele_bulletin_service.modele_standard_pdf().chemin == rapport.modele_pdf
    modele_bulletin_service.apercu_modele(modele_bulletin_service.modele_standard_pdf())


def test_mise_en_page_anterieure_refaite_au_demarrage():
    _enregistrer()
    dossier = settings.MODELES_ETABLISSEMENT_DIR
    marqueur = dossier / build_template.NOM_FICHIER_VERSION
    assert marqueur.read_text(encoding="utf-8") == build_template.VERSION_MISE_EN_PAGE
    assert service.assurer_modeles_etablissement() is None  # déjà à jour : rien n'est refait

    # Poste mis à jour : modèles de la mise en page précédente, PDF produit autrefois avec LibreOffice.
    marqueur.write_text("1", encoding="utf-8")
    ancien_pdf = dossier / build_template.CHEMIN_MODELE_PDF.name
    ancien_pdf.write_bytes(b"%PDF ancien modele de l'etablissement")
    rapport = service.assurer_modeles_etablissement()
    assert rapport is not None and marqueur.read_text(encoding="utf-8") == build_template.VERSION_MISE_EN_PAGE
    # Sans LibreOffice, le PDF de l'établissement est conservé (il garde son en-tête).
    assert ancien_pdf.read_bytes() == b"%PDF ancien modele de l'etablissement"
