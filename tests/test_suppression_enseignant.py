"""
Tests de la suppression physique et définitive d'un enseignant
(services/enseignant_service.supprimer_enseignant_definitivement).

Couvre les 3 cas de l'énoncé (aucune donnée / données sans bulletin /
bulletin existant), la transaction en cascade avec rollback, la
non-régression de la désactivation/réactivation, la confirmation
explicite requise, et la conservation de l'audit.
"""

import sqlite3

import pytest

import database.connection as database_connection
from database.connection import get_connection
from database.repositories import enseignant_repository, heures_repository, remuneration_repository, retenue_repository
from services import donnees_paie_service, enseignant_service, periode_service
from services.donnees_paie_service import DonneesPaieEnseignant
from services.enseignant_service import EnseignantValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Konate", "prenom": "Yssouf", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _creer_periode_ouverte(mois=8, annee=2029):
    periode = periode_service.creer_periode(mois=mois, annee=annee)
    return periode_service.ouvrir_periode(periode.id)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


def _inserer_bulletin_minimal(db_path, enseignant, periode_id):
    """Insère directement un bulletin minimal (module 06 pas encore implémenté)."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO bulletins_paie (
                enseignant_id, periode_id, nom_snapshot, prenom_snapshot, sexe_snapshot, statut_snapshot,
                total_heures, taux_horaire, gain_heures, prime_ap_pp, surveillance_secretariat,
                indemnite_suggestion_admin, base_taxable, taxe_5pct, retenue_amicale, dette, net_a_payer
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            """,
            (
                enseignant.id, periode_id, enseignant.nom, enseignant.prenom,
                enseignant.sexe.value, enseignant.statut.value, enseignant.taux_horaire,
            ),
        )
        conn.commit()


# ---------------------------------------------------------------------
# 1 & 2. Suppression sans données liées + enseignant disparu ensuite
# ---------------------------------------------------------------------

def test_suppression_enseignant_sans_donnees():
    e = _creer_enseignant()
    enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)


def test_enseignant_introuvable_apres_suppression():
    e = _creer_enseignant()
    enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)
    assert enseignant_repository.obtenir_par_id(e.id) is None
    with pytest.raises(EnseignantValidationError):
        enseignant_service.obtenir_enseignant(e.id)


# ---------------------------------------------------------------------
# 3, 4, 5. Suppression avec heures / rémunérations / retenues
# ---------------------------------------------------------------------

def test_suppression_enseignant_avec_heures():
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10, 2: 5})]
    )
    enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)
    assert enseignant_repository.obtenir_par_id(e.id) is None
    assert heures_repository.lister_par_enseignant_periode(e.id, p.id) == []


def test_suppression_enseignant_avec_remunerations():
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, prime_ap_pp=5000)]
    )
    enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)
    assert enseignant_repository.obtenir_par_id(e.id) is None
    assert remuneration_repository.lister_par_enseignant_periode(e.id, p.id) == []


def test_suppression_enseignant_avec_retenues():
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, dette=2000)]
    )
    enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)
    assert enseignant_repository.obtenir_par_id(e.id) is None
    assert retenue_repository.lister_par_enseignant_periode(e.id, p.id) == []


# ---------------------------------------------------------------------
# 6. Suppression groupée des données dépendantes (les 3 types à la fois),
#    y compris quand la période n'est plus OUVERTE (CAS 2)
# ---------------------------------------------------------------------

def test_suppression_groupee_toutes_dependances_periode_validee():
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id,
        [DonneesPaieEnseignant(
            enseignant_id=e.id,
            heures_par_semaine={1: 10, 2: 8, 3: 6},
            prime_ap_pp=1000, surveillance_secretariat=500, indemnite_suggestion_admin=200,
            retenue_amicale=100, dette=50,
        )],
    )
    p = periode_service.valider_periode(p.id)  # période n'est plus OUVERTE

    deps = enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)

    assert deps.nombre_heures == 3
    assert deps.nombre_elements_remuneration == 3
    assert deps.nombre_retenues == 2
    assert enseignant_repository.obtenir_par_id(e.id) is None
    assert heures_repository.lister_par_enseignant_periode(e.id, p.id) == []
    assert remuneration_repository.lister_par_enseignant_periode(e.id, p.id) == []
    assert retenue_repository.lister_par_enseignant_periode(e.id, p.id) == []


# ---------------------------------------------------------------------
# 7. Rollback si une suppression échoue en cours de route
# ---------------------------------------------------------------------

def test_rollback_si_echec_en_cours_de_suppression(db_path, monkeypatch):
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10}, prime_ap_pp=1000)]
    )

    def _echec_simule(*args, **kwargs):
        raise sqlite3.OperationalError("panne simulée")

    # La suppression des retenues (dernière étape avant l'enseignant) échoue.
    monkeypatch.setattr(retenue_repository, "supprimer_par_enseignant", _echec_simule)

    with pytest.raises(EnseignantValidationError):
        enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)

    # Rien ne doit avoir été supprimé : ni les heures, ni les
    # rémunérations (pourtant traitées avant l'échec), ni l'enseignant.
    assert enseignant_repository.obtenir_par_id(e.id) is not None
    assert heures_repository.lister_par_enseignant_periode(e.id, p.id) != []
    assert remuneration_repository.lister_par_enseignant_periode(e.id, p.id) != []


# ---------------------------------------------------------------------
# 8 & 9. Refus si bulletin existant + bulletin intact après refus
# ---------------------------------------------------------------------

