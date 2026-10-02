"""
Compléter les fiches d'enseignants en une fois, export de la liste à
compléter puis réimport, et doublons probables à l'import.
"""

import math

import pandas as pd
import pytest
from openpyxl import load_workbook

from exports.import_template_export import REMPLISSAGE_A_COMPLETER, generer_classeur_fiches_a_completer
from models.enseignant import Enseignant
from models.enums import Sexe, StatutEnseignant, StrategieDoublon, TypeImport
from services import enseignant_service, import_service
from services.enseignant_service import ComplementFiche, completer_fiches_en_lot
from database.repositories import enseignant_repository
from utils.validators import EnseignantValidationError


def _fiche(db_path, nom, prenom="", sexe=None, statut=None, taux=None) -> int:
    return enseignant_repository.creer(
        Enseignant(nom=nom, prenom=prenom, sexe=sexe, statut=statut, taux_horaire=taux), db_path=db_path
    )


def _par_nom(db_path):
    return {e.nom: e for e in enseignant_service.lister_enseignants(db_path=db_path)}


def _preparer_excel(tmp_path, df, db_path, strategie=StrategieDoublon.REFUSER, ignorer=False):
    chemin = tmp_path / "liste.xlsx"
    df.to_excel(chemin, index=False)
    contenu = import_service.lire_fichier(chemin, "liste.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    return import_service.preparer_import_enseignants(
        analyse, contenu.feuilles[analyse.feuille_choisie], strategie, db_path=db_path,
        ignorer_doublons_probables=ignorer,
    )


# --- Compléter en une fois ------------------------------------------------

def test_completer_plusieurs_fiches_en_une_fois(db_path):
    a = _fiche(db_path, "ATEBA", "Paul", sexe=Sexe.HOMME)
    b = _fiche(db_path, "BELLA", "Christine")
    resultat = completer_fiches_en_lot([
        ComplementFiche(a, statut="P", taux_horaire=1800.0),           # devient complète
        ComplementFiche(b, sexe="F", statut=None, taux_horaire=math.nan),  # reste à compléter
    ], db_path=db_path)

    assert (resultat.nb_fiches_modifiees, resultat.nb_fiches_completees) == (2, 1)
    fiches = _par_nom(db_path)
    assert fiches["ATEBA"].est_complet and fiches["ATEBA"].taux_horaire == 1800
    assert fiches["BELLA"].sexe == Sexe.FEMME and fiches["BELLA"].champs_manquants == ["statut", "taux horaire"]
    assert [e.nom for e in enseignant_service.lister_enseignants_payables(db_path=db_path)] == ["ATEBA"]


def test_completer_en_lot_n_efface_rien_et_ignore_les_lignes_inchangees(db_path):
    a = _fiche(db_path, "OWONA", "Luc", statut=StatutEnseignant.VACATAIRE, taux=1500)
    resultat = completer_fiches_en_lot([ComplementFiche(a)], db_path=db_path)
    assert resultat.nb_fiches_modifiees == 0
    owona = _par_nom(db_path)["OWONA"]
    assert owona.statut == StatutEnseignant.VACATAIRE and owona.taux_horaire == 1500


def test_completer_en_lot_tout_ou_rien(db_path):
    a = _fiche(db_path, "ATEBA", "Paul")
    b = _fiche(db_path, "BELLA", "Christine")
    with pytest.raises(EnseignantValidationError, match="BELLA Christine"):
        completer_fiches_en_lot([
            ComplementFiche(a, sexe="M", statut="P", taux_horaire=2000),
            ComplementFiche(b, taux_horaire=-5),
        ], db_path=db_path)
    assert _par_nom(db_path)["ATEBA"].sexe is None  # rien n'a été écrit


# --- Export de la liste à compléter, puis réimport --------------------------

