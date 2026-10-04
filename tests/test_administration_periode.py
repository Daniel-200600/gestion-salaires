"""Rouvrir (invalider) ou supprimer une période validée ou clôturée — administrateur uniquement."""

import sqlite3

import pytest

import database.connection as database_connection
from models.enums import RoleUtilisateur, StatutPeriode
from services import (
    administration_periode_service as admin_periode,
    bulletin_service,
    enseignant_service,
    paie_service,
    periode_service,
    utilisateur_service,
)
from services import donnees_paie_service
from services.autorisation_service import AutorisationRefuseeError
from services.donnees_paie_service import DonneesPaieEnseignant

MDP = "Motdepasse-Solide-1"


@pytest.fixture(autouse=True)
def _base(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


@pytest.fixture
def admin(db_path):
    return utilisateur_service.creer_utilisateur("Admin", "Test", "admin", MDP, RoleUtilisateur.ADMIN, db_path=db_path)


@pytest.fixture
def periode_validee(db_path):
    e = enseignant_service.creer_enseignant("BELLA", "Christine", "F", "V", 1800)
    p = periode_service.ouvrir_periode(periode_service.creer_periode(mois=9, annee=2026).id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [DonneesPaieEnseignant(
        enseignant_id=e.id, heures_par_semaine={1: 10}, retenue_amicale=1000)])
    p = periode_service.valider_periode(p.id)
    bulletin_service.generer_bulletin_enseignant(p.id, e.id)  # crée l'instantané immuable
    return p, e


def _instantanes(db_path, periode_id):
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM bulletins_paie WHERE periode_id = ?", (periode_id,)).fetchone()[0]


def test_rouvrir_une_periode_validee_puis_la_revalider(admin, periode_validee, db_path):
    periode, enseignant = periode_validee
    assert _instantanes(db_path, periode.id) == 1
    rapport = admin_periode.rouvrir_periode(admin.id, periode.id, "septembre 2026", motif="heures erronées")
    assert rapport.sauvegarde.exists() and rapport.sauvegarde.name.startswith("avant_reouverture_")
    assert periode_service.obtenir_periode(periode.id).statut == StatutPeriode.OUVERTE
    assert _instantanes(db_path, periode.id) == 0

    # Correction des données puis nouvelle validation et nouveau bulletin.
    donnees_paie_service.enregistrer_donnees_paie_groupe(periode.id, [DonneesPaieEnseignant(
        enseignant_id=enseignant.id, heures_par_semaine={1: 12}, retenue_amicale=1000)])
    periode_service.valider_periode(periode.id)
    bulletin_service.generer_bulletin_enseignant(periode.id, enseignant.id)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT gain_heures FROM bulletins_paie").fetchone()[0] == 21600
        details = conn.execute("SELECT details FROM audit_log WHERE entite = 'periode_paie' "
                               "AND details LIKE '%rouverte%'").fetchone()[0]
    assert "motif : heures erronées" in details


def test_rouvrir_une_periode_cloturee(admin, periode_validee):
    periode, _ = periode_validee
    periode_service.cloturer_periode(periode.id)
    admin_periode.rouvrir_periode(admin.id, periode.id, "Septembre 2026")
    periode = periode_service.obtenir_periode(periode.id)
    assert periode.statut == StatutPeriode.OUVERTE and periode.date_cloture is None


def test_supprimer_une_periode_cloturee_et_ses_donnees(admin, periode_validee, db_path):
    periode, enseignant = periode_validee
    periode_service.cloturer_periode(periode.id)
    rapport = admin_periode.supprimer_periode(admin.id, periode.id, "Septembre 2026")
    assert (rapport.nb_saisies_heures, rapport.nb_instantanes_bulletins) == (1, 1)
    assert periode_service.lister_periodes() == []
    assert enseignant_service.obtenir_enseignant(enseignant.id).nom == "BELLA"  # fiches conservées
    with sqlite3.connect(db_path) as conn:  # les protections sont toujours en place
        noms = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert {"trg_periodes_paie_suppression_limitee", "trg_bulletins_paie_immuable_delete",
            "trg_periodes_paie_cloturee_figee", "trg_periodes_paie_transition_invalide"} <= noms
    nouvelle = periode_service.ouvrir_periode(periode_service.creer_periode(mois=9, annee=2026).id)
    with pytest.raises(Exception):  # une période ouverte reste non supprimable en direct
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM periodes_paie WHERE id = ?", (nouvelle.id,))


def test_confirmation_et_droits_exiges(admin, periode_validee, db_path):
    periode, _ = periode_validee
    with pytest.raises(admin_periode.AdministrationPeriodeError, match="Confirmation incorrecte"):
        admin_periode.supprimer_periode(admin.id, periode.id, "Septembre")
    gestionnaire = utilisateur_service.creer_utilisateur("G", "P", "gestion", MDP, RoleUtilisateur.GESTIONNAIRE_PAIE,
                                                       db_path=db_path)
    with pytest.raises(AutorisationRefuseeError):
        admin_periode.rouvrir_periode(gestionnaire.id, periode.id, "Septembre 2026")
    ouverte = periode_service.ouvrir_periode(periode_service.creer_periode(mois=10, annee=2026).id)
    with pytest.raises(admin_periode.AdministrationPeriodeError, match="validée ou clôturée"):
        admin_periode.rouvrir_periode(admin.id, ouverte.id, "Octobre 2026")
    assert periode_service.obtenir_periode(periode.id).statut == StatutPeriode.VALIDEE


def test_echec_en_cours_de_route_rien_ne_change(admin, periode_validee, db_path, monkeypatch):
    periode, _ = periode_validee

    def panne(conn, table, periode_id):
        raise RuntimeError("panne simulée")
    monkeypatch.setattr(admin_periode, "_compter", panne)
    with pytest.raises(RuntimeError):
        admin_periode.supprimer_periode(admin.id, periode.id, "Septembre 2026")
    assert periode_service.obtenir_periode(periode.id).statut == StatutPeriode.VALIDEE
    assert _instantanes(db_path, periode.id) == 1
    assert paie_service.calculer_paie_enseignant(periode.id, periode_validee[1].id).net_a_percevoir > 0


def test_sauvegarde_a_cote_de_la_base_utilisee(admin, periode_validee, db_path):
    rapport = admin_periode.rouvrir_periode(admin.id, periode_validee[0].id, "Septembre 2026")
    assert rapport.sauvegarde.parent == db_path.parent / "backups"  # jamais le dossier de l'application
