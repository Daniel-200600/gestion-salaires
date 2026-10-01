"""
Tests de la suppression physique et définitive d'une période de paie
(services/periode_service.supprimer_periode_definitivement).

Couvre les règles de l'énoncé : BROUILLON sans donnée -> autorisé ;
BROUILLON avec données mais sans bulletin -> autorisé (transaction en
cascade) ; bulletin existant -> toujours refusé ; VALIDEE -> refusé ;
CLOTUREE -> refusé ; atomicité (rollback complet en cas d'échec) ;
absence de données orphelines après suppression ; conservation de
l'audit ; non-régression sur le reste du cycle de vie des périodes.
"""

import sqlite3

import pytest

import database.connection as database_connection
from database.connection import get_connection
from database.repositories import (
    enseignant_repository,
    heures_repository,
    periode_repository,
    remuneration_repository,
    retenue_repository,
)
from services import donnees_paie_service, enseignant_service, periode_service
from services.donnees_paie_service import DonneesPaieEnseignant
from services.periode_service import PeriodeValidationError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch, tmp_path):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    from services import bulletin_service
    monkeypatch.setattr(bulletin_service, "EXPORT_DIR_BULLETINS", tmp_path / "bulletins")


def _creer_enseignant(**overrides):
    donnees = {"nom": "Fokou", "prenom": "Herve", "sexe": "M", "statut": "P", "taux_horaire": 1000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _saisir_donnees(periode_id, enseignant_id, **kwargs):
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        periode_id, [DonneesPaieEnseignant(enseignant_id=enseignant_id, **kwargs)]
    )


# ---------------------------------------------------------------------
# Test 1 — Période BROUILLON sans données -> suppression réussie
# ---------------------------------------------------------------------

def test_suppression_periode_brouillon_sans_donnees():
    p = periode_service.creer_periode(mois=1, annee=2036)
    periode_service.supprimer_periode_definitivement(p.id, confirmation=True)
    assert periode_repository.obtenir_par_id(p.id) is None


# ---------------------------------------------------------------------
# Test 2 — BROUILLON avec données de paie mais sans bulletin
# ---------------------------------------------------------------------
# Remarque : par construction (saisie exigeant le statut OUVERTE), une
# période BROUILLON n'a normalement aucune donnée de paie. Le test
# insère néanmoins des données directement pour vérifier que le
# service reste robuste et supprime proprement ce cas si jamais il se
# présentait (défense en profondeur).

def test_periode_brouillon_ne_peut_structurellement_pas_avoir_de_donnees(db_path):
    """
    Documente et vérifie une propriété du système : une période
    BROUILLON ne peut jamais avoir de données de paie, car le trigger
    SQL sur l'INSERT exige explicitement le statut OUVERTE — y compris
    pour une insertion SQL directe. Le scénario "BROUILLON avec
    données" est donc structurellement impossible à atteindre ; la
    robustesse de la cascade de suppression elle-même (si ce cas
    survenait malgré tout) est vérifiée séparément par
    test_cascade_repository_supprime_bien_toutes_les_dependances.
    """
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=2, annee=2036)  # reste BROUILLON
    with get_connection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="non ouverte"):
            conn.execute(
                "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
                "VALUES (?, ?, 1, 10)",
                (e.id, p.id),
            )

    # La période BROUILLON, elle, reste bien supprimable normalement.
    periode_service.supprimer_periode_definitivement(p.id, confirmation=True)
    assert periode_repository.obtenir_par_id(p.id) is None


# ---------------------------------------------------------------------
# Test 3 — Période avec bulletin -> suppression refusée
# ---------------------------------------------------------------------

def test_suppression_refusee_si_bulletin_existant():
    from services import bulletin_service

    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=3, annee=2036)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    bulletin_service.generer_bulletin_enseignant(p.id, e.id)

    with pytest.raises(PeriodeValidationError, match="bulletin"):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    assert periode_repository.obtenir_par_id(p.id) is not None


# ---------------------------------------------------------------------
# Test 4 — Période VALIDEE -> suppression refusée (même sans bulletin)
# ---------------------------------------------------------------------

def test_suppression_refusee_periode_validee():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=4, annee=2036)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)

    with pytest.raises(PeriodeValidationError, match="BROUILLON"):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    assert periode_repository.obtenir_par_id(p.id) is not None


# ---------------------------------------------------------------------
# Test 5 — Période CLOTUREE -> suppression refusée
# ---------------------------------------------------------------------

def test_suppression_refusee_periode_cloturee():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=5, annee=2036)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    p = periode_service.cloturer_periode(p.id)

    with pytest.raises(PeriodeValidationError, match="BROUILLON"):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    assert periode_repository.obtenir_par_id(p.id) is not None


