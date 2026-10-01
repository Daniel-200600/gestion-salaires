"""
Tests de database/migrations.py — correction du bug
`sqlite3.IntegrityError: CHECK constraint failed` sur `audit_log`
pour les bases créées avec une version antérieure du schéma.
"""

import sqlite3

import pytest

from database import migrations
from database.initialization import init_database
from models.enums import RoleUtilisateur, TypeActionAudit

def _schema_reel() -> str:
    from config.settings import SCHEMA_PATH
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _creer_ancienne_base(chemin) -> None:
    """
    Construit une base « ancienne » réaliste : le VRAI schéma actuel
    (toutes les tables identiques à la version courante), à
    l'exception du CHECK de `audit_log`, tronqué pour ne contenir que
    les valeurs les plus anciennes — reproduit fidèlement une base
    créée par une version antérieure de l'application, sans risquer
    la dérive d'un schéma simplifié à la main.
    """
    schema_tronque = _schema_reel().replace(
        """'calcul_paie',
                        'generation_bulletin',
                        'export_comptable',
                        'restauration_sauvegarde',
                        'suppression_definitive',
                        'connexion_reussie',
                        'connexion_echouee',
                        'deconnexion',
                        'utilisateur_cree',
                        'utilisateur_modifie',
                        'utilisateur_desactive',
                        'utilisateur_active',
                        'mot_de_passe_modifie',
                        'mot_de_passe_reinitialise',
                        'role_modifie',
                        'periode_ouverte',
                        'validation_refusee',
                        'cloture_refusee',
                        'reporting_exporte',
                        'rapprochement_execute',
                        'document_archive',
                        'document_integrite_verifiee',
                        'document_supprime',
                        'document_telecharge',
                        'archive_creee',
                        'archive_restauree',
                        'import_donnees',
                        'import_donnees_echec',
                        'import_donnees_simulation',
                        'alerte_creee',
                        'alerte_acquittee',
                        'alerte_resolue',
                        'alerte_ignoree',
                        'automatisation_preparee',
                        'automatisation_executee',
                        'automatisation_echec',
                        'generation_massive_bulletins',
                        'export_massif',
                        'archive_massive'
                    ))""",
        "'calcul_paie'\n                    ))",
    )
    # Vérifie que la troncature a bien eu lieu (sinon le test ne reproduirait rien de réel).
    assert "connexion_reussie" not in schema_tronque, "La troncature du schéma de test a échoué."

    conn = sqlite3.connect(chemin)
    conn.executescript(schema_tronque)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------
# Reproduction exacte du bug rapporté (section 6)
# ---------------------------------------------------------------------

def test_bug_reproduit_sur_ancienne_base_sans_migration(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)

    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        conn.execute("INSERT INTO audit_log (type_action) VALUES ('connexion_reussie')")
    conn.close()


def test_migration_corrige_le_bug(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)

    conn = sqlite3.connect(db_path)
    a_migre = migrations.migrer_audit_log_si_necessaire(conn, _schema_reel())
    assert a_migre is True

    conn.execute("INSERT INTO audit_log (type_action, utilisateur) VALUES ('connexion_reussie', 'admin')")
    conn.commit()
    conn.close()


def test_connexion_reelle_fonctionne_apres_migration_sur_ancienne_base(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)

    from services import utilisateur_service
    utilisateur_service.creer_utilisateur(
        nom="Admin", prenom="Test", username="admin_test", mot_de_passe="MotDePasse123!",
        confirmation_mot_de_passe="MotDePasse123!", role=RoleUtilisateur.ADMIN, actif=True, db_path=db_path,
    )

    init_database(db_path=db_path, schema_path=None)

    from services import auth_service
    resultat = auth_service.connecter("admin_test", "MotDePasse123!", db_path=db_path)
    assert resultat.reussie is True


# ---------------------------------------------------------------------
# Préservation des données existantes (section 4/17)
# ---------------------------------------------------------------------

