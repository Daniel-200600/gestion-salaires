"""
Licence d'utilisation : clés signées, liées à un ordinateur, et mode
démonstration en l'absence de licence valide.
"""

import json
import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from database.repositories import enseignant_repository
from models.enseignant import Enseignant
from models.enums import Sexe, StatutEnseignant, StrategieDoublon, TypeImport
from outils import generer_licence
from services import enseignant_service, import_service, licence_service, paie_service, periode_service
from services.paie_service import CalculPaieError
from utils.validators import EnseignantValidationError

CODE_POSTE = "ABCD-1234-EF56-7890"


@pytest.fixture
def cle_privee(tmp_path, monkeypatch):
    """Paire de clés de test, poste au code fixe, fichier de licence dans un dossier temporaire."""
    cle = Ed25519PrivateKey.generate()
    publique = cle.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(licence_service, "CLE_PUBLIQUE_B64", licence_service._b64_encoder(publique))
    monkeypatch.setattr(licence_service, "code_machine", lambda: CODE_POSTE)
    monkeypatch.setattr(licence_service, "chemin_licence", lambda: tmp_path / "donnees" / "licence.cle")
    return cle


def _cle(cle_privee, machine=CODE_POSTE, expire=None, etablissement="Collège Exemple"):
    charge = json.dumps({"n": "L-2026-001", "e": etablissement, "m": machine, "d": "2026-10-02",
                         "x": expire}).encode("utf-8")
    return licence_service.encoder_cle(charge, cle_privee.sign(charge))


# --- Clés --------------------------------------------------------------------

def test_cle_valide_lue(cle_privee):
    licence = licence_service.decoder_cle(_cle(cle_privee, expire="2027-09-30"))
    assert (licence.numero, licence.etablissement, licence.code_machine) == ("L-2026-001", "Collège Exemple", CODE_POSTE)
    assert licence.libelle_validite == "jusqu'au 30/09/2027"


def test_cle_copiee_avec_espaces_et_retours_a_la_ligne(cle_privee):
    cle = _cle(cle_privee)
    assert licence_service.decoder_cle(" " + cle[:40] + "\n" + cle[40:] + "\n").numero == "L-2026-001"


@pytest.mark.parametrize("alteration", ["charge", "signature", "prefixe", "tronquee"])
def test_cle_falsifiee_refusee(cle_privee, alteration):
    prefixe, charge, signature = _cle(cle_privee).split(".")
    if alteration == "charge":  # établissement modifié à la main
        donnees = json.loads(licence_service._b64_decoder(charge))
        donnees["e"] = "Autre établissement"
        charge = licence_service._b64_encoder(json.dumps(donnees).encode())
    elif alteration == "signature":
        signature = signature[:-2] + ("AA" if not signature.endswith("AA") else "BB")
    elif alteration == "prefixe":
        prefixe = "AUTRE1"
    else:
        signature = signature[:20]
    with pytest.raises(licence_service.LicenceInvalideError):
        licence_service.decoder_cle(".".join([prefixe, charge, signature]))


def test_cle_signee_par_une_autre_cle_refusee(cle_privee):
    with pytest.raises(licence_service.LicenceInvalideError, match="invalide"):
        licence_service.decoder_cle(_cle(Ed25519PrivateKey.generate()))


def test_activation_installe_la_licence_et_journalise(cle_privee, db_path):
    assert not licence_service.etat_licence().active
    licence_service.activer_licence(_cle(cle_privee), utilisateur="admin", db_path=db_path)
    etat = licence_service.etat_licence()
    assert etat.active and etat.licence.etablissement == "Collège Exemple"
    with sqlite3.connect(db_path) as conn:
        details = conn.execute("SELECT details FROM audit_log WHERE entite = 'licence'").fetchone()[0]
    assert "L-2026-001" in details


def test_cle_d_un_autre_ordinateur_refusee(cle_privee, db_path):
    with pytest.raises(licence_service.LicenceInvalideError, match="autre ordinateur"):
        licence_service.activer_licence(_cle(cle_privee, machine="FFFF-0000-FFFF-0000"), db_path=db_path)
    assert not licence_service.chemin_licence().exists()


def test_licence_expiree(cle_privee, db_path):
    hier = (date.today() - timedelta(days=1)).isoformat()
    with pytest.raises(licence_service.LicenceInvalideError, match="expiré"):
        licence_service.activer_licence(_cle(cle_privee, expire=hier), db_path=db_path)
    # Une licence installée devient inactive à son expiration.
    licence_service.activer_licence(_cle(cle_privee, expire=date.today().isoformat()), db_path=db_path)
    assert licence_service.etat_licence().active
    assert not licence_service.etat_licence(aujourdhui=date.today() + timedelta(days=1)).active


def test_fichier_de_licence_modifie_desactive(cle_privee, db_path):
    licence_service.activer_licence(_cle(cle_privee), db_path=db_path)
    licence_service.chemin_licence().write_text("GPAIE1.abc.def", encoding="utf-8")
    etat = licence_service.etat_licence()
    assert not etat.active and "invalide" in etat.motif


def test_code_machine_stable_et_lisible():
    code = licence_service.code_machine()
    assert code == licence_service.code_machine()
    assert len(code) == 19 and code.count("-") == 3


