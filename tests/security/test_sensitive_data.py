"""
Tests de sécurité — absence de données sensibles dans le code et les
journaux (module 19, section 24/39).
"""

import re
from pathlib import Path

import pytest

import database.connection as database_connection
from database.connection import get_connection
from models.enums import RoleUtilisateur
from services import auth_service, utilisateur_service

RACINE_PROJET = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})


# ---------------------------------------------------------------------
# Audit statique — aucun secret codé en dur (section 39)
# ---------------------------------------------------------------------

MOTIF_SECRET_SUSPECT = re.compile(
    r'(password|mot_de_passe|secret|api_key|token)\s*=\s*["\'][^"\'{}]{4,}["\']', re.IGNORECASE
)


def test_aucun_mot_de_passe_administrateur_par_defaut():
    """
    Aucun identifiant admin par défaut ne doit exister : le premier
    compte est toujours créé manuellement via le formulaire
    d'initialisation (utils/session_auth._afficher_formulaire_initialisation_admin).
    """
    contenu_session_auth = (RACINE_PROJET / "utils" / "session_auth.py").read_text(encoding="utf-8")
    assert "admin123" not in contenu_session_auth.lower()
    assert '"admin", "admin"' not in contenu_session_auth.lower()


def test_aucun_secret_evident_code_en_dur_dans_services():
    """Recherche de motifs `password="valeur"` codés en dur dans la couche services (hors tests)."""
    dossier_services = RACINE_PROJET / "services"
    trouvailles = []
    for fichier in dossier_services.glob("*.py"):
        contenu = fichier.read_text(encoding="utf-8")
        for ligne_num, ligne in enumerate(contenu.splitlines(), start=1):
            if MOTIF_SECRET_SUSPECT.search(ligne) and "def " not in ligne and "param" not in ligne.lower():
                trouvailles.append(f"{fichier.name}:{ligne_num}")
    assert trouvailles == [], f"Motif de secret codé en dur suspect trouvé : {trouvailles}"


# ---------------------------------------------------------------------
# Logs / audit — jamais de mot de passe (section 5/24)
# ---------------------------------------------------------------------

def test_audit_log_jamais_de_colonne_mot_de_passe(db_path):
    """La table audit_log ne doit avoir aucune colonne pouvant stocker un mot de passe en clair."""
    with get_connection(db_path) as conn:
        colonnes = [r["name"] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
    for colonne in colonnes:
        assert "password" not in colonne.lower()
        assert "mot_de_passe" not in colonne.lower()


def test_table_utilisateurs_ne_stocke_jamais_le_mot_de_passe_en_clair(db_path):
    """Seule une colonne de hash doit exister — jamais une colonne 'password' ou 'mot_de_passe' en clair."""
    with get_connection(db_path) as conn:
        colonnes = [r["name"] for r in conn.execute("PRAGMA table_info(utilisateurs)").fetchall()]
    assert "password" not in colonnes
    assert "mot_de_passe" not in colonnes
    assert any("hash" in c.lower() for c in colonnes)


def test_mot_de_passe_stocke_est_bien_un_hash_jamais_en_clair(db_path):
    utilisateur_service.creer_utilisateur(
        nom="Test", prenom="User", username="secure_test", mot_de_passe="MotDePasseUltraSecret99!",
        confirmation_mot_de_passe="MotDePasseUltraSecret99!", role=RoleUtilisateur.CONSULTATION, actif=True,
        db_path=db_path,
    )
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT password_hash FROM utilisateurs WHERE username = ?", ("secure_test",)).fetchone()
    assert "MotDePasseUltraSecret99!" not in row["password_hash"]
    assert row["password_hash"].startswith("scrypt$")
