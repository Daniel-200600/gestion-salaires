"""
Tests de services/parametres_service.py (module 10) : lecture,
modification, persistance (y compris à travers un "redémarrage"
simulé — relecture depuis un nouvel appel), valeurs par défaut,
paramètres invalides.
"""

from services import parametres_service
from services.parametres_service import ParametresEtablissement


def test_valeurs_par_defaut_si_fichier_absent(tmp_path):
    chemin = tmp_path / "parametres.json"
    parametres = parametres_service.charger_parametres(chemin)
    assert parametres.nom_etablissement == ""
    assert parametres.devise == "FCFA"


def test_enregistrement_et_lecture(tmp_path):
    chemin = tmp_path / "parametres.json"
    parametres = ParametresEtablissement(
        nom_etablissement="Collège Bilingue Exemple",
        adresse="Yaoundé, Cameroun",
        telephone="+237 6XX XXX XXX",
        email="contact@ecole.cm",
        annee_scolaire="2026-2027",
        devise="FCFA",
        nom_responsable="M. le Coordonateur",
        fonction_responsable="Coordonateur Général",
    )
    parametres_service.enregistrer_parametres(parametres, chemin)

    relu = parametres_service.charger_parametres(chemin)
    assert relu == parametres


def test_persistance_a_travers_redemarrage_simule(tmp_path):
    """Simule un redémarrage : deux appels indépendants, le second doit voir ce que le premier a écrit."""
    chemin = tmp_path / "parametres.json"

    parametres_service.enregistrer_parametres(ParametresEtablissement(nom_etablissement="École A"), chemin)

    parametres_relus = parametres_service.charger_parametres(chemin)
    assert parametres_relus.nom_etablissement == "École A"


def test_modification_ecrase_proprement_les_valeurs_precedentes(tmp_path):
    chemin = tmp_path / "parametres.json"
    parametres_service.enregistrer_parametres(ParametresEtablissement(nom_etablissement="Ancien nom"), chemin)
    parametres_service.enregistrer_parametres(ParametresEtablissement(nom_etablissement="Nouveau nom"), chemin)

    relu = parametres_service.charger_parametres(chemin)
    assert relu.nom_etablissement == "Nouveau nom"


def test_fichier_vide_retombe_sur_defaut(tmp_path):
    chemin = tmp_path / "parametres.json"
    chemin.write_text("", encoding="utf-8")
    parametres = parametres_service.charger_parametres(chemin)
    assert parametres == ParametresEtablissement()


def test_fichier_json_corrompu_retombe_sur_defaut(tmp_path):
    chemin = tmp_path / "parametres.json"
    chemin.write_text("{ ceci n'est pas du JSON valide", encoding="utf-8")
    parametres = parametres_service.charger_parametres(chemin)
    assert parametres == ParametresEtablissement()


def test_fichier_json_valide_mais_pas_un_objet_retombe_sur_defaut(tmp_path):
    chemin = tmp_path / "parametres.json"
    chemin.write_text("[1, 2, 3]", encoding="utf-8")
    parametres = parametres_service.charger_parametres(chemin)
    assert parametres == ParametresEtablissement()


def test_cles_inconnues_dans_le_fichier_sont_ignorees(tmp_path):
    import json
    chemin = tmp_path / "parametres.json"
    chemin.write_text(
        json.dumps({"nom_etablissement": "École B", "champ_futur_inconnu": "valeur"}), encoding="utf-8"
    )
    parametres = parametres_service.charger_parametres(chemin)
    assert parametres.nom_etablissement == "École B"


def test_enregistrement_cree_le_dossier_parent(tmp_path):
    chemin = tmp_path / "sous_dossier" / "parametres.json"
    assert not chemin.parent.exists()
    parametres_service.enregistrer_parametres(ParametresEtablissement(nom_etablissement="Test"), chemin)
    assert chemin.exists()


def test_ne_modifie_jamais_le_taux_de_taxe():
    """Garde-fou : le service de paramètres n'importe ni n'utilise jamais TAUX_TAXE (règle métier figée)."""
    import inspect
    source = inspect.getsource(parametres_service)
    assert "import TAUX_TAXE" not in source
    assert "TAUX_TAXE =" not in source
    assert "TAUX_TAXE *" not in source
