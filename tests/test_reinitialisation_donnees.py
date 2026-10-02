"""
Tests de la réinitialisation complète des données métier
(services/reinitialisation_service.py).

RÉINITIALISER LES DONNÉES ≠ RÉINITIALISER LES COMPTES : chaque test
vérifie, en plus de son objet propre, que les comptes utilisateurs ne
sont jamais altérés. Toutes les opérations portent sur une base et des
dossiers temporaires propres à chaque test.
"""

import sqlite3
import zipfile

import pytest

import database.connection as database_connection
from database.initialization import init_database
from database.repositories import audit_log_repository, import_repository
from models.enums import (
    NiveauAlerte,
    NiveauAnomalie,
    RoleUtilisateur,
    StatutImport,
    TypeActionAudit,
    TypeDocument,
    TypeImport,
)
from models.import_journal import AnomalieImport, ImportJournal
from services import (
    alert_service,
    auth_service,
    bulletin_service,
    document_service,
    donnees_paie_service,
    enseignant_service,
    periode_service,
    permission_service,
    reinitialisation_service,
    utilisateur_service,
)
from services.autorisation_service import AutorisationRefuseeError
from services.donnees_paie_service import DonneesPaieEnseignant
from services.reinitialisation_service import (
    CATEGORIES_SUPPRIMEES,
    ConfirmationInvalideError,
    ReinitialisationError,
    TABLES_CONSERVEES,
)

MDP_ADMIN = "Admin-Paie-2026!"
MDP_GESTION = "Gestion-Paie-2026!"
MDP_LECTURE = "Lecture-Paie-2026!"


# ---------------------------------------------------------------------
# Environnement isolé
# ---------------------------------------------------------------------

@pytest.fixture
def env(db_path, tmp_path, monkeypatch):
    """Base, dossier des fichiers générés et dossier de sauvegardes temporaires."""
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    dossier_exports = tmp_path / "exports"
    dossier_bulletins = dossier_exports / "bulletins"
    dossier_bulletins.mkdir(parents=True)
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", dossier_bulletins)
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})
    return {
        "db": db_path,
        "exports": dossier_exports,
        "backups": tmp_path / "backups",
    }


def _creer_comptes(db):
    admin = utilisateur_service.creer_utilisateur(
        "Kamga", "Paul", "admin.paie", MDP_ADMIN, RoleUtilisateur.ADMIN, db_path=db
    )
    gestion = utilisateur_service.creer_utilisateur(
        "Ngono", "Marie", "gestion.paie", MDP_GESTION, RoleUtilisateur.GESTIONNAIRE_PAIE, db_path=db
    )
    lecture = utilisateur_service.creer_utilisateur(
        "Fotso", "Luc", "lecture.paie", MDP_LECTURE, RoleUtilisateur.CONSULTATION, db_path=db
    )
    return admin, gestion, lecture


def _peupler_donnees_metier(env):
    """Enseignants, période, données de paie, bulletins, documents, import et alertes."""
    db = env["db"]
    e1 = enseignant_service.creer_enseignant(
        nom="Mbarga", prenom="Alice", sexe="F", statut="P", taux_horaire=2000, db_path=db
    )
    e2 = enseignant_service.creer_enseignant(
        nom="Essomba", prenom="Jean", sexe="M", statut="V", taux_horaire=1500, db_path=db
    )
    periode = periode_service.creer_periode(mois=9, annee=2030, db_path=db)
    periode_service.ouvrir_periode(periode.id, db_path=db)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode.id,
        [
            DonneesPaieEnseignant(
                enseignant_id=e1.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
                prime_ap_pp=5000, retenue_amicale=1000,
            ),
            DonneesPaieEnseignant(
                enseignant_id=e2.id, heures_par_semaine={1: 10}, surveillance_secretariat=3000, dette=500,
            ),
        ],
        db_path=db,
    )
    periode_service.valider_periode(periode.id, db_path=db)
    bulletin_service.generer_bulletins_groupe(periode.id, [e1.id, e2.id], db_path=db, utilisateur="admin.paie")

    export_excel = env["exports"] / "Etat_Paie_Septembre_2030.xlsx"
    export_excel.write_bytes(b"contenu de test")
    document_service.enregistrer_document(
        TypeDocument.EXPORT_EXCEL, export_excel, periode_id=periode.id, db_path=db
    )
    archives = env["exports"] / "archives"
    archives.mkdir()
    (archives / "PAIE_Septembre_2030.zip").write_bytes(b"archive de test")

    journal_id = import_repository.enregistrer_import(
        ImportJournal(nom_fichier="enseignants.xlsx", type_import=TypeImport.ENSEIGNANTS,
                      statut=StatutImport.TERMINE, utilisateur="gestion.paie", nb_lignes=2),
        db_path=db,
    )
    import_repository.enregistrer_anomalies(
        journal_id,
        [AnomalieImport(ligne=3, niveau=NiveauAnomalie.AVERTISSEMENT, message="Ligne ignorée")],
        db_path=db,
    )
    alert_service.creer_ou_mettre_a_jour_alerte(
        "test_anomalie", NiveauAlerte.AVERTISSEMENT, "Anomalie de test", "Détail", "test",
        periode_id=periode.id, enseignant_id=e1.id, db_path=db,
    )
    alert_service.creer_ou_mettre_a_jour_alerte(
        "test_import", NiveauAlerte.INFO, "Import de test", "Détail", "test", import_id=journal_id, db_path=db,
    )
    return {"enseignants": [e1, e2], "periode": periode}


