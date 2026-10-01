"""
Tests de services/import_service.py (module 15).
"""

import pytest
import pandas as pd

import database.connection as database_connection
from database.connection import get_connection
from models.enums import RoleUtilisateur, StrategieDoublon, TypeImport
from services import (
    controle_paie_service,
    enseignant_service,
    import_service,
    periode_service,
    permission_service,
)
from services.import_service import ImportServiceError


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


def _creer_enseignant(**overrides):
    donnees = {"nom": "Kamgang", "prenom": "Jean", "sexe": "M", "statut": "P", "taux_horaire": 2000}
    donnees.update(overrides)
    return enseignant_service.creer_enseignant(**donnees)


def _fichier_xlsx(tmp_path, df: pd.DataFrame, nom="import.xlsx"):
    chemin = tmp_path / nom
    df.to_excel(chemin, index=False)
    return chemin


def _fichier_csv(tmp_path, contenu: str, nom="import.csv"):
    chemin = tmp_path / nom
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# ---------------------------------------------------------------------
# Fichiers — chargement et sécurité (section A)
# ---------------------------------------------------------------------

def test_lecture_fichier_excel_valide(tmp_path):
    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["B"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [1000]})
    chemin = _fichier_xlsx(tmp_path, df)
    contenu = import_service.lire_fichier(chemin, "test.xlsx")
    assert contenu.noms_feuilles == ["Sheet1"]


def test_lecture_fichier_csv_valide(tmp_path):
    chemin = _fichier_csv(tmp_path, "Nom,Prenom,Sexe,Statut,taux_horaire\nA,B,M,P,1000\n")
    contenu = import_service.lire_fichier(chemin, "test.csv")
    assert "csv" in contenu.noms_feuilles


def test_fichier_vide_refuse(tmp_path):
    chemin = tmp_path / "vide.xlsx"
    chemin.touch()
    with pytest.raises(ImportServiceError, match="vide"):
        import_service.lire_fichier(chemin, "vide.xlsx")


def test_fichier_corrompu_refuse(tmp_path):
    chemin = tmp_path / "corrompu.xlsx"
    chemin.write_bytes(b"CECI N'EST PAS UN FICHIER EXCEL VALIDE" * 10)
    with pytest.raises(ImportServiceError):
        import_service.lire_fichier(chemin, "corrompu.xlsx")


def test_extension_interdite_refusee(tmp_path):
    chemin = tmp_path / "fichier.txt"
    chemin.write_text("contenu")
    with pytest.raises(ImportServiceError, match="Extension"):
        import_service.lire_fichier(chemin, "fichier.txt")


def test_fichier_inexistant_refuse(tmp_path):
    with pytest.raises(ImportServiceError, match="introuvable"):
        import_service.lire_fichier(tmp_path / "absent.xlsx", "absent.xlsx")


def test_feuille_vide_refusee(tmp_path):
    df_vide = pd.DataFrame()
    chemin = tmp_path / "vide_feuille.xlsx"
    with pd.ExcelWriter(chemin) as writer:
        df_vide.to_excel(writer, sheet_name="VideFeuille", index=False)
    with pytest.raises(ImportServiceError):
        import_service.lire_fichier(chemin, "vide_feuille.xlsx")


def test_plusieurs_feuilles_detectees(tmp_path):
    chemin = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(chemin) as writer:
        pd.DataFrame({"Nom": ["A"]}).to_excel(writer, sheet_name="Feuille1", index=False)
        pd.DataFrame({"Nom": ["B"]}).to_excel(writer, sheet_name="Feuille2", index=False)
    contenu = import_service.lire_fichier(chemin, "multi.xlsx")
    assert set(contenu.noms_feuilles) == {"Feuille1", "Feuille2"}


# ---------------------------------------------------------------------
# Colonnes — normalisation (section 7)
# ---------------------------------------------------------------------

