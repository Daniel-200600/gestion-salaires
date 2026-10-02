"""
Taux de taxe paramétrable.

- 5 % par défaut : aucun résultat existant ne change (cas de référence 208 250 FCFA) ;
- l'administrateur peut définir un autre taux (ex. 5,5 % :
  10 h × 1 800 FCFA -> taxe 990, net 17 010) ;
- chaque période porte son taux, figé à la validation (service ET trigger SQL) ;
- migration des bases existantes sans perte ;
- modification réservée à l'administrateur, vérifiée côté service ;
- chaque modification est journalisée.
"""

import sqlite3
from decimal import Decimal

import pytest

import database.connection as database_connection
from config.settings import SCHEMA_PATH, TAUX_TAXE
from database import migrations
from database.initialization import init_database
from models.enums import RoleUtilisateur, TypeActionAudit
from services import (
    administration_service,
    auth_service,
    donnees_paie_service,
    enseignant_service,
    paie_service,
    parametres_paie_service,
    periode_service,
    utilisateur_service,
)
from services.autorisation_service import AutorisationRefuseeError
from services.donnees_paie_service import DonneesPaieEnseignant
from services.parametres_paie_service import ParametrePaieError

MDP = "Motdepasse-Solide-1"


@pytest.fixture(autouse=True)
def _base(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})


def _periode_ouverte(mois=7, annee=2026):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


def _enseignant(taux_horaire=2000, **autres):
    donnees = {"nom": "Ngono", "prenom": "Marie", "sexe": "F", "statut": "V", "taux_horaire": taux_horaire}
    donnees.update(autres)
    return enseignant_service.creer_enseignant(**donnees)


def _saisir(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


def _cas_reference(periode):
    e = _enseignant(taux_horaire=2000)
    _saisir(periode.id, e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
            retenue_amicale=5000, dette=10000)
    return e


# ---------------------------------------------------------------------
# Valeur par défaut : rien ne change
# ---------------------------------------------------------------------

def test_taux_par_defaut_est_5_pourcent():
    assert TAUX_TAXE == Decimal("0.05")
    assert parametres_paie_service.obtenir_taux_taxe_defaut() == Decimal("0.05")
    assert _periode_ouverte().taux_taxe == Decimal("0.05")


def test_cas_de_reference_inchange_208250():
    periode = _periode_ouverte()
    e = _cas_reference(periode)
    resultat = paie_service.calculer_paie_enseignant(periode.id, e.id)
    assert (resultat.taxe_5, resultat.net_a_percevoir, resultat.taux_taxe) == (11750, 208250, Decimal("0.05"))


# ---------------------------------------------------------------------
# Taux de 5,5 % : calcul au franc près
# ---------------------------------------------------------------------

def test_bulletin_officiel_reproduit_avec_5_5_pourcent():
    parametres_paie_service.definir_taux_taxe_defaut("5,5")
    periode = _periode_ouverte()
    assert periode.taux_taxe == Decimal("0.055")
    e = _enseignant(taux_horaire=1800)
    _saisir(periode.id, e.id, heures_par_semaine={1: 10})
    resultat = paie_service.calculer_paie_enseignant(periode.id, e.id)
    assert resultat.gain_heures == 18000
    assert resultat.taxe_5 == 990
    assert resultat.net_a_percevoir == 17010


def test_changer_le_taux_par_defaut_ne_modifie_aucune_periode_existante():
    ancienne = _periode_ouverte(mois=6)
    parametres_paie_service.definir_taux_taxe_defaut(Decimal("5.5"))
    nouvelle = _periode_ouverte(mois=7)
    assert periode_service.obtenir_periode(ancienne.id).taux_taxe == Decimal("0.05")
    assert nouvelle.taux_taxe == Decimal("0.055")


# ---------------------------------------------------------------------
# Taux propre à une période, figé à la validation
# ---------------------------------------------------------------------

def test_taux_modifiable_en_brouillon_et_ouverte():
    periode = periode_service.creer_periode(mois=8, annee=2026)
    periode = parametres_paie_service.definir_taux_taxe_periode(periode.id, "6")
    assert periode.taux_taxe == Decimal("0.06")
    periode_service.ouvrir_periode(periode.id)
    periode = parametres_paie_service.definir_taux_taxe_periode(periode.id, "5.5")
    assert periode.taux_taxe == Decimal("0.055")


def test_taux_fige_apres_validation_et_resultats_stables():
    periode = _periode_ouverte()
    e = _cas_reference(periode)
    periode = periode_service.valider_periode(periode.id)
    avant = paie_service.calculer_paie_enseignant(periode.id, e.id)

    with pytest.raises(ParametrePaieError, match="figé"):
        parametres_paie_service.definir_taux_taxe_periode(periode.id, "5.5")
    parametres_paie_service.definir_taux_taxe_defaut("5.5")  # n'affecte pas la période validée

    apres = paie_service.calculer_paie_enseignant(periode.id, e.id)
    assert (apres.taxe_5, apres.net_a_percevoir) == (avant.taxe_5, avant.net_a_percevoir) == (11750, 208250)


def test_trigger_sql_bloque_la_modification_directe_du_taux_d_une_periode_validee(db_path):
    periode = _periode_ouverte()
    periode_service.valider_periode(periode.id)
    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="fige"):
            conn.execute("UPDATE periodes_paie SET taux_taxe = '0.055' WHERE id = ?", (periode.id,))
    finally:
        conn.close()