def test_export_puis_reimport_complete_les_fiches(tmp_path, db_path):
    _fiche(db_path, "ATEBA", "Paul", sexe=Sexe.HOMME)
    _fiche(db_path, "NGONO", "Marie", statut=StatutEnseignant.PERMANENT, taux=2000)
    chemin = tmp_path / "a_completer.xlsx"
    generer_classeur_fiches_a_completer(enseignant_service.lister_enseignants_a_completer(db_path=db_path)).save(chemin)

    feuille = load_workbook(chemin)["Donnees"]
    assert [c.value for c in feuille[1]][:5] == ["Nom", "Prenom", "Sexe", "Statut", "Taux_Horaire"]
    assert [c.value for c in feuille[2]][:5] == ["ATEBA", "Paul", "M", None, None]
    assert feuille["D2"].fill.fgColor.rgb.endswith(REMPLISSAGE_A_COMPLETER.fgColor.rgb[-6:])
    assert not feuille["C2"].fill.fgColor.rgb.endswith("FFF2CC")

    # Le secrétariat remplit une partie des cases jaunes.
    df = pd.read_excel(chemin)
    df.loc[df["Nom"] == "ATEBA", ["Statut", "Taux_Horaire"]] = ["V", 1500]
    df.loc[df["Nom"] == "NGONO", "Sexe"] = "F"
    rapport = _preparer_excel(tmp_path, df, db_path, StrategieDoublon.METTRE_A_JOUR)
    assert rapport.nb_mises_a_jour == 2 and rapport.nb_creations == 0
    import_service.executer_import_enseignants(rapport, "liste.xlsx", db_path=db_path)

    fiches = _par_nom(db_path)
    assert fiches["ATEBA"].est_complet and fiches["ATEBA"].taux_horaire == 1500
    assert fiches["NGONO"].est_complet and fiches["NGONO"].statut == StatutEnseignant.PERMANENT
    assert not enseignant_service.lister_enseignants_a_completer(db_path=db_path)


# --- Doublons -----------------------------------------------------------------

def test_meme_nom_dans_un_autre_ordre_reconnu(tmp_path, db_path):
    _fiche(db_path, "MBARGA", "Élise", sexe=Sexe.FEMME)
    df = pd.DataFrame({"Noms et prénoms": ["Elise Mbarga"], "Statut": ["Vacataire"]})

    refuse = _preparer_excel(tmp_path, df, db_path)
    assert refuse.nb_rejetees == 1 and refuse.nb_creations == 0

    maj = _preparer_excel(tmp_path, df, db_path, StrategieDoublon.METTRE_A_JOUR)
    import_service.executer_import_enseignants(maj, "liste.xlsx", db_path=db_path)
    mbarga = _par_nom(db_path)["MBARGA"]
    assert (mbarga.prenom, mbarga.sexe, mbarga.statut) == ("Élise", Sexe.FEMME, StatutEnseignant.VACATAIRE)


@pytest.mark.parametrize("nom, prenom", [("NGONO", "Marie"), ("NGONO", "Marie Clair"), ("NGONNO", "Marie Claire")])
def test_doublon_probable_signale(tmp_path, db_path, nom, prenom):
    _fiche(db_path, "NGONO", "Marie Claire")
    df = pd.DataFrame({"Nom": [nom, "ESSOMBA"], "Prénom": [prenom, "Jean"]})

    rapport = _preparer_excel(tmp_path, df, db_path)
    assert rapport.nb_creations == 2 and rapport.nb_doublons_probables == 1
    assert "NGONO Marie Claire" in rapport.lignes[0].doublon_probable
    assert rapport.lignes[1].doublon_probable is None

    ecarte = _preparer_excel(tmp_path, df, db_path, ignorer=True)
    assert ecarte.nb_creations == 1 and ecarte.nb_ignorees == 1


def test_doublon_probable_dans_le_fichier(tmp_path, db_path):
    df = pd.DataFrame({"Nom": ["ATEBA", "ATEBA", "ATANGANA"], "Prénom": ["Paul", "Paul Henri", "Pierre"]})
    rapport = _preparer_excel(tmp_path, df, db_path)
    assert [l.doublon_probable is not None for l in rapport.lignes] == [False, True, False]
    assert "ligne 1" in rapport.lignes[1].doublon_probable


def test_noms_differents_non_signales(tmp_path, db_path):
    _fiche(db_path, "ATANGANA", "Paul")
    df = pd.DataFrame({"Nom": ["ATANGANA", "ESSOMBA"], "Prénom": ["Pierre", "Paul"]})
    assert _preparer_excel(tmp_path, df, db_path).nb_doublons_probables == 0
