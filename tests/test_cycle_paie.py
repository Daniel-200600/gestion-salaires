"""
Tests du module 12 : machine à états des périodes, protection des
données de paie après validation/clôture, audit du cycle, historique.
"""

import pytest

import database.connection as database_connection
from database.connection import get_connection
from models.enums import RoleUtilisateur, StatutPeriode
from services import (
    controle_paie_service,
    donnees_paie_service,
    enseignant_service,
    heures_service,
    periode_service,
    remuneration_service,
    retenue_service,
)
from services.controle_paie_service import ControlePaieError
from services.donnees_paie_service import DonneesPaieEnseignant
from services.heures_service import DonneesPaieValidationError
from services.periode_service import PeriodeValidationError

# Cas de référence officiel : vacataire, taxe de 5 %.
pytestmark = pytest.mark.taxe_historique


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    from services import bulletin_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", db_path.parent / "bulletins")


def _creer_enseignant(**overrides):
    donnees = {"nom": "Ondoa", "prenom": "Serge", "sexe": "M", "statut": "V", "taux_horaire": 2000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


def _periode_cloturee_avec_donnees(e):
    p = periode_service.creer_periode(mois=1, annee=2041)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    _saisir_donnees(
        p.id, e.id,
        heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
        prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
        retenue_amicale=5000, dette=10000,
    )
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)
    return periode_service.obtenir_periode(p.id)


# ---------------------------------------------------------------------
# Machine à états — transitions autorisées
# ---------------------------------------------------------------------

def test_workflow_complet_brouillon_ouverte_validee_cloturee():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=2, annee=2041)
    assert p.statut == StatutPeriode.BROUILLON

    p = controle_paie_service.ouvrir_periode_avec_audit(p.id)
    assert p.statut == StatutPeriode.OUVERTE

    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=500)
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    p = periode_service.obtenir_periode(p.id)
    assert p.statut == StatutPeriode.VALIDEE

    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)
    p = periode_service.obtenir_periode(p.id)
    assert p.statut == StatutPeriode.CLOTUREE


# ---------------------------------------------------------------------
# Machine à états — transitions interdites
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "statut_depart,statut_cible",
    [
        (StatutPeriode.CLOTUREE, StatutPeriode.OUVERTE),
        (StatutPeriode.CLOTUREE, StatutPeriode.VALIDEE),
        (StatutPeriode.CLOTUREE, StatutPeriode.BROUILLON),
        (StatutPeriode.VALIDEE, StatutPeriode.OUVERTE),
        (StatutPeriode.VALIDEE, StatutPeriode.BROUILLON),
        (StatutPeriode.OUVERTE, StatutPeriode.BROUILLON),
    ],
)
def test_transitions_inverses_toujours_interdites(statut_depart, statut_cible):
    assert periode_service.transition_autorisee(statut_depart, statut_cible) is False


@pytest.mark.parametrize(
    "statut_depart,statut_cible",
    [
        (StatutPeriode.BROUILLON, StatutPeriode.OUVERTE),
        (StatutPeriode.OUVERTE, StatutPeriode.VALIDEE),
        (StatutPeriode.VALIDEE, StatutPeriode.CLOTUREE),
    ],
)
def test_transitions_normales_autorisees(statut_depart, statut_cible):
    assert periode_service.transition_autorisee(statut_depart, statut_cible) is True


def test_cloture_ne_peut_pas_etre_appelee_directement_sur_ouverte():
    p = periode_service.creer_periode(mois=3, annee=2041)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    with pytest.raises(ControlePaieError, match="VALIDEE"):
        controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)


def test_validation_ne_peut_pas_etre_appelee_sur_brouillon():
    p = periode_service.creer_periode(mois=4, annee=2041)
    with pytest.raises(ControlePaieError):
        controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)


# ---------------------------------------------------------------------
# Helpers centralisés de modifiabilité
# ---------------------------------------------------------------------

def test_est_modifiable_uniquement_pour_ouverte():
    p_brouillon = periode_service.creer_periode(mois=5, annee=2041)
    assert periode_service.est_modifiable(p_brouillon) is False

    p_ouverte = controle_paie_service.ouvrir_periode_avec_audit(p_brouillon.id)
    assert periode_service.est_modifiable(p_ouverte) is True