@pytest.mark.parametrize("saisie", ["-1", "55", "abc", "", "5,125"])
def test_saisies_invalides_refusees(saisie):
    with pytest.raises(ParametrePaieError):
        parametres_paie_service.pourcentage_vers_taux(saisie)


@pytest.mark.parametrize("saisie, taux, texte", [
    ("5", Decimal("0.05"), "5 %"), ("5,5", Decimal("0.055"), "5,5 %"), ("5.25", Decimal("0.0525"), "5,25 %"),
    ("0", Decimal("0"), "0 %"),
])
def test_conversion_et_affichage(saisie, taux, texte):
    assert parametres_paie_service.pourcentage_vers_taux(saisie) == taux
    assert parametres_paie_service.formater_taux(taux) == texte


def test_modifications_journalisees(db_path):
    parametres_paie_service.definir_taux_taxe_defaut("5.5", utilisateur="admin")
    periode = periode_service.creer_periode(mois=9, annee=2026)
    parametres_paie_service.definir_taux_taxe_periode(periode.id, "6", utilisateur="admin")
    conn = sqlite3.connect(db_path)
    lignes = conn.execute(
        "SELECT entite, utilisateur, details FROM audit_log WHERE type_action = ?",
        (TypeActionAudit.PARAMETRE_PAIE_MODIFIE.value,),
    ).fetchall()
    conn.close()
    assert ("parametres_paie", "admin", "Taux de taxe par défaut : 5 % -> 5,5 %") in lignes
    assert any(entite == "periode" and "5,5 % -> 6 %" in details for entite, _u, details in lignes)


# ---------------------------------------------------------------------
# Migration d'une base existante (sans colonne taux_taxe)
# ---------------------------------------------------------------------

def test_migration_base_existante_sans_colonne_taux(tmp_path):
    chemin = tmp_path / "ancienne.db"
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    ancien_schema = schema.replace(
        """    taux_taxe       TEXT    NOT NULL DEFAULT '0.05'
                        CHECK (CAST(taux_taxe AS REAL) >= 0 AND CAST(taux_taxe AS REAL) < 1),
""", "")
    debut = ancien_schema.index("-- Le taux de taxe d'une période validée")
    fin = ancien_schema.index("-- Seule une période encore en brouillon")
    ancien_schema = ancien_schema[:debut] + ancien_schema[fin:]
    assert "taux_taxe" not in ancien_schema
    conn = sqlite3.connect(chemin)
    conn.executescript(ancien_schema)
    conn.execute("INSERT INTO periodes_paie (mois, annee, libelle, statut) VALUES (5, 2026, 'Mai 2026', 'brouillon')")
    conn.commit()
    conn.close()

    init_database(db_path=chemin)
    init_database(db_path=chemin)  # idempotent

    conn = sqlite3.connect(chemin)
    colonnes = [ligne[1] for ligne in conn.execute("PRAGMA table_info(periodes_paie)")]
    valeur = conn.execute("SELECT taux_taxe FROM periodes_paie WHERE mois = 5").fetchone()[0]
    declencheurs = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    conn.close()
    assert colonnes.count("taux_taxe") == 1
    assert valeur == "0.05"
    assert "trg_periodes_paie_taux_fige" in declencheurs
    assert migrations.ajouter_colonnes_manquantes(sqlite3.connect(chemin)) == []


# ---------------------------------------------------------------------
# Réservé à l'administrateur, vérifié côté service
# ---------------------------------------------------------------------

@pytest.fixture
def comptes(db_path):
    return {
        role: utilisateur_service.creer_utilisateur("Nom", "Prenom", role.value, MDP, role, db_path=db_path)
        for role in RoleUtilisateur
    }


@pytest.mark.parametrize("role", [RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION])
def test_non_admin_refuse_meme_en_appel_direct(comptes, role, db_path):
    periode = periode_service.creer_periode(mois=10, annee=2026)
    with pytest.raises(AutorisationRefuseeError):
        administration_service.definir_taux_taxe_defaut(comptes[role].id, "5.5", db_path=db_path)
    with pytest.raises(AutorisationRefuseeError):
        administration_service.definir_taux_taxe_periode(comptes[role].id, periode.id, "5.5", db_path=db_path)
    assert parametres_paie_service.obtenir_taux_taxe_defaut(db_path=db_path) == Decimal("0.05")


def test_admin_autorise(comptes, db_path):
    administration_service.definir_taux_taxe_defaut(comptes[RoleUtilisateur.ADMIN].id, "5.5", db_path=db_path)
    assert parametres_paie_service.obtenir_taux_taxe_defaut(db_path=db_path) == Decimal("0.055")