def test_normalisation_colonnes_variantes():
    resultat = import_service.normaliser_colonnes(
        ["NOM", "Prénom", "sexe", "Statut enseignant", "Taux Horaire"], TypeImport.ENSEIGNANTS
    )
    assert resultat.correspondance["NOM"] == "nom"
    assert resultat.correspondance["Prénom"] == "prenom"
    assert resultat.correspondance["Statut enseignant"] == "statut"
    assert resultat.correspondance["Taux Horaire"] == "taux_horaire"
    assert resultat.colonnes_inconnues == []


def test_normalisation_colonnes_inconnues_signalees():
    resultat = import_service.normaliser_colonnes(["Nom", "Colonne Mystere"], TypeImport.ENSEIGNANTS)
    assert "Colonne Mystere" in resultat.colonnes_inconnues
    assert "Colonne Mystere" not in resultat.correspondance


def test_normalisation_colonnes_ambigues_non_mappees():
    resultat = import_service.normaliser_colonnes(["Commentaire"], TypeImport.ENSEIGNANTS)
    assert resultat.colonnes_inconnues == ["Commentaire"]


# ---------------------------------------------------------------------
# Analyse / prévisualisation
# ---------------------------------------------------------------------

def test_analyse_fichier_apercu(tmp_path):
    df = pd.DataFrame({
        "Nom": ["A", "B"], "Prenom": ["X", "Y"], "Sexe": ["M", "F"], "Statut": ["P", "V"],
        "taux_horaire": [1000, 2000],
    })
    chemin = _fichier_xlsx(tmp_path, df)
    contenu = import_service.lire_fichier(chemin, "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    assert analyse.nombre_lignes == 2
    assert len(analyse.apercu) == 2


# ---------------------------------------------------------------------
# Données — validation technique et métier (section 11/12)
# ---------------------------------------------------------------------

def test_donnees_valides_toutes_creees(tmp_path):
    df = pd.DataFrame({
        "Nom": ["A", "B"], "Prenom": ["X", "Y"], "Sexe": ["M", "F"], "Statut": ["P", "V"],
        "taux_horaire": [1000, 2000],
    })
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    assert rapport.nb_creations == 2
    assert rapport.nb_erreurs == 0


def test_type_invalide_taux_horaire_rejete(tmp_path):
    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": ["abc"]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    assert rapport.nb_rejetees == 1
    assert rapport.nb_erreurs == 1


def test_champ_obligatoire_manquant_rejete(tmp_path):
    df = pd.DataFrame({"Nom": [""], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [1000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    assert rapport.nb_rejetees == 1


def test_valeur_negative_taux_rejetee(tmp_path):
    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [-500]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    assert rapport.nb_rejetees == 1


def test_statut_invalide_rejete(tmp_path):
    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["Z"], "taux_horaire": [1000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    assert rapport.nb_rejetees == 1


# ---------------------------------------------------------------------
# Doublons (section 13/14)
# ---------------------------------------------------------------------

def test_doublon_interne_au_fichier_ignore(tmp_path):
    df = pd.DataFrame({
        "Nom": ["A", "A"], "Prenom": ["X", "X"], "Sexe": ["M", "M"], "Statut": ["P", "P"],
        "taux_horaire": [1000, 1000],
    })
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    assert rapport.nb_creations == 1
    assert rapport.nb_ignorees == 1


def test_doublon_avec_base_strategie_refuser(tmp_path):
    _creer_enseignant(nom="Kamgang", prenom="Jean")
    df = pd.DataFrame({"Nom": ["Kamgang"], "Prenom": ["Jean"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [3000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(
        analyse, contenu.feuilles[analyse.feuille_choisie], strategie_doublon=StrategieDoublon.REFUSER
    )
    assert rapport.nb_rejetees == 1


def test_doublon_avec_base_strategie_ignorer(tmp_path):
    _creer_enseignant(nom="Kamgang", prenom="Jean")
    df = pd.DataFrame({"Nom": ["Kamgang"], "Prenom": ["Jean"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [3000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(
        analyse, contenu.feuilles[analyse.feuille_choisie], strategie_doublon=StrategieDoublon.IGNORER
    )
    assert rapport.nb_ignorees == 1


def test_doublon_avec_base_strategie_mettre_a_jour(tmp_path):
    e = _creer_enseignant(nom="Kamgang", prenom="Jean", taux_horaire=1000)
    df = pd.DataFrame({"Nom": ["Kamgang"], "Prenom": ["Jean"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [3000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(
        analyse, contenu.feuilles[analyse.feuille_choisie], strategie_doublon=StrategieDoublon.METTRE_A_JOUR
    )
    assert rapport.nb_mises_a_jour == 1
    assert rapport.lignes[0].cible_id == e.id


# ---------------------------------------------------------------------
# Base — enseignant/période connus ou non
# ---------------------------------------------------------------------

def test_import_heures_enseignant_inexistant_rejete(tmp_path):
    p = periode_service.creer_periode(mois=1, annee=2080)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    df = pd.DataFrame({"Nom": ["Inconnu"], "Prenom": ["X"], "Semaine_1": [10]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "heures.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.HEURES)
    rapport = import_service.preparer_import_heures(analyse, contenu.feuilles[analyse.feuille_choisie], p.id)
    assert rapport.nb_rejetees == 1


@pytest.mark.parametrize("statut_cible", ["brouillon", "validee", "cloturee"])
def test_import_heures_periode_non_ouverte_refusee(tmp_path, statut_cible):
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=2, annee=2080)
    if statut_cible != "brouillon":
        controle_paie_service.ouvrir_periode_avec_audit(p.id)
        from services import donnees_paie_service
        from services.donnees_paie_service import DonneesPaieEnseignant
        donnees_paie_service.enregistrer_donnees_paie_groupe(
            p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 5})]
        )
        if statut_cible in ("validee", "cloturee"):
            controle_paie_service.valider_periode_avec_controle(p.id, confirmation=True)
        if statut_cible == "cloturee":
            controle_paie_service.cloturer_periode_avec_controle(p.id, confirmation=True)

    df = pd.DataFrame({"Nom": [e.nom], "Prenom": [e.prenom], "Semaine_1": [10]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "heures.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.HEURES)
    rapport = import_service.preparer_import_heures(analyse, contenu.feuilles[analyse.feuille_choisie], p.id)
    assert rapport.nb_rejetees == 1
    assert statut_cible.upper() in rapport.toutes_anomalies[0].message


def test_import_heures_periode_ouverte_autorisee(tmp_path):
    e = _creer_enseignant()
    p = periode_service.creer_periode(mois=3, annee=2080)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    df = pd.DataFrame({"Nom": [e.nom], "Prenom": [e.prenom], "Semaine_1": [10]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "heures.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.HEURES)
    rapport = import_service.preparer_import_heures(analyse, contenu.feuilles[analyse.feuille_choisie], p.id)
    assert rapport.nb_mises_a_jour == 1


def test_import_periode_inexistante_leve():
    with pytest.raises(ImportServiceError):
        import_service.preparer_import_heures(
            import_service.RapportAnalyse("x", "f", ["f"], 0, [], {}, []), pd.DataFrame(), 999999
        )


# ---------------------------------------------------------------------
# Transaction (section 16)
# ---------------------------------------------------------------------

def test_import_reussi_persiste_en_base(tmp_path, db_path):
    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [1000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])

    journal = import_service.executer_import_enseignants(rapport, "test.xlsx", utilisateur="admin")
    assert journal.statut.value == "termine"

    tous = enseignant_service.lister_enseignants(inclure_inactifs=True)
    assert len(tous) == 1


def test_import_journal_enregistre_avec_anomalies(tmp_path):
    df = pd.DataFrame({
        "Nom": ["A", ""], "Prenom": ["X", "Y"], "Sexe": ["M", "M"], "Statut": ["P", "P"],
        "taux_horaire": [1000, 1000],
    })
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])

    journal = import_service.executer_import_enseignants(rapport, "test.xlsx", utilisateur="admin")
    from database.repositories import import_repository
    anomalies = import_repository.lister_anomalies(journal.id)
    assert len(anomalies) == 1


# ---------------------------------------------------------------------
# Dry Run — jamais de modification de la base
# ---------------------------------------------------------------------

def test_dry_run_ne_modifie_jamais_la_base(tmp_path):
    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [1000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)

    import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])

    assert enseignant_service.lister_enseignants(inclure_inactifs=True) == []


# ---------------------------------------------------------------------
# Permissions (section 20)
# ---------------------------------------------------------------------

def test_permission_import_donnees_admin_gestionnaire_uniquement():
    assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission_service.IMPORT_DONNEES)
    assert permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission_service.IMPORT_DONNEES)
    assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission_service.IMPORT_DONNEES)


# ---------------------------------------------------------------------
# Audit (section 21)
# ---------------------------------------------------------------------

def test_audit_import_reussi(tmp_path, db_path):
    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [1000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    import_service.executer_import_enseignants(rapport, "test.xlsx", utilisateur="admin")

    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'import_donnees'").fetchall()
    assert len(lignes) == 1
    assert lignes[0]["utilisateur"] == "admin"


# ---------------------------------------------------------------------
# Non-régression du cas de référence, à travers un import
# ---------------------------------------------------------------------

def test_cas_reference_apres_import(tmp_path):
    df = pd.DataFrame({"Nom": ["Kamgang"], "Prenom": ["Jean Paul"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [2000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    import_service.executer_import_enseignants(rapport, "test.xlsx", utilisateur="admin")

    e = enseignant_service.lister_enseignants()[0]
    p = periode_service.creer_periode(mois=4, annee=2080)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)

    from services import donnees_paie_service
    from services.donnees_paie_service import DonneesPaieEnseignant
    donnees_paie_service.enregistrer_donnees_paie_groupe(p.id, [
        DonneesPaieEnseignant(
            enseignant_id=e.id, heures_par_semaine={1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            prime_ap_pp=20000, surveillance_secretariat=10000, indemnite_suggestion_admin=5000,
            retenue_amicale=5000, dette=10000,
        ),
    ])
    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir == 208250


# ---------------------------------------------------------------------
# Rollback formel (section 16/34) — aucune donnée partielle après échec
# ---------------------------------------------------------------------

def test_rollback_complet_aucune_donnee_partielle(tmp_path):
    from unittest.mock import patch
    from database.repositories import enseignant_repository

    df = pd.DataFrame({
        "Nom": ["Alpha", "Beta", "Gamma"], "Prenom": ["A", "B", "C"],
        "Sexe": ["M", "M", "M"], "Statut": ["P", "P", "P"], "taux_horaire": [1000, 1000, 1000],
    })
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "rollback.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])
    assert rapport.nb_creations == 3

    appel_compteur = {"n": 0}
    original_creer = enseignant_repository.creer

    def creer_avec_echec(*args, **kwargs):
        appel_compteur["n"] += 1
        if appel_compteur["n"] == 2:
            raise RuntimeError("Panne simulée en cours de transaction")
        return original_creer(*args, **kwargs)

    with patch.object(enseignant_repository, "creer", side_effect=creer_avec_echec):
        journal = import_service.executer_import_enseignants(rapport, "rollback.xlsx", utilisateur="admin")

    assert journal.statut.value == "echec"
    assert enseignant_service.lister_enseignants(inclure_inactifs=True) == []


def test_import_echec_journalise_dans_audit(tmp_path, db_path):
    from unittest.mock import patch
    from database.repositories import enseignant_repository

    df = pd.DataFrame({"Nom": ["A"], "Prenom": ["X"], "Sexe": ["M"], "Statut": ["P"], "taux_horaire": [1000]})
    contenu = import_service.lire_fichier(_fichier_xlsx(tmp_path, df), "test.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(analyse, contenu.feuilles[analyse.feuille_choisie])

    with patch.object(enseignant_repository, "creer", side_effect=RuntimeError("panne")):
        import_service.executer_import_enseignants(rapport, "test.xlsx", utilisateur="admin")

    with get_connection(db_path) as conn:
        lignes = conn.execute("SELECT * FROM audit_log WHERE type_action = 'import_donnees_echec'").fetchall()
    assert len(lignes) == 1