# --- Mode démonstration ---------------------------------------------------------

def _fiche(db_path, nom):
    return enseignant_repository.creer(Enseignant(
        nom=nom, prenom="Test", sexe=Sexe.HOMME, statut=StatutEnseignant.VACATAIRE, taux_horaire=1000,
    ), db_path=db_path)


@pytest.mark.mode_demo
def test_demo_limite_le_nombre_d_enseignants(cle_privee, db_path):
    for i in range(licence_service.LIMITE_DEMO_ENSEIGNANTS):
        enseignant_service.creer_enseignant(f"NOM{i}", "Prenom", "M", "V", 1000, db_path=db_path)
    with pytest.raises(EnseignantValidationError, match="Mode démonstration"):
        enseignant_service.creer_enseignant("SIXIEME", "Prenom", "M", "V", 1000, db_path=db_path)

    licence_service.activer_licence(_cle(cle_privee), db_path=db_path)
    enseignant_service.creer_enseignant("SIXIEME", "Prenom", "M", "V", 1000, db_path=db_path)
    assert licence_service.places_restantes_demo(db_path) is None


@pytest.mark.mode_demo
def test_demo_import_limite(cle_privee, tmp_path, db_path):
    _fiche(db_path, "DEJA")
    chemin = tmp_path / "liste.xlsx"
    noms = ["ATEBA", "BELLA", "ESSOMBA", "FOUDA", "MBARGA", "NGONO", "OWONA"]
    pd.DataFrame({"Nom": noms, "Prénom": ["Paul", "Christine", "Jean", "Agnès", "Élise", "Marie", "Luc"]}).to_excel(
        chemin, index=False)
    contenu = import_service.lire_fichier(chemin, "liste.xlsx")
    analyse = import_service.analyser_fichier(contenu, TypeImport.ENSEIGNANTS)
    rapport = import_service.preparer_import_enseignants(
        analyse, contenu.feuilles[analyse.feuille_choisie], StrategieDoublon.REFUSER, db_path=db_path
    )
    assert rapport.nb_creations == 4 and rapport.nb_rejetees == 3
    assert [l.action for l in rapport.lignes][-3:] == ["rejetee"] * 3
    assert all("Mode démonstration" in l.anomalies[-1].message for l in rapport.lignes[-3:])


@pytest.mark.mode_demo
def test_demo_calcul_bloque_seulement_pour_les_periodes_ouvertes(cle_privee, db_path):
    ids = [_fiche(db_path, f"NOM{i}") for i in range(licence_service.LIMITE_DEMO_ENSEIGNANTS + 1)]
    periode = periode_service.ouvrir_periode(periode_service.creer_periode(mois=5, annee=2031, db_path=db_path).id,
                                             db_path=db_path)
    with pytest.raises(CalculPaieError, match="Licence requise"):
        paie_service.calculer_paie_enseignant(periode.id, ids[0], db_path=db_path)

    # Une période validée reste consultable sans licence.
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE periodes_paie SET statut = 'validee' WHERE id = ?", (periode.id,))
    assert paie_service.calculer_paie_enseignant(periode.id, ids[0], db_path=db_path).net_a_percevoir == 0

    autre = periode_service.ouvrir_periode(periode_service.creer_periode(mois=6, annee=2031, db_path=db_path).id,
                                           db_path=db_path)
    licence_service.activer_licence(_cle(cle_privee), db_path=db_path)
    paie_service.calculer_paie_enseignant(autre.id, ids[0], db_path=db_path)


@pytest.mark.mode_demo
def test_demo_calcul_permis_dans_la_limite(cle_privee, db_path):
    enseignant_id = _fiche(db_path, "SEUL")
    periode = periode_service.ouvrir_periode(periode_service.creer_periode(mois=6, annee=2031, db_path=db_path).id,
                                             db_path=db_path)
    paie_service.calculer_paie_enseignant(periode.id, enseignant_id, db_path=db_path)


# --- Outil de l'auteur -------------------------------------------------------------

def test_outil_auteur_cree_des_cles_numerotees(tmp_path, monkeypatch, capsys):
    dossier = tmp_path / "licences"
    generer_licence.main(["--dossier", str(dossier), "init"])
    publique = capsys.readouterr().out.rsplit(": ", 1)[1].strip()
    monkeypatch.setattr(licence_service, "CLE_PUBLIQUE_B64", publique)

    premier = generer_licence.creer(dossier, "Collège  Exemple", "abcd1234ef567890", "2099-12-31")
    second = generer_licence.creer(dossier, "Lycée Autre", CODE_POSTE)
    licence = licence_service.decoder_cle(premier.read_text(encoding="utf-8"))
    assert (licence.numero, licence.etablissement, licence.code_machine) == (
        f"L-{date.today().year}-001", "Collège Exemple", CODE_POSTE)
    assert licence_service.decoder_cle(second.read_text(encoding="utf-8")).numero.endswith("-002")
    assert len((dossier / "registre_licences.csv").read_text(encoding="utf-8-sig").splitlines()) == 3

    with pytest.raises(SystemExit):  # la clé privée n'est jamais remplacée
        generer_licence.main(["--dossier", str(dossier), "init"])
    with pytest.raises(SystemExit):
        generer_licence.creer(dossier, "Collège", "ABC")  # code machine incomplet