def test_anciennes_entrees_audit_conservees(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO audit_log (type_action, details) VALUES ('creation', 'entree historique')")
    conn.commit()
    conn.close()

    conn2 = sqlite3.connect(db_path)
    migrations.migrer_audit_log_si_necessaire(conn2, _schema_reel())
    ligne = conn2.execute("SELECT * FROM audit_log WHERE details = 'entree historique'").fetchone()
    assert ligne is not None
    conn2.close()


def test_enseignants_et_periodes_preserves_apres_migration(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)

    from services import enseignant_service, periode_service
    e = enseignant_service.creer_enseignant(
        nom="Kamgang", prenom="Jean", sexe="M", statut="P", taux_horaire=2000, db_path=db_path
    )
    p = periode_service.creer_periode(mois=8, annee=2026, db_path=db_path)

    init_database(db_path=db_path)

    e_relu = enseignant_service.obtenir_enseignant(e.id, db_path=db_path)
    p_relu = periode_service.obtenir_periode(p.id, db_path=db_path)
    assert e_relu.nom == "Kamgang"
    assert p_relu.mois == 8


def test_integrite_sqlite_ok_apres_migration(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)
    conn = sqlite3.connect(db_path)
    migrations.migrer_audit_log_si_necessaire(conn, _schema_reel())
    resultat = conn.execute("PRAGMA integrity_check").fetchone()
    assert resultat[0] == "ok"
    conn.close()


def test_aucune_perte_de_ligne_lors_de_la_migration(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)
    conn = sqlite3.connect(db_path)
    for i in range(10):
        conn.execute("INSERT INTO audit_log (type_action, details) VALUES ('creation', ?)", (f"ligne_{i}",))
    conn.commit()

    migrations.migrer_audit_log_si_necessaire(conn, _schema_reel())
    total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert total == 10
    conn.close()


# ---------------------------------------------------------------------
# Idempotence (section 5)
# ---------------------------------------------------------------------

def test_migration_idempotente_deuxieme_appel_sans_effet(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)
    conn = sqlite3.connect(db_path)

    premiere = migrations.migrer_audit_log_si_necessaire(conn, _schema_reel())
    assert premiere is True

    deuxieme = migrations.migrer_audit_log_si_necessaire(conn, _schema_reel())
    assert deuxieme is False
    conn.close()


def test_init_database_deux_fois_de_suite_ne_casse_rien(tmp_path):
    db_path = tmp_path / "ancienne.db"
    _creer_ancienne_base(db_path)

    init_database(db_path=db_path)
    init_database(db_path=db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO audit_log (type_action) VALUES ('connexion_reussie')")
    conn.commit()
    integrite = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    assert integrite == "ok"


def test_base_neuve_jamais_migree():
    conn = sqlite3.connect(":memory:")
    resultat = migrations.migrer_audit_log_si_necessaire(conn, _schema_reel())
    assert resultat is False
    conn.close()


def test_base_deja_a_jour_ne_necessite_pas_migration(db_path):
    from database.connection import get_connection
    with get_connection(db_path) as conn:
        resultat = migrations.migrer_audit_log_si_necessaire(conn, _schema_reel())
    assert resultat is False


# ---------------------------------------------------------------------
# Cohérence exhaustive enum / schéma (section 3)
# ---------------------------------------------------------------------

def test_toutes_les_valeurs_enum_couvertes_par_le_schema_actuel():
    schema_sql = _schema_reel()
    valeurs_manquantes = [v.value for v in TypeActionAudit if f"'{v.value}'" not in schema_sql]
    assert valeurs_manquantes == [], f"Valeurs absentes du CHECK de schema.sql : {valeurs_manquantes}"


def test_aucune_valeur_schema_orpheline_de_lenum():
    import re
    schema_sql = _schema_reel()
    match = re.search(
        r"type_action\s+TEXT\s+NOT NULL\s+CHECK\s*\(type_action IN \((.*?)\)\)", schema_sql, re.DOTALL
    )
    valeurs_schema = set(re.findall(r"'([a-z_]+)'", match.group(1)))
    valeurs_enum = {v.value for v in TypeActionAudit}
    assert valeurs_schema == valeurs_enum
