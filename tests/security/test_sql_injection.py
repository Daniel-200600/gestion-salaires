"""
Tests de sécurité — injection SQL (module 19, section 11/12).

Toutes les requêtes du projet utilisent des paramètres liés (`?`),
jamais de concaténation ou de f-string avec une valeur utilisateur —
vérifié par audit statique (grep) en amont de ce fichier. Ces tests
vérifient dynamiquement qu'aucune charge utile d'injection ne
provoque de comportement anormal (erreur non contrôlée, contournement
de filtre, corruption de données) à travers les points d'entrée réels
de l'application.
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from services import enseignant_service, periode_service
from services.periode_service import PeriodeValidationError

CHARGES_INJECTION = [
    "'; DROP TABLE enseignants; --",
    "' OR '1'='1",
    "' OR 1=1 --",
    "Robert'); DROP TABLE enseignants;--",
    "admin'--",
    "' UNION SELECT * FROM utilisateurs --",
    '"; DELETE FROM enseignants WHERE 1=1; --',
]


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


@pytest.mark.parametrize("charge", CHARGES_INJECTION)
def test_injection_dans_nom_enseignant_sans_danger(charge, db_path):
    """Le nom est stocké tel quel (texte littéral) — jamais interprété comme SQL."""
    enseignant = enseignant_service.creer_enseignant(
        nom=charge, prenom="Test", sexe="M", statut="P", taux_horaire=1000
    )
    assert enseignant.nom == charge  # stocké fidèlement, pas exécuté

    with get_connection(db_path) as conn:
        table_existe = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='enseignants'"
        ).fetchone()
    assert table_existe is not None  # la table n'a jamais été supprimée


@pytest.mark.parametrize("charge", CHARGES_INJECTION)
def test_injection_dans_recherche_enseignant_sans_danger(charge):
    """La recherche texte ne doit jamais planter ni contourner le paramétrage avec une charge d'injection."""
    from database.repositories import enseignant_repository
    resultats = enseignant_repository.rechercher(charge)
    assert isinstance(resultats, list)  # ne lève jamais, retourne simplement une liste (vide ou non)


def test_table_utilisateurs_toujours_presente_apres_tentatives(db_path):
    """Vérification finale : après toutes les tentatives d'injection ci-dessus, le schéma reste intact."""
    for charge in CHARGES_INJECTION:
        enseignant_service.creer_enseignant(nom=charge, prenom="X", sexe="M", statut="P", taux_horaire=1000)

    with get_connection(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for table_attendue in ("enseignants", "utilisateurs", "periodes_paie", "audit_log"):
        assert table_attendue in tables


def test_injection_dans_creation_periode_rejetee_par_validation():
    """Le champ mois, typé entier, rejette toute charge textuelle via la validation métier — jamais exécutée comme SQL."""
    for charge in CHARGES_INJECTION:
        with pytest.raises(PeriodeValidationError):
            periode_service.creer_periode(mois=charge, annee=2026)


# ---------------------------------------------------------------------
# Audit statique — aucune requête ne construit du SQL par f-string/concat avec une valeur utilisateur
# ---------------------------------------------------------------------

def test_audit_statique_aucune_concatenation_sql_dangereuse():
    """
    Recherche, dans tous les repositories, toute construction de
    requête par f-string interpolant directement une variable. Les
    seules interpolations autorisées sont des noms de colonnes fixes
    provenant d'un dictionnaire interne contrôlé par le code
    (ex. alerte_repository.changer_statut), jamais une valeur saisie
    par l'utilisateur.
    """
    import re
    from pathlib import Path

    dossier_repositories = Path(__file__).resolve().parent.parent.parent / "database" / "repositories"
    motif_f_string_sql = re.compile(r'f["\'].*?(SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE)

    fichiers_suspects = []
    for fichier in dossier_repositories.glob("*.py"):
        contenu = fichier.read_text(encoding="utf-8")
        if motif_f_string_sql.search(contenu):
            fichiers_suspects.append(fichier.name)

    # alerte_repository.py utilise un f-string SQL mais UNIQUEMENT avec des
    # noms de colonnes fixes tirés d'un dict interne (jamais une entrée
    # utilisateur) — revu manuellement et documenté dans security_audit.md.
    fichiers_suspects_non_revus = [f for f in fichiers_suspects if f != "alerte_repository.py"]
    assert fichiers_suspects_non_revus == [], (
        f"Requête(s) SQL construite(s) par f-string non revue(s) trouvée(s) dans : {fichiers_suspects_non_revus}"
    )