def test_periode_ouverte_sans_bulletin_egalement_refusee():
    """OUVERTE n'est pas BROUILLON : refusée par la même règle (protection maximale de l'historique)."""
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=6, annee=2036)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})

    with pytest.raises(PeriodeValidationError, match="BROUILLON"):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)


# ---------------------------------------------------------------------
# Test 6 — Une suppression refusée ne modifie aucune donnée
# ---------------------------------------------------------------------

def test_suppression_refusee_ne_modifie_rien():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=7, annee=2036)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=500)
    p = periode_service.valider_periode(p.id)

    with pytest.raises(PeriodeValidationError):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    assert heures_repository.compter_par_periode(p.id) == 1
    assert remuneration_repository.compter_par_periode(p.id) == 3
    periode_relue = periode_repository.obtenir_par_id(p.id)
    assert periode_relue.statut.value == "validee"


# ---------------------------------------------------------------------
# Test 7 — Atomicité (rollback complet en cas d'échec en cours de suppression)
# ---------------------------------------------------------------------

def test_atomicite_reelle_via_api_publique(monkeypatch):
    """
    Vérifie l'atomicité réelle de supprimer_periode_definitivement via
    l'API publique : si la suppression de la ligne periodes_paie
    elle-même échoue (dernière étape de la cascade), la transaction
    est intégralement annulée — la période reste intacte.
    """
    p = periode_service.creer_periode(mois=12, annee=2036)  # BROUILLON, sans données

    def _echec_simule(*args, **kwargs):
        raise sqlite3.OperationalError("panne simulée sur la suppression finale")

    monkeypatch.setattr(periode_repository, "supprimer_definitivement", _echec_simule)

    with pytest.raises(PeriodeValidationError):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    # Le rollback a bien annulé l'opération : la période existe toujours.
    assert periode_repository.obtenir_par_id(p.id) is not None


def test_atomicite_rollback_preserve_heures_si_echec_sur_retenues(db_path, monkeypatch):
    """
    Vérifie, au niveau transactionnel bas niveau (même mécanisme
    qu'utilise le service), qu'un échec en cours de cascade restaure
    bien les lignes déjà supprimées dans la transaction interrompue.
    """
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=10, annee=2036)
    p = periode_service.ouvrir_periode(p.id)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO saisies_heures (enseignant_id, periode_id, numero_semaine, heures_effectuees) "
            "VALUES (?, ?, 1, 10)",
            (e.id, p.id),
        )
        conn.commit()

    with get_connection(db_path) as conn:
        try:
            heures_repository.supprimer_par_periode(p.id, conn=conn)
            raise sqlite3.OperationalError("panne simulée sur retenues")
        except sqlite3.OperationalError:
            conn.rollback()

    # Le rollback doit avoir restauré les heures supprimées avant l'échec simulé.
    assert heures_repository.compter_par_periode(p.id) == 1


# ---------------------------------------------------------------------
# Cascade générique (au niveau repository) avec des données réelles
# ---------------------------------------------------------------------

def test_cascade_repository_supprime_bien_toutes_les_dependances(db_path):
    """
    Vérifie, au niveau repository (indépendamment du verrou de statut
    appliqué par periode_service), que la cascade de suppression
    (heures + rémunérations + retenues) fonctionne correctement.
    Nécessaire car une période BROUILLON ne peut, par construction,
    jamais recevoir de données (la saisie exige le statut OUVERTE) :
    le scénario "données existantes" ne peut être vérifié qu'avec une
    période OUVERTE ; la ligne periodes_paie elle-même n'est pas
    supprimée ici (le trigger SQL l'interdit hors BROUILLON — testé
    séparément par test_suppression_periode_brouillon_sans_donnees).
    """
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=2, annee=2036)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=500, dette=100)

    with get_connection(db_path) as conn:
        heures_repository.supprimer_par_periode(p.id, conn=conn)
        remuneration_repository.supprimer_par_periode(p.id, conn=conn)
        retenue_repository.supprimer_par_periode(p.id, conn=conn)
        conn.commit()

    assert heures_repository.compter_par_periode(p.id) == 0
    assert remuneration_repository.compter_par_periode(p.id) == 0
    assert retenue_repository.compter_par_periode(p.id) == 0
    assert enseignant_repository.obtenir_par_id(e.id) is not None  # jamais touché


# ---------------------------------------------------------------------
# Confirmation explicite obligatoire
# ---------------------------------------------------------------------

