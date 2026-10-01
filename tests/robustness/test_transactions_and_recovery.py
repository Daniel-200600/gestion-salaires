"""
Tests de robustesse — transactions, intégrité base, reprise après
incident (module 19, section 17/18/23).
"""

import sqlite3

import pytest

import database.connection as database_connection
from database.connection import get_connection
from services import backup_service, controle_paie_service, donnees_paie_service, enseignant_service, periode_service
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


# ---------------------------------------------------------------------
# Transactions — import massif (consolidation module 15, aucune régression)
# ---------------------------------------------------------------------

def test_rollback_import_aucune_donnee_partielle(tmp_path):
    from unittest.mock import patch
    from database.repositories import enseignant_repository
    from services import import_service
    from models.enums import TypeImport
    import pandas as pd

    df = pd.DataFrame({
        "Nom": ["Alpha", "Beta", "Gamma"], "Prenom": ["A", "B", "C"],
        "Sexe": ["M", "M", "M"], "Statut": ["P", "P", "P"], "taux_horaire": [1000, 1000, 1000],
    })
    fichier = tmp_path / "test.xlsx"
    df.to_excel(fichier, index=False)
    contenu = import_service.lire_fichier(fichier, "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])

    original = enseignant_repository.creer
    compteur = {"n": 0}

    def echec_a_la_deuxieme(*args, **kwargs):
        compteur["n"] += 1
        if compteur["n"] == 2:
            raise RuntimeError("Panne simulée")
        return original(*args, **kwargs)

    with patch.object(enseignant_repository, "creer", side_effect=echec_a_la_deuxieme):
        journal = import_service.executer_import_enseignants(rapport, "test.xlsx")

    assert journal.statut.value == "echec"
    assert enseignant_service.lister_enseignants(inclure_inactifs=True) == []


# ---------------------------------------------------------------------
# Intégrité de la base (section 17)
# ---------------------------------------------------------------------

def test_pragma_integrity_check_base_saine(db_path):
    with get_connection(db_path) as conn:
        resultat = conn.execute("PRAGMA integrity_check").fetchone()
    assert resultat[0] == "ok"


def test_diagnostic_detecte_base_inexistante(tmp_path):
    from services import diagnostic_service
    chemin_inexistant = tmp_path / "absente.db"
    diagnostic = diagnostic_service.diagnostiquer_systeme(db_path=chemin_inexistant)
    assert diagnostic.base_accessible is False


def test_diagnostic_ne_plante_jamais_sur_base_partiellement_corrompue(tmp_path):
    """Une base SQLite valide mais sans les tables applicatives ne doit jamais faire planter le diagnostic."""
    from services import diagnostic_service
    chemin_base_vide = tmp_path / "vide_sans_tables.db"
    conn = sqlite3.connect(chemin_base_vide)
    conn.execute("CREATE TABLE autre_chose (id INTEGER)")
    conn.commit()
    conn.close()

    diagnostic = diagnostic_service.diagnostiquer_systeme(db_path=chemin_base_vide)
    assert diagnostic is not None


# ---------------------------------------------------------------------
# Sauvegarde / restauration — reprise après incident (section 23)
# ---------------------------------------------------------------------

def test_restauration_fichier_inexistant_refusee_proprement(tmp_path):
    resultat = backup_service.restaurer_sauvegarde(
        tmp_path / "n_existe_pas.db", confirmation=True, db_path=tmp_path / "cible.db", backup_dir=tmp_path,
    )
    assert resultat.reussie is False


def test_restauration_fichier_non_sqlite_refusee(tmp_path, db_path):
    faux_fichier = tmp_path / "pas_une_db.db"
    faux_fichier.write_bytes(b"CECI N'EST PAS UNE BASE SQLITE" * 10)

    resultat = backup_service.restaurer_sauvegarde(
        faux_fichier, confirmation=True, db_path=db_path, backup_dir=tmp_path,
    )
    assert resultat.reussie is False

    with get_connection(db_path) as conn:
        integrite = conn.execute("PRAGMA integrity_check").fetchone()
    assert integrite[0] == "ok"


def test_restauration_sans_confirmation_refusee(db_path, tmp_path):
    from services.backup_service import BackupServiceError
    sauvegarde = backup_service.creer_sauvegarde(db_path=db_path, backup_dir=tmp_path)
    with pytest.raises(BackupServiceError):
        backup_service.restaurer_sauvegarde(sauvegarde, confirmation=False, db_path=db_path, backup_dir=tmp_path)


def test_base_reste_recuperable_apres_restauration_refusee(db_path, tmp_path):
    """Après un échec de restauration (fichier invalide), la base active doit rester pleinement fonctionnelle."""
    enseignant_service.creer_enseignant(
        nom="Avant", prenom="Incident", sexe="M", statut="P", taux_horaire=1000, db_path=db_path
    )

    faux_fichier = tmp_path / "invalide.db"
    faux_fichier.write_bytes(b"invalide")
    backup_service.restaurer_sauvegarde(faux_fichier, confirmation=True, db_path=db_path, backup_dir=tmp_path)

    tous = enseignant_service.lister_enseignants(inclure_inactifs=True, db_path=db_path)
    assert any(ens.nom == "Avant" for ens in tous)


# ---------------------------------------------------------------------
# Idempotence des automatisations (consolidation module 18, section 29)
# ---------------------------------------------------------------------

def test_generation_bulletins_repetee_trois_fois_toujours_idempotente(tmp_path, monkeypatch):
    from services import automatisation_service, bulletin_service, document_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")

    e = enseignant_service.creer_enseignant(nom="Idem", prenom="Potent", sexe="M", statut="P", taux_horaire=2000)
    p = periode_service.creer_periode(mois=6, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10})]
    )

    for _ in range(3):
        automatisation_service.generer_bulletins_massif(p.id)

    documents = document_service.rechercher_documents(periode_id=p.id)
    assert len(documents) == 1