def test_est_cloturee():
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    assert periode_service.est_cloturee(p) is True
    assert periode_service.est_modifiable(p) is False


def test_verifier_periode_modifiable_leve_si_non_modifiable():
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    with pytest.raises(PeriodeValidationError, match="ne sont plus modifiables"):
        periode_service.verifier_periode_modifiable(p)


# ---------------------------------------------------------------------
# Protection des heures pour une période clôturée
# ---------------------------------------------------------------------

def test_periode_cloturee_empeche_ajout_heures():
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(p.id, e.id, {1: 99})


def test_periode_cloturee_empeche_modification_heures_existantes():
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    heures_avant = heures_service.obtenir_heures_enseignant(p.id, e.id)
    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(p.id, e.id, {1: 5})
    heures_apres = heures_service.obtenir_heures_enseignant(p.id, e.id)
    assert heures_avant == heures_apres  # rien n'a changé


def test_aucune_fonction_de_suppression_individuelle_exposee():
    """
    Aucun service de saisie (heures/rémunération/retenue) n'expose de
    fonction de suppression d'une ligne individuelle : la seule
    suppression possible passe soit par la transaction complète de
    suppression d'enseignant (services.enseignant_service, qui exige
    l'absence de bulletin), soit par celle de période (qui exige le
    statut BROUILLON) — toutes deux déjà protégées, transactionnelles
    et auditées depuis les modules 08/09. Aucune opération normale de
    saisie (module 03/04) ne peut donc jamais supprimer une ligne
    d'une période clôturée.

    Note : la cascade de suppression définitive d'un enseignant reste,
    elle, volontairement inchangée (règle du module 08) — elle purge
    toutes les données d'un enseignant, y compris sur une période
    clôturée, tant qu'aucun bulletin n'a été généré pour lui. Ce n'est
    pas une régression du module 12 : c'est la même règle que depuis
    le module 08, non modifiée ici.
    """
    assert not hasattr(heures_service, "supprimer_heures_enseignant")
    assert not hasattr(remuneration_service, "supprimer_remuneration_enseignant")
    assert not hasattr(retenue_service, "supprimer_retenues_enseignant")


# ---------------------------------------------------------------------
# Protection des rémunérations et retenues
# ---------------------------------------------------------------------

def test_periode_cloturee_empeche_modification_remuneration():
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    with pytest.raises(DonneesPaieValidationError):
        remuneration_service.enregistrer_remuneration_enseignant(p.id, e.id, prime_ap_pp=99999)


def test_periode_cloturee_empeche_modification_retenue():
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    with pytest.raises(DonneesPaieValidationError):
        retenue_service.enregistrer_retenues_enseignant(p.id, e.id, dette=99999)


def test_periode_validee_empeche_aussi_la_modification():
    """VALIDEE (pas seulement CLOTUREE) bloque déjà toute écriture — seule OUVERTE autorise la saisie."""
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=6, annee=2041)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    p = periode_service.obtenir_periode(p.id)

    with pytest.raises(DonneesPaieValidationError):
        heures_service.enregistrer_heures_enseignant(p.id, e.id, {1: 50})


# ---------------------------------------------------------------------
# Le calcul (paie_service) reste inchangé pour une période clôturée
# ---------------------------------------------------------------------

def test_calcul_paie_inchange_apres_cloture():
    e = _creer_enseignant(taux_horaire=2000)
    p = _periode_cloturee_avec_donnees(e)
    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir == 208250


# ---------------------------------------------------------------------
# Suppression de période (protections du module 08/09 intactes)
# ---------------------------------------------------------------------

def test_suppression_periode_cloturee_toujours_interdite():
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    with pytest.raises(PeriodeValidationError, match="BROUILLON"):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)


def test_suppression_periode_ouverte_toujours_interdite():
    p = periode_service.creer_periode(mois=7, annee=2041)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    with pytest.raises(PeriodeValidationError, match="BROUILLON"):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)