def _compter(db, table):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _lignes_comptes(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT * FROM utilisateurs ORDER BY id").fetchall()
    finally:
        conn.close()


def _noms_declencheurs(db):
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    finally:
        conn.close()


def _reinitialiser(env, utilisateur_id, phrase="RÉINITIALISER", confirmation=True):
    return reinitialisation_service.reinitialiser_donnees_metier(
        utilisateur_id, phrase, confirmation=confirmation,
        db_path=env["db"], dossier_exports=env["exports"], backup_dir=env["backups"],
    )


# ---------------------------------------------------------------------
# Scénario critique complet (section 27)
# ---------------------------------------------------------------------

def test_scenario_critique_reinitialisation_complete(env):
    db = env["db"]
    admin, gestion, lecture = _creer_comptes(db)
    assert auth_service.connecter("admin.paie", MDP_ADMIN, db_path=db).reussie
    _peupler_donnees_metier(env)

    # Vérification préalable : toutes les catégories contiennent des données.
    for categorie in CATEGORIES_SUPPRIMEES:
        assert _compter(db, categorie.table) > 0, f"{categorie.table} devrait contenir des données"
    assert any(env["exports"].rglob("*.docx"))
    comptes_avant = _lignes_comptes(db)
    declencheurs_avant = _noms_declencheurs(db)
    permissions_avant = {role: permission_service.permissions_du_role(role) for role in RoleUtilisateur}

    rapport = _reinitialiser(env, admin.id)

    assert rapport.reussie, rapport.message
    # Toutes les données métier ont disparu.
    for categorie in CATEGORIES_SUPPRIMEES:
        assert _compter(db, categorie.table) == 0, f"{categorie.table} n'a pas été vidée"
    assert not [p for p in env["exports"].rglob("*") if p.is_file()]
    assert (env["exports"] / "bulletins").is_dir()
    # Comptes strictement identiques (identifiants, hash, rôles, statut, dates).
    assert _lignes_comptes(db) == comptes_avant
    # Les mots de passe fonctionnent toujours.
    assert auth_service.connecter("admin.paie", MDP_ADMIN, db_path=db).reussie
    assert auth_service.connecter("gestion.paie", MDP_GESTION, db_path=db).reussie
    assert auth_service.connecter("lecture.paie", MDP_LECTURE, db_path=db).reussie
    # Rôles inchangés.
    roles = {u.username: u.role for u in utilisateur_service.lister_utilisateurs(db_path=db)}
    assert roles == {
        "admin.paie": RoleUtilisateur.ADMIN,
        "gestion.paie": RoleUtilisateur.GESTIONNAIRE_PAIE,
        "lecture.paie": RoleUtilisateur.CONSULTATION,
    }
    # Permissions inchangées.
    assert {role: permission_service.permissions_du_role(role) for role in RoleUtilisateur} == permissions_avant
    # Base intègre et règles de protection rétablies.
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    assert _noms_declencheurs(db) == declencheurs_avant


def test_application_reste_utilisable_apres_reinitialisation(env):
    """Après réinitialisation, un nouveau cycle de paie complet fonctionne normalement."""
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    _peupler_donnees_metier(env)
    assert _reinitialiser(env, admin.id).reussie

    enseignant = enseignant_service.creer_enseignant(
        nom="Mbarga", prenom="Alice", sexe="F", statut="P", taux_horaire=2000, db_path=db
    )
    periode = periode_service.creer_periode(mois=10, annee=2030, db_path=db)
    periode_service.ouvrir_periode(periode.id, db_path=db)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode.id,
        [DonneesPaieEnseignant(
            enseignant_id=enseignant.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
            retenue_amicale=5000, dette=10000,
        )],
        db_path=db,
    )
    from services.paie_service import calculer_paie_enseignant

    resultat = calculer_paie_enseignant(periode.id, enseignant.id, db_path=db)
    assert resultat.net_a_percevoir == 208250  # cas de référence : formules de paie inchangées