# ---------------------------------------------------------------------
# Concurrence (section 28) — comportement documenté, pas de nouvelle
# architecture de verrouillage introduite tardivement
# ---------------------------------------------------------------------

def test_deux_connexions_simultanees_en_ecriture_comportement_sqlite(db_path):
    """
    Documente le comportement réel (jamais modifié ici) : SQLite
    n'autorise qu'UN SEUL écrivain à la fois. Une seconde connexion
    tentant d'écrire pendant qu'une transaction est ouverte sur la
    première reçoit soit une erreur immédiate (« database is locked »),
    soit une brève attente selon le busy_timeout du driver — jamais de
    corruption silencieuse ni d'écriture perdue sans erreur.
    """
    import sqlite3

    conn1 = sqlite3.connect(db_path)
    conn1.execute("BEGIN IMMEDIATE")
    conn1.execute("INSERT INTO enseignants (nom, prenom, sexe, statut, taux_horaire, actif) VALUES (?, ?, ?, ?, ?, 1)", ("Conn1", "X", "M", "P", 1000))

    conn2 = sqlite3.connect(db_path, timeout=0.5)
    with pytest.raises(sqlite3.OperationalError):
        conn2.execute("INSERT INTO enseignants (nom, prenom, sexe, statut, taux_horaire, actif) VALUES (?, ?, ?, ?, ?, 1)", ("Conn2", "X", "M", "P", 1000))

    conn1.commit()
    conn1.close()
    conn2.close()

    # Après libération du verrou, la base reste cohérente et utilisable.
    conn3 = sqlite3.connect(db_path)
    total = conn3.execute("SELECT COUNT(*) FROM enseignants").fetchone()[0]
    conn3.close()
    assert total == 1  # seule l'écriture de conn1 a abouti, jamais de duplication ni de corruption