def test_refus_suppression_si_bulletin_existant(db_path):
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    p = periode_service.valider_periode(p.id)
    _inserer_bulletin_minimal(db_path, e, p.id)

    with pytest.raises(EnseignantValidationError, match="historique de paie"):
        enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)


def test_bulletin_intact_apres_refus_suppression(db_path):
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    p = periode_service.valider_periode(p.id)
    _inserer_bulletin_minimal(db_path, e, p.id)

    with pytest.raises(EnseignantValidationError):
        enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)

    # L'enseignant et son bulletin doivent être totalement intacts.
    assert enseignant_repository.obtenir_par_id(e.id) is not None
    with get_connection(db_path) as conn:
        bulletins = conn.execute(
            "SELECT * FROM bulletins_paie WHERE enseignant_id = ?", (e.id,)
        ).fetchall()
    assert len(bulletins) == 1


# ---------------------------------------------------------------------
# 10 & 11. Désactivation / réactivation toujours fonctionnelles
# ---------------------------------------------------------------------

def test_desactivation_toujours_fonctionnelle():
    e = _creer_enseignant()
    resultat = enseignant_service.desactiver_enseignant(e.id)
    assert resultat.actif is False
    assert enseignant_repository.obtenir_par_id(e.id) is not None  # toujours en base


def test_reactivation_toujours_fonctionnelle():
    e = _creer_enseignant()
    enseignant_service.desactiver_enseignant(e.id)
    resultat = enseignant_service.reactiver_enseignant(e.id)
    assert resultat.actif is True


# ---------------------------------------------------------------------
# 12. Confirmation explicite requise (garde-fou service, jamais contournable)
# ---------------------------------------------------------------------

def test_suppression_refusee_sans_confirmation():
    e = _creer_enseignant()
    with pytest.raises(EnseignantValidationError, match="confirmation"):
        enseignant_service.supprimer_enseignant_definitivement(e.id)  # confirmation=False par défaut
    assert enseignant_repository.obtenir_par_id(e.id) is not None


def test_suppression_refusee_confirmation_false_explicite():
    e = _creer_enseignant()
    with pytest.raises(EnseignantValidationError):
        enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=False)
    assert enseignant_repository.obtenir_par_id(e.id) is not None


def test_suppression_enseignant_inexistant():
    with pytest.raises(EnseignantValidationError):
        enseignant_service.supprimer_enseignant_definitivement(9999, confirmation=True)


# ---------------------------------------------------------------------
# 13. Conservation de l'audit
# ---------------------------------------------------------------------

def test_audit_conserve_apres_suppression_reussie(db_path):
    e = _creer_enseignant(nom="Konate", prenom="Yssouf")
    enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'suppression_definitive' AND entite_id = ?",
            (e.id,),
        ).fetchall()

    assert len(lignes) == 1
    assert "Konate" in lignes[0]["details"]
    assert "Yssouf" in lignes[0]["details"]
    assert "Succès" in lignes[0]["details"]
    # L'enseignant est supprimé, mais l'entrée d'audit n'est PAS supprimée en cascade.
    assert enseignant_repository.obtenir_par_id(e.id) is None


def test_audit_conserve_apres_refus_bulletin(db_path):
    e = _creer_enseignant(nom="Sanogo", prenom="Bakary")
    p = _creer_periode_ouverte()
    p = periode_service.valider_periode(p.id)
    _inserer_bulletin_minimal(db_path, e, p.id)

    with pytest.raises(EnseignantValidationError):
        enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'suppression_definitive' AND entite_id = ?",
            (e.id,),
        ).fetchall()

    assert len(lignes) == 1
    assert "Refusé" in lignes[0]["details"]


def test_dependances_enseignant_denombrement_correct():
    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id,
        [DonneesPaieEnseignant(
            enseignant_id=e.id,
            heures_par_semaine={1: 5, 2: 5},
            prime_ap_pp=100,
            retenue_amicale=50,
        )],
    )
    deps = enseignant_service.obtenir_dependances_enseignant(e.id)
    assert deps.nombre_heures == 2
    assert deps.nombre_elements_remuneration == 3  # les 3 types insérés (même à 0)
    assert deps.nombre_retenues == 2  # les 2 types insérés (même à 0)
    assert deps.nombre_bulletins == 0
    assert deps.a_des_donnees_de_paie is True
    assert deps.a_des_bulletins is False


# ---------------------------------------------------------------------
# Correction : un bulletin réellement généré par le module 07 est un
# fichier .docx sur disque, jamais une ligne dans bulletins_paie. La
# détection doit donc aussi porter sur le système de fichiers réel,
# sans quoi la protection CAS 3 ne se déclenche jamais en usage réel.
# ---------------------------------------------------------------------

def test_bulletin_reel_sur_disque_detecte_par_dependances(tmp_path, monkeypatch):
    from services import bulletin_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")

    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    bulletin_service.generer_bulletin_enseignant(p.id, e.id)  # vrai bulletin, fichier .docx

    deps = enseignant_service.obtenir_dependances_enseignant(e.id)
    assert deps.bulletins_generes_sur_disque is True
    assert deps.a_des_bulletins is True  # combine DB (toujours 0 ici) et disque


def test_suppression_refusee_pour_bulletin_reel_sur_disque(tmp_path, monkeypatch):
    from services import bulletin_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")

    e = _creer_enseignant()
    p = _creer_periode_ouverte()
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    bulletin_service.generer_bulletin_enseignant(p.id, e.id)

    with pytest.raises(EnseignantValidationError, match="historique de paie"):
        enseignant_service.supprimer_enseignant_definitivement(e.id, confirmation=True)

    assert enseignant_repository.obtenir_par_id(e.id) is not None