def test_regles_de_protection_toujours_actives_apres_reinitialisation(env):
    """Les déclencheurs supprimés temporairement sont bien recréés : une période validée reste non supprimable."""
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    _peupler_donnees_metier(env)
    assert _reinitialiser(env, admin.id).reussie

    periode = periode_service.creer_periode(mois=11, annee=2030, db_path=db)
    periode_service.ouvrir_periode(periode.id, db_path=db)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM periodes_paie WHERE id = ?", (periode.id,))
    finally:
        conn.close()


def test_reinitialisation_sur_base_deja_vierge(env):
    admin, _, _ = _creer_comptes(env["db"])
    rapport = _reinitialiser(env, admin.id)
    assert rapport.reussie
    assert sum(rapport.elements_supprimes.values()) == 0


# ---------------------------------------------------------------------
# Séparation des privilèges (section 28) — appel DIRECT du service
# ---------------------------------------------------------------------

def test_admin_peut_reinitialiser(env):
    admin, _, _ = _creer_comptes(env["db"])
    _peupler_donnees_metier(env)
    assert _reinitialiser(env, admin.id).reussie


@pytest.mark.parametrize("indice_compte", [1, 2], ids=["GESTIONNAIRE_PAIE", "CONSULTATION"])
def test_non_admin_refuse_meme_en_appel_direct(env, indice_compte):
    comptes = _creer_comptes(env["db"])
    _peupler_donnees_metier(env)
    enseignants_avant = _compter(env["db"], "enseignants")

    with pytest.raises(AutorisationRefuseeError):
        _reinitialiser(env, comptes[indice_compte].id)

    assert _compter(env["db"], "enseignants") == enseignants_avant
    assert not env["backups"].exists() or not any(env["backups"].iterdir()), "Aucune sauvegarde ne doit être créée"


def test_utilisateur_inconnu_refuse(env):
    _creer_comptes(env["db"])
    with pytest.raises(AutorisationRefuseeError):
        _reinitialiser(env, 9999)


def test_aucun_utilisateur_refuse(env):
    _creer_comptes(env["db"])
    with pytest.raises(AutorisationRefuseeError):
        _reinitialiser(env, None)


def test_admin_desactive_refuse(env):
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    second_admin = utilisateur_service.creer_utilisateur(
        "Ondoa", "Eric", "admin2", MDP_ADMIN, RoleUtilisateur.ADMIN, db_path=db
    )
    utilisateur_service.desactiver_utilisateur(second_admin.id, db_path=db)
    with pytest.raises(AutorisationRefuseeError):
        _reinitialiser(env, second_admin.id)


def test_role_relu_en_base_et_non_en_session(env):
    """Un administrateur rétrogradé entre-temps est refusé, quel que soit le rôle encore affiché en session."""
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    autre_admin = utilisateur_service.creer_utilisateur(
        "Ondoa", "Eric", "admin2", MDP_ADMIN, RoleUtilisateur.ADMIN, db_path=db
    )
    utilisateur_service.modifier_utilisateur(
        autre_admin.id, nom="Ondoa", prenom="Eric", role=RoleUtilisateur.CONSULTATION, db_path=db
    )
    with pytest.raises(AutorisationRefuseeError):
        _reinitialiser(env, autre_admin.id)


