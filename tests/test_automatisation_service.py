"""
Tests de services/automatisation_service.py (module 18).
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from models.enums import RoleUtilisateur, StatutOperationAutomatisation
from services import (
    automatisation_service,
    controle_paie_service,
    donnees_paie_service,
    enseignant_service,
    periode_service,
    permission_service,
)
from services.automatisation_service import AutomatisationError
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch, tmp_path):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    from services import bulletin_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")


def _creer_enseignant(**overrides):
    donnees = {"nom": "Kamgang", "prenom": "Jean", "sexe": "M", "statut": "P", "taux_horaire": 2000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _periode_ouverte_avec_donnees(mois=1, annee=2099):
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=mois, annee=annee)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
            retenue_amicale=5000, dette=10000),
    ])
    return p, e


# ---------------------------------------------------------------------
# Préconditions
# ---------------------------------------------------------------------

def test_preconditions_periode_saine_ok():
    p, e = _periode_ouverte_avec_donnees()
    resultat = automatisation_service.verifier_preconditions(p.id)
    assert resultat.ok is True
    assert resultat.problemes_bloquants == []


def test_preconditions_periode_inexistante():
    resultat = automatisation_service.verifier_preconditions(999999)
    assert resultat.ok is False


def test_preconditions_periode_vide_signale_avertissement():
    p = periode_service.creer_periode(mois=2, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    resultat = automatisation_service.verifier_preconditions(p.id)
    assert resultat.avertissements or not resultat.ok


# ---------------------------------------------------------------------
# Dry run — jamais d'écriture
# ---------------------------------------------------------------------

def test_dry_run_ne_cree_aucun_document():
    from services import document_service
    p, e = _periode_ouverte_avec_donnees(mois=3)
    automatisation_service.analyser_generation_bulletins(p.id)
    assert document_service.rechercher_documents(periode_id=p.id) == []


def test_dry_run_classifie_correctement():
    p, e = _periode_ouverte_avec_donnees(mois=4)
    analyse = automatisation_service.analyser_generation_bulletins(p.id)
    assert analyse.nombre_prets == 1
    assert analyse.nombre_deja_existants == 0


def test_dry_run_detecte_deja_existant_apres_generation():
    p, e = _periode_ouverte_avec_donnees(mois=5)
    automatisation_service.generer_bulletins_massif(p.id)
    analyse = automatisation_service.analyser_generation_bulletins(p.id)
    assert analyse.nombre_deja_existants == 1
    assert analyse.nombre_prets == 0


# ---------------------------------------------------------------------
# Génération massive — idempotence (section 10)
# ---------------------------------------------------------------------

def test_generation_massive_reussie():
    p, e = _periode_ouverte_avec_donnees(mois=6)
    operation = automatisation_service.generer_bulletins_massif(p.id, utilisateur="admin")
    assert operation.succes == 1
    assert operation.erreurs == 0
    assert operation.statut == StatutOperationAutomatisation.TERMINEE


def test_generation_massive_idempotente():
    p, e = _periode_ouverte_avec_donnees(mois=7)
    automatisation_service.generer_bulletins_massif(p.id)
    operation2 = automatisation_service.generer_bulletins_massif(p.id)
    assert operation2.succes == 0
    assert operation2.ignores == 1


def test_generation_massive_forcer_regeneration():
    from services import document_service
    p, e = _periode_ouverte_avec_donnees(mois=8)
    automatisation_service.generer_bulletins_massif(p.id)
    operation2 = automatisation_service.generer_bulletins_massif(p.id, forcer_regeneration=True)
    assert operation2.succes == 1
    documents = document_service.rechercher_documents(periode_id=p.id)
    assert len(documents) == 2


def test_generation_massive_limitee_a_certains_enseignants():
    p = periode_service.creer_periode(mois=9, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    e1 = _creer_enseignant(nom="A", prenom="A")
    e2 = _creer_enseignant(nom="B", prenom="B")
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10}),
        DonneesPaieEnseignant(enseignant_id=e2.id, heures_par_semaine={1: 10}),
    ])
    operation = automatisation_service.generer_bulletins_massif(p.id, enseignant_ids=[e1.id])
    assert operation.total == 1
    assert operation.lignes[0].enseignant_id == e1.id


# ---------------------------------------------------------------------
# Isolation d'erreur (section 9) — une erreur n'interrompt jamais le lot
# ---------------------------------------------------------------------

def test_erreur_individuelle_nempeche_pas_les_autres():
    from unittest.mock import patch
    from services import bulletin_service

    p = periode_service.creer_periode(mois=10, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    e1 = _creer_enseignant(nom="A", prenom="A")
    e2 = _creer_enseignant(nom="B", prenom="B")
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10}),
        DonneesPaieEnseignant(enseignant_id=e2.id, heures_par_semaine={1: 10}),
    ])

    original = bulletin_service.generer_bulletin_enseignant

    def echec_pour_e1(periode_id, enseignant_id, **kwargs):
        if enseignant_id == e1.id:
            raise RuntimeError("Panne simulée")
        return original(periode_id, enseignant_id, **kwargs)

    with patch.object(bulletin_service, "generer_bulletin_enseignant", side_effect=echec_pour_e1):
        operation = automatisation_service.generer_bulletins_massif(p.id)

    assert operation.erreurs == 1
    assert operation.succes == 1
    assert operation.statut == StatutOperationAutomatisation.TERMINEE_AVEC_ERREURS


# ---------------------------------------------------------------------
# Reprise ciblée (section 25)
# ---------------------------------------------------------------------

def test_reprise_ne_retraite_que_les_erreurs():
    from unittest.mock import patch
    from services import bulletin_service

    p = periode_service.creer_periode(mois=11, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    e1 = _creer_enseignant(nom="A", prenom="A")
    e2 = _creer_enseignant(nom="B", prenom="B")
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(enseignant_id=e1.id, heures_par_semaine={1: 10}),
        DonneesPaieEnseignant(enseignant_id=e2.id, heures_par_semaine={1: 10}),
    ])

    original = bulletin_service.generer_bulletin_enseignant

    def echec_pour_e1(periode_id, enseignant_id, **kwargs):
        if enseignant_id == e1.id:
            raise RuntimeError("Panne simulée")
        return original(periode_id, enseignant_id, **kwargs)

    with patch.object(bulletin_service, "generer_bulletin_enseignant", side_effect=echec_pour_e1):
        operation = automatisation_service.generer_bulletins_massif(p.id)

    operation_reprise = automatisation_service.reprendre_erreurs(operation, utilisateur="admin")
    assert operation_reprise.total == 1
    assert operation_reprise.lignes[0].enseignant_id == e1.id
    assert operation_reprise.succes == 1


def test_reprise_sans_erreur_leve():
    p, e = _periode_ouverte_avec_donnees(mois=12)
    operation = automatisation_service.generer_bulletins_massif(p.id)
    with pytest.raises(AutomatisationError):
        automatisation_service.reprendre_erreurs(operation)


# ---------------------------------------------------------------------
# Alertes (section 22) — réutilise le module 16
# ---------------------------------------------------------------------

def test_alerte_creee_si_erreurs():
    from unittest.mock import patch
    from services import alert_service, bulletin_service

    p, e = _periode_ouverte_avec_donnees(mois=1, annee=2100)
    with patch.object(bulletin_service, "generer_bulletin_enseignant", side_effect=RuntimeError("panne")):
        automatisation_service.generer_bulletins_massif(p.id)

    alertes = alert_service.lister_alertes(type_alerte="AUTOMATISATION_ERREURS")
    assert len(alertes) == 1


def test_aucune_alerte_si_succes_complet():
    from services import alert_service
    p, e = _periode_ouverte_avec_donnees(mois=2, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id)
    assert alert_service.lister_alertes(type_alerte="AUTOMATISATION_ERREURS") == []


# ---------------------------------------------------------------------
# Audit (section 21)
# ---------------------------------------------------------------------

def test_audit_generation_massive(db_path):
    p, e = _periode_ouverte_avec_donnees(mois=3, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id, utilisateur="admin")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'generation_massive_bulletins'").fetchall()
    assert len(lignes) == 1
    assert lignes[0]["utilisateur"] == "admin"


def test_audit_preparation(db_path):
    p, e = _periode_ouverte_avec_donnees(mois=4, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id, utilisateur="admin")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'automatisation_preparee'").fetchall()
    assert len(lignes) == 1


# ---------------------------------------------------------------------
# Pack de paie
# ---------------------------------------------------------------------

def test_pack_de_paie_contient_manifest_et_readme(tmp_path):
    import zipfile
    p, e = _periode_ouverte_avec_donnees(mois=5, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id, utilisateur="admin")

    chemin_pack = automatisation_service.creer_pack_paie(
        p.id, etablissement="École Test", utilisateur="admin", dossier_destination=tmp_path
    )
    assert chemin_pack.exists()
    with zipfile.ZipFile(chemin_pack) as archive:
        assert "Manifest.json" in archive.namelist()
        assert "README.txt" in archive.namelist()
        assert any(n.startswith("Bulletins/") for n in archive.namelist())


def test_pack_de_paie_ne_ecrase_jamais(tmp_path):
    p, e = _periode_ouverte_avec_donnees(mois=6, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id)
    chemin1 = automatisation_service.creer_pack_paie(p.id, dossier_destination=tmp_path)
    chemin2 = automatisation_service.creer_pack_paie(p.id, dossier_destination=tmp_path)
    assert chemin1 != chemin2
    assert chemin1.exists() and chemin2.exists()


def test_pack_de_paie_aucun_mot_de_passe(tmp_path):
    import zipfile, json
    p, e = _periode_ouverte_avec_donnees(mois=7, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id, utilisateur="admin")
    chemin_pack = automatisation_service.creer_pack_paie(p.id, utilisateur="admin", dossier_destination=tmp_path)
    with zipfile.ZipFile(chemin_pack) as archive:
        manifest = json.loads(archive.read("Manifest.json").decode("utf-8"))
    assert "password" not in json.dumps(manifest).lower()
    assert "mot_de_passe" not in json.dumps(manifest).lower()


# ---------------------------------------------------------------------
# Archive massive — réutilise le module 14 tel quel
# ---------------------------------------------------------------------

def test_archive_massive_refusee_si_non_cloturee(tmp_path):
    from services.archive_service import ArchiveServiceError
    p, e = _periode_ouverte_avec_donnees(mois=8, annee=2100)
    with pytest.raises(ArchiveServiceError):
        automatisation_service.archiver_periode_massif(p.id, dossier_destination=tmp_path)


def test_archive_massive_reussie_periode_cloturee(tmp_path):
    p, e = _periode_ouverte_avec_donnees(mois=9, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id)
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)

    rapport = automatisation_service.archiver_periode_massif(p.id, utilisateur="admin", dossier_destination=tmp_path)
    assert rapport.chemin_archive.exists()
    assert rapport.nombre_documents == 1


# ---------------------------------------------------------------------
# Vérification d'intégrité — réutilise le module 14 tel quel
# ---------------------------------------------------------------------

def test_verification_integrite_delegue_au_module_14():
    p, e = _periode_ouverte_avec_donnees(mois=10, annee=2100)
    automatisation_service.generer_bulletins_massif(p.id)
    rapport = automatisation_service.verifier_integrite_periode(p.id)
    assert rapport.nombre_documents >= 1


# ---------------------------------------------------------------------
# Permissions (section 27)
# ---------------------------------------------------------------------

def test_permission_automatisation_refusee_a_consultation():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.AUTOMATISATION_EXECUTER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.AUTOMATISATION_EXECUTER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.AUTOMATISATION_EXECUTER)


# ---------------------------------------------------------------------
# Cas de référence officiel, à travers l'automatisation
# ---------------------------------------------------------------------

def test_cas_reference_a_travers_generation_massive():
    p, e = _periode_ouverte_avec_donnees(mois=11, annee=2100)
    operation = automatisation_service.generer_bulletins_massif(p.id, utilisateur="admin")
    assert operation.succes == 1

    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir == 208250