def test_suppression_periode_brouillon_toujours_autorisee():
    p = periode_service.creer_periode(mois=8, annee=2041)
    periode_service.supprimer_periode_definitivement(p.id, confirmation=True)
    assert periode_service.obtenir_periode.__call__  # sanity: fonction toujours utilisable
    from services.periode_service import PeriodeNotFoundError
    with pytest.raises(PeriodeNotFoundError):
        periode_service.obtenir_periode(p.id)


# ---------------------------------------------------------------------
# Contrôle avant validation / clôture (réutilise le module 09)
# ---------------------------------------------------------------------

def test_validation_refusee_si_enseignant_non_calculable():
    p = periode_service.creer_periode(mois=9, annee=2041)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    rapport = controle_paie_service.controler_periode(p.id, enseignant_ids=[9999])
    assert rapport.est_bloque


def test_validation_reussie_sans_anomalie():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=10, annee=2041)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=500)
    rapport = controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
    assert not rapport.est_bloque


# ---------------------------------------------------------------------
# Permissions des 3 rôles sur le cycle
# ---------------------------------------------------------------------

def test_permissions_cycle_pour_les_trois_roles():
    from services import permission_service
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.PERIODE_GERER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.PERIODE_GERER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.PERIODE_GERER)

    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.PAIE_VALIDER)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.PAIE_VALIDER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.PAIE_VALIDER)

    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.PAIE_CLOTURER)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.PAIE_CLOTURER)


# ---------------------------------------------------------------------
# Audit du cycle
# ---------------------------------------------------------------------

def test_audit_ouverture(db_path):
    p = periode_service.creer_periode(mois=11, annee=2041)
    controle_paie_service.ouvrir_periode_avec_audit(p.id, utilisateur="testeur")
    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'periode_ouverte' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert len(lignes) == 1
    assert lignes[0]["utilisateur"] == "testeur"


def test_audit_validation_refusee(db_path):
    from unittest.mock import patch
    import services.controle_paie_service as cps

    p = periode_service.creer_periode(mois=1, annee=2042)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    rapport = controle_paie_service.controler_periode(p.id, enseignant_ids=[9999])
    assert rapport.est_bloque

    with patch.object(cps, "controler_periode", return_value=rapport):
        with pytest.raises(ControlePaieError):
            cps.valider_periode_avec_controle(p.id, confirmation=True, db_path=db_path)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'validation_refusee' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert len(lignes) == 1


def test_audit_cloture_refusee_mauvais_statut(db_path):
    p = periode_service.creer_periode(mois=2, annee=2042)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)  # reste OUVERTE, pas VALIDEE
    with pytest.raises(ControlePaieError):
        controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True, db_path=db_path)
    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'cloture_refusee' AND entite_id = ?", (p.id,)
        ).fetchall()
    assert len(lignes) == 1


def test_audit_complet_du_cycle_avec_utilisateurs(db_path):
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=3, annee=2042)
    controle_paie_service.ouvrir_periode_avec_audit(p.id, utilisateur="alice")
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True, utilisateur="bob")
    controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True, utilisateur="carole")

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT type_action, utilisateur FROM audit_log WHERE entite_id = ? ORDER BY id", (p.id,)
        ).fetchall()
    evenements = [(l["type_action"], l["utilisateur"]) for l in lignes]
    assert ("periode_ouverte", "alice") in evenements
    assert ("validation_periode", "bob") in evenements
    assert ("cloture_periode", "carole") in evenements


# ---------------------------------------------------------------------
# Historique conservé pour une période clôturée
# ---------------------------------------------------------------------

def test_historique_conserve_apres_cloture():
    from services import historique_paie_service
    e = _creer_enseignant()
    p = _periode_cloturee_avec_donnees(e)
    historique = historique_paie_service.historique_enseignant(e.id)
    assert len(historique) == 1
    assert historique[0].resultat.net_a_percevoir == 208250


# ---------------------------------------------------------------------
# Cas de référence officiel, à travers le cycle complet
# ---------------------------------------------------------------------

def test_cas_reference_a_travers_le_cycle_complet():
    e = _creer_enseignant(taux_horaire=2000)
    p = _periode_cloturee_avec_donnees(e)
    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.total_heures == 100
    assert resultat.gain_heures == 200000
    assert resultat.base_taxable == 235000
    assert resultat.taxe_5 == 11750
    assert resultat.net_a_percevoir == 208250