def test_tentative_refusee_journalisee(env):
    db = env["db"]
    _, gestion, _ = _creer_comptes(db)
    with pytest.raises(AutorisationRefuseeError):
        _reinitialiser(env, gestion.id)
    conn = sqlite3.connect(db)
    try:
        lignes = conn.execute(
            "SELECT utilisateur, details FROM audit_log WHERE type_action = ?",
            (TypeActionAudit.REINITIALISATION_DONNEES_ECHEC.value,),
        ).fetchall()
    finally:
        conn.close()
    assert lignes and lignes[-1][0] == "gestion.paie"
    assert "Refusée" in lignes[-1][1]


def test_permission_reservee_a_admin_dans_la_matrice():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.DONNEES_REINITIALISER)
    assert not permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.DONNEES_REINITIALISER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.DONNEES_REINITIALISER)
    assert not permission_service.a_permission(None, permission_service.DONNEES_REINITIALISER)


# ---------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------

@pytest.mark.parametrize("phrase", ["", "reinitialiser", "Réinitialiser", "OUI", "RESET", None])
def test_phrase_de_confirmation_incorrecte_refusee(env, phrase):
    admin, _, _ = _creer_comptes(env["db"])
    _peupler_donnees_metier(env)
    with pytest.raises(ConfirmationInvalideError):
        _reinitialiser(env, admin.id, phrase=phrase)
    assert _compter(env["db"], "enseignants") == 2


def test_case_de_confirmation_obligatoire(env):
    admin, _, _ = _creer_comptes(env["db"])
    _peupler_donnees_metier(env)
    with pytest.raises(ConfirmationInvalideError):
        _reinitialiser(env, admin.id, confirmation=False)
    assert _compter(env["db"], "enseignants") == 2


def test_phrase_sans_accent_acceptee(env):
    admin, _, _ = _creer_comptes(env["db"])
    assert _reinitialiser(env, admin.id, phrase="  REINITIALISER ").reussie


# ---------------------------------------------------------------------
# Sauvegarde préalable
# ---------------------------------------------------------------------

def test_sauvegarde_creee_avant_suppression_et_complete(env):
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    _peupler_donnees_metier(env)

    rapport = _reinitialiser(env, admin.id)

    assert rapport.sauvegarde_archive is not None and rapport.sauvegarde_archive.exists()
    assert rapport.sauvegarde_base is not None and rapport.sauvegarde_base.exists()
    assert rapport.sauvegarde_archive.name.startswith("Avant_Reinitialisation_")
    # La sauvegarde contient l'état AVANT suppression : données et documents.
    conn = sqlite3.connect(rapport.sauvegarde_base)
    try:
        assert conn.execute("SELECT COUNT(*) FROM enseignants").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM bulletins_paie").fetchone()[0] == 2
    finally:
        conn.close()
    with zipfile.ZipFile(rapport.sauvegarde_archive) as archive:
        noms = archive.namelist()
    assert any(n.startswith("documents/") and n.endswith(".docx") for n in noms)
    assert any(n.startswith("base_de_donnees/") for n in noms)


def test_echec_de_sauvegarde_annule_tout(env, monkeypatch):
    admin, _, _ = _creer_comptes(env["db"])
    _peupler_donnees_metier(env)

    def _sauvegarde_impossible(*args, **kwargs):
        raise reinitialisation_service.backup_service.BackupServiceError("disque plein (simulé)")

    monkeypatch.setattr(reinitialisation_service.backup_service, "creer_sauvegarde_complete", _sauvegarde_impossible)
    with pytest.raises(ReinitialisationError):
        _reinitialiser(env, admin.id)
    assert _compter(env["db"], "enseignants") == 2
    assert any(env["exports"].rglob("*.docx"))


def test_sauvegarde_restaurable_depuis_l_onglet_restauration(env):
    """La base sauvegardée avant réinitialisation est une sauvegarde standard, restaurable."""
    from services import backup_service

    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    _peupler_donnees_metier(env)
    rapport = _reinitialiser(env, admin.id)
    assert _compter(db, "enseignants") == 0

    resultat = backup_service.restaurer_sauvegarde(
        rapport.sauvegarde_base, confirmation=True, db_path=db, backup_dir=env["backups"]
    )
    assert resultat.reussie
    assert _compter(db, "enseignants") == 2


