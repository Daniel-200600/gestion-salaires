"""
Tests de services/alert_service.py (module 16).
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from models.enums import NiveauAlerte, RoleUtilisateur, StatutAlerte
from services import alert_service, enseignant_service, periode_service, permission_service
from services.alert_service import AlertServiceError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Kamgang", "prenom": "Jean", "sexe": "M", "statut": "P", "taux_horaire": 2000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_alerte(**overrides):
    donnees = dict(
        type_alerte="TEST_ALERTE", niveau=NiveauAlerte.AVERTISSEMENT, titre="Titre de test",
        message="Message de test", source="test",
    )
    donnees.update(overrides)
    return alert_service.creer_ou_mettre_a_jour_alerte(**donnees)


# ---------------------------------------------------------------------
# Création
# ---------------------------------------------------------------------

def test_creation_alerte():
    alerte = _creer_alerte()
    assert alerte.id is not None
    assert alerte.statut == StatutAlerte.NOUVELLE
    assert alerte.niveau == NiveauAlerte.AVERTISSEMENT
    assert alerte.message == "Message de test"
    assert alerte.date_creation is not None


def test_creation_alerte_avec_contexte():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=1, annee=2090)
    alerte = _creer_alerte(periode_id=p.id, enseignant_id=e.id)
    assert alerte.periode_id == p.id
    assert alerte.enseignant_id == e.id


# ---------------------------------------------------------------------
# Déduplication (section 13)
# ---------------------------------------------------------------------

def test_meme_anomalie_detectee_deux_fois_pas_de_duplication():
    a1 = _creer_alerte()
    a2 = _creer_alerte(message="Message mis à jour")
    assert a1.id == a2.id
    assert a2.message == "Message mis à jour"

    toutes = alert_service.lister_alertes()
    assert len(toutes) == 1


def test_deduplication_specifique_au_contexte():
    e1 = _creer_enseignant(nom="A", prenom="A")
    e2 = _creer_enseignant(nom="B", prenom="B")
    _creer_alerte(enseignant_id=e1.id)
    _creer_alerte(enseignant_id=e2.id)
    assert len(alert_service.lister_alertes()) == 2


def test_alerte_resolue_puis_redetectee_cree_une_nouvelle_alerte():
    a1 = _creer_alerte()
    alert_service.resoudre(a1.id)
    a2 = _creer_alerte()
    assert a2.id != a1.id
    assert a2.statut == StatutAlerte.NOUVELLE


# ---------------------------------------------------------------------
# Statuts et transitions (section 12)
# ---------------------------------------------------------------------

def test_transition_nouvelle_vers_lue():
    a = _creer_alerte()
    resultat = alert_service.marquer_lue(a.id, utilisateur="admin")
    assert resultat.statut == StatutAlerte.LUE


def test_transition_lue_vers_acquittee():
    a = _creer_alerte()
    alert_service.marquer_lue(a.id)
    resultat = alert_service.acquitter(a.id, utilisateur="admin")
    assert resultat.statut == StatutAlerte.ACQUITTEE
    assert resultat.acquitte_par == "admin"
    assert resultat.date_acquittement is not None


def test_transition_acquittee_vers_resolue():
    a = _creer_alerte()
    alert_service.marquer_lue(a.id)
    alert_service.acquitter(a.id)
    resultat = alert_service.resoudre(a.id, utilisateur="admin")
    assert resultat.statut == StatutAlerte.RESOLUE
    assert resultat.resolue_par == "admin"


def test_transition_nouvelle_vers_ignoree():
    a = _creer_alerte()
    resultat = alert_service.ignorer(a.id, utilisateur="admin")
    assert resultat.statut == StatutAlerte.IGNOREE


def test_transition_nouvelle_vers_resolue_directe_autorisee():
    a = _creer_alerte()
    resultat = alert_service.resoudre(a.id)
    assert resultat.statut == StatutAlerte.RESOLUE


def test_transition_resolue_vers_lue_refusee():
    a = _creer_alerte()
    alert_service.resoudre(a.id)
    with pytest.raises(AlertServiceError):
        alert_service.marquer_lue(a.id)


def test_transition_ignoree_vers_acquittee_refusee():
    a = _creer_alerte()
    alert_service.ignorer(a.id)
    with pytest.raises(AlertServiceError):
        alert_service.acquitter(a.id)


def test_transition_alerte_inexistante_leve():
    with pytest.raises(AlertServiceError):
        alert_service.acquitter(999999)


# ---------------------------------------------------------------------
# Résolution automatique (section 14)
# ---------------------------------------------------------------------

def test_resolution_automatique_conserve_historique():
    a = _creer_alerte()
    n_resolues = alert_service.resoudre_alertes_obsoletes("test", cles_encore_actives=[])
    assert n_resolues == 1

    relue = alert_service.lister_alertes()[0]
    assert relue.statut == StatutAlerte.RESOLUE
    assert relue.id == a.id


def test_resolution_automatique_epargne_les_alertes_toujours_actives():
    a = _creer_alerte()
    n_resolues = alert_service.resoudre_alertes_obsoletes("test", cles_encore_actives=[a.cle_deduplication])
    assert n_resolues == 0
    assert alert_service.lister_alertes()[0].statut == StatutAlerte.NOUVELLE


def test_resolution_automatique_ignore_les_autres_sources():
    _creer_alerte(source="autre_source")
    n_resolues = alert_service.resoudre_alertes_obsoletes("test", cles_encore_actives=[])
    assert n_resolues == 0


# ---------------------------------------------------------------------
# Audit (section 21)
# ---------------------------------------------------------------------

def test_audit_creation_alerte(db_path):
    _creer_alerte()
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'alerte_creee'").fetchall()
    assert len(lignes) == 1


def test_audit_acquittement(db_path):
    a = _creer_alerte()
    alert_service.acquitter(a.id, utilisateur="admin")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'alerte_acquittee'").fetchall()
    assert len(lignes) == 1
    assert lignes[0]["utilisateur"] == "admin"


def test_audit_resolution(db_path):
    a = _creer_alerte()
    alert_service.resoudre(a.id, utilisateur="admin")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'alerte_resolue'").fetchall()
    assert len(lignes) == 1


def test_audit_ignoree(db_path):
    a = _creer_alerte()
    alert_service.ignorer(a.id, utilisateur="admin")
    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'alerte_ignoree'").fetchall()
    assert len(lignes) == 1


# ---------------------------------------------------------------------
# Recherche / compteurs
# ---------------------------------------------------------------------

def test_lister_alertes_filtre_par_niveau():
    _creer_alerte(type_alerte="A", niveau=NiveauAlerte.CRITIQUE)
    _creer_alerte(type_alerte="B", niveau=NiveauAlerte.INFO)
    resultats = alert_service.lister_alertes(niveau=NiveauAlerte.CRITIQUE)
    assert len(resultats) == 1
    assert resultats[0].type_alerte == "A"


def test_compter_alertes_actives_exclut_resolues_et_ignorees():
    a1 = _creer_alerte(type_alerte="A")
    _creer_alerte(type_alerte="B")
    alert_service.resoudre(a1.id)

    compteurs = alert_service.compter_alertes_actives()
    assert sum(compteurs.values()) == 1


# ---------------------------------------------------------------------
# Permissions (section 20)
# ---------------------------------------------------------------------

def test_permission_alerte_consulter_accessible_aux_trois_roles():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.ALERTE_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.ALERTE_CONSULTER)
    assert permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.ALERTE_CONSULTER)


def test_permission_alerte_gerer_refusee_a_consultation():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.ALERTE_GERER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.ALERTE_GERER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.ALERTE_GERER)