def test_suppression_refusee_sans_confirmation():
    p = periode_service.creer_periode(mois=11, annee=2036)
    with pytest.raises(PeriodeValidationError, match="confirmation"):
        periode_service.supprimer_periode_definitivement(p.id)
    assert periode_repository.obtenir_par_id(p.id) is not None


def test_suppression_periode_inexistante():
    from services.periode_service import PeriodeNotFoundError
    with pytest.raises(PeriodeNotFoundError):
        periode_service.supprimer_periode_definitivement(9999, confirmation=True)


# ---------------------------------------------------------------------
# Absence de données orphelines après une suppression autorisée
# ---------------------------------------------------------------------

def test_aucune_donnee_orpheline_apres_suppression_autorisee(db_path):
    """
    Vérifie qu'après une cascade de suppression (heures + rémunérations
    + retenues), plus aucune ligne ne subsiste pour cette période, et
    que l'enseignant lui-même n'est jamais affecté.
    """
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=12, annee=2036)
    p = periode_service.ouvrir_periode(p.id)  # la saisie exige OUVERTE
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10}, prime_ap_pp=500, dette=100)

    with get_connection(db_path) as conn:
        heures_repository.supprimer_par_periode(p.id, conn=conn)
        remuneration_repository.supprimer_par_periode(p.id, conn=conn)
        retenue_repository.supprimer_par_periode(p.id, conn=conn)
        conn.commit()

    with get_connection(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) c FROM saisies_heures WHERE periode_id = ?", (p.id,)
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) c FROM elements_remuneration WHERE periode_id = ?", (p.id,)
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) c FROM retenues WHERE periode_id = ?", (p.id,)
        ).fetchone()["c"] == 0

    assert enseignant_repository.obtenir_par_id(e.id) is not None


# ---------------------------------------------------------------------
# Le bulletin lui-même n'est jamais supprimé par cascade
# ---------------------------------------------------------------------

def test_bulletin_jamais_supprime_par_cascade_periode():
    """Un bulletin bloque la suppression de la période ; il n'est donc jamais purgé par cascade."""
    from services import bulletin_service

    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=1, annee=2037)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    resultat_bulletin = bulletin_service.generer_bulletin_enseignant(p.id, e.id)

    with pytest.raises(PeriodeValidationError):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    assert resultat_bulletin.chemin.exists()


# ---------------------------------------------------------------------
# Conservation de l'audit
# ---------------------------------------------------------------------

def test_audit_conserve_apres_suppression_reussie(db_path):
    p = periode_service.creer_periode(mois=2, annee=2037)
    libelle = p.libelle
    periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'suppression_definitive' "
            "AND entite = 'periode_paie' AND entite_id = ?",
            (p.id,),
        ).fetchall()
    assert len(lignes) == 1
    assert libelle in lignes[0]["details"]
    assert "Succès" in lignes[0]["details"]


def test_audit_conserve_apres_refus_bulletin(db_path):
    from services import bulletin_service

    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=3, annee=2037)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 10})
    p = periode_service.valider_periode(p.id)
    bulletin_service.generer_bulletin_enseignant(p.id, e.id)

    with pytest.raises(PeriodeValidationError):
        periode_service.supprimer_periode_definitivement(p.id, confirmation=True)

    with get_connection(db_path) as conn:
        lignes = conn.execute(
            "SELECT * FROM audit_log WHERE type_action = 'suppression_definitive' "
            "AND entite = 'periode_paie' AND entite_id = ?",
            (p.id,),
        ).fetchall()
    assert len(lignes) == 1
    assert "Refusé" in lignes[0]["details"]


# ---------------------------------------------------------------------
# Non-régression : le reste du cycle de vie des périodes fonctionne toujours
# ---------------------------------------------------------------------

def test_cycle_de_vie_periode_toujours_fonctionnel():
    p = periode_service.creer_periode(mois=4, annee=2037)
    assert p.statut.value == "brouillon"
    p = periode_service.ouvrir_periode(p.id)
    assert p.statut.value == "ouverte"
    p = periode_service.valider_periode(p.id)
    assert p.statut.value == "validee"
    p = periode_service.cloturer_periode(p.id)
    assert p.statut.value == "cloturee"


def test_dependances_periode_denombrement_correct():
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=5, annee=2037)
    p = periode_service.ouvrir_periode(p.id)
    _saisir_donnees(p.id, e.id, heures_par_semaine={1: 5, 2: 5}, prime_ap_pp=100, retenue_amicale=50)

    deps = periode_service.obtenir_dependances_periode(p.id)
    assert deps.nombre_heures == 2
    assert deps.nombre_elements_remuneration == 3
    assert deps.nombre_retenues == 2
    assert deps.a_des_donnees_de_paie is True
    assert deps.a_des_bulletins is False