# ---------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------

def test_rollback_si_echec_pendant_la_transaction(env, monkeypatch):
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    _peupler_donnees_metier(env)
    volumes_avant = {c.table: _compter(db, c.table) for c in CATEGORIES_SUPPRIMEES}
    fichiers_avant = sorted(p.relative_to(env["exports"]) for p in env["exports"].rglob("*") if p.is_file())
    comptes_avant = _lignes_comptes(db)
    declencheurs_avant = _noms_declencheurs(db)

    def _echec_simule(*args, **kwargs):
        raise ReinitialisationError("panne simulée pendant la vérification")

    monkeypatch.setattr(reinitialisation_service, "_verifier_etat_avant_validation", _echec_simule)
    rapport = _reinitialiser(env, admin.id)

    assert not rapport.reussie
    assert "annulée" in rapport.message
    assert {c.table: _compter(db, c.table) for c in CATEGORIES_SUPPRIMEES} == volumes_avant
    assert sorted(p.relative_to(env["exports"]) for p in env["exports"].rglob("*") if p.is_file()) == fichiers_avant
    assert _lignes_comptes(db) == comptes_avant
    assert _noms_declencheurs(db) == declencheurs_avant
    assert not list(env["exports"].parent.glob(".reinitialisation_en_cours_*"))


def test_restauration_automatique_si_verification_finale_echoue(env, monkeypatch):
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    _peupler_donnees_metier(env)
    volumes_avant = {c.table: _compter(db, c.table) for c in CATEGORIES_SUPPRIMEES}
    fichiers_avant = sorted(p.relative_to(env["exports"]) for p in env["exports"].rglob("*") if p.is_file())

    def _echec_final(*args, **kwargs):
        raise ReinitialisationError("intégrité simulée en échec")

    monkeypatch.setattr(reinitialisation_service, "_verifier_etat_apres_validation", _echec_final)
    rapport = _reinitialiser(env, admin.id)

    assert not rapport.reussie
    assert rapport.restauration_effectuee
    assert {c.table: _compter(db, c.table) for c in CATEGORIES_SUPPRIMEES} == volumes_avant
    assert sorted(p.relative_to(env["exports"]) for p in env["exports"].rglob("*") if p.is_file()) == fichiers_avant
    assert auth_service.connecter("admin.paie", MDP_ADMIN, db_path=db).reussie


def test_base_corrompue_refusee_avant_toute_action(env, monkeypatch):
    admin, _, _ = _creer_comptes(env["db"])
    _peupler_donnees_metier(env)
    from services.backup_service import ResultatIntegrite

    monkeypatch.setattr(
        reinitialisation_service.backup_service, "verifier_integrite",
        lambda chemin: ResultatIntegrite(False, "corruption simulée"),
    )
    with pytest.raises(ReinitialisationError):
        _reinitialiser(env, admin.id)
    assert _compter(env["db"], "enseignants") == 2


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def _entrees_audit(db, type_action):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM audit_log WHERE type_action = ? ORDER BY id", (type_action.value,)
        ).fetchall()
    finally:
        conn.close()


def test_audit_de_reinitialisation_complet_et_sans_secret(env):
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    _peupler_donnees_metier(env)
    rapport = _reinitialiser(env, admin.id)

    entrees = _entrees_audit(db, TypeActionAudit.REINITIALISATION_DONNEES)
    assert len(entrees) == 1
    entree = entrees[0]
    assert entree["utilisateur"] == "admin.paie"
    assert entree["date_action"]
    assert "réussie" in entree["details"]
    assert rapport.sauvegarde_archive.name in entree["details"]
    assert "Enseignants : 2" in entree["details"]
    assert "Bulletins de paie : 2" in entree["details"]
    assert "Comptes utilisateurs conservés : 3" in entree["details"]

    conn = sqlite3.connect(db)
    try:
        hashes = [r[0] for r in conn.execute("SELECT password_hash FROM utilisateurs")]
        textes_audit = " ".join(r[0] or "" for r in conn.execute("SELECT details FROM audit_log"))
    finally:
        conn.close()
    for secret in [MDP_ADMIN, MDP_GESTION, MDP_LECTURE, *hashes, "scrypt$"]:
        assert secret not in textes_audit


def test_journal_d_audit_conserve_en_entier(env):
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    auth_service.connecter("admin.paie", MDP_ADMIN, db_path=db)
    auth_service.connecter("admin.paie", "mauvais-mot-de-passe", db_path=db)
    _peupler_donnees_metier(env)
    connexions_avant = len(_entrees_audit(db, TypeActionAudit.CONNEXION_REUSSIE))
    echecs_avant = len(_entrees_audit(db, TypeActionAudit.CONNEXION_ECHOUEE))
    bulletins_avant = len(_entrees_audit(db, TypeActionAudit.GENERATION_BULLETIN))
    alertes_avant = len(_entrees_audit(db, TypeActionAudit.ALERTE_CREEE))
    assert bulletins_avant

    assert _reinitialiser(env, admin.id).reussie

    assert len(_entrees_audit(db, TypeActionAudit.CONNEXION_REUSSIE)) == connexions_avant
    assert len(_entrees_audit(db, TypeActionAudit.CONNEXION_ECHOUEE)) == echecs_avant
    # L'historique métier n'est pas effacé : un administrateur ne peut pas
    # faire disparaître la trace des bulletins générés ou des alertes.
    assert len(_entrees_audit(db, TypeActionAudit.GENERATION_BULLETIN)) == bulletins_avant
    assert len(_entrees_audit(db, TypeActionAudit.ALERTE_CREEE)) == alertes_avant


def test_echec_journalise(env, monkeypatch):
    db = env["db"]
    admin, _, _ = _creer_comptes(db)
    monkeypatch.setattr(
        reinitialisation_service, "_verifier_etat_avant_validation",
        lambda *a, **k: (_ for _ in ()).throw(ReinitialisationError("panne simulée")),
    )
    rapport = _reinitialiser(env, admin.id)
    assert not rapport.reussie
    entrees = _entrees_audit(db, TypeActionAudit.REINITIALISATION_DONNEES_ECHEC)
    assert entrees and entrees[-1]["utilisateur"] == "admin.paie"


# ---------------------------------------------------------------------
# Aperçu et exhaustivité du périmètre
# ---------------------------------------------------------------------

def test_apercu_reflete_les_donnees_reelles_sans_rien_modifier(env):
    db = env["db"]
    _creer_comptes(db)
    _peupler_donnees_metier(env)
    apercu = reinitialisation_service.apercu_reinitialisation(db_path=db, dossier_exports=env["exports"])
    assert apercu.elements_a_supprimer["Enseignants"] == 2
    assert apercu.elements_a_supprimer["Périodes de paie"] == 1
    assert apercu.elements_a_supprimer["Bulletins de paie"] == 2
    assert apercu.comptes_conserves == 3
    assert apercu.fichiers_a_supprimer >= 4
    assert apercu.tables_non_classees == []
    assert _compter(db, "enseignants") == 2


def test_toute_table_du_schema_est_classee(tmp_path):
    """Une table ajoutée au schéma sans être classée ferait échouer ce test : jamais d'oubli silencieux."""
    base = tmp_path / "schema.db"
    init_database(db_path=base)
    conn = sqlite3.connect(base)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
    finally:
        conn.close()
    classees = {c.table for c in CATEGORIES_SUPPRIMEES} | set(TABLES_CONSERVEES)
    assert tables == classees


def test_tables_d_authentification_jamais_dans_le_perimetre_supprime():
    tables_supprimees = {c.table for c in CATEGORIES_SUPPRIMEES}
    assert "utilisateurs" not in tables_supprimees
    assert "audit_log" not in tables_supprimees


def test_reinitialisation_donnees_distincte_de_reinitialisation_comptes():
    """Deux fonctions distinctes : la réinitialisation des données n'appelle jamais celle des comptes."""
    import inspect

    source = inspect.getsource(reinitialisation_service)
    assert "reinitialiser_tous_les_comptes" not in source
    assert "DELETE FROM utilisateurs" not in source
    assert "UPDATE utilisateurs" not in source
