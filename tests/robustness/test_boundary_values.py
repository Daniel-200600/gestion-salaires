"""
Tests de robustesse — valeurs limites (module 19, section 27).
"""

import pytest

import database.connection as database_connection
from services import controle_paie_service, donnees_paie_service, enseignant_service, periode_service, statistiques_service
from services.donnees_paie_service import DonneesPaieEnseignant


@pytest.fixture(autouse=True)
def _rediriger_connexion_par_defaut(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)


# ---------------------------------------------------------------------
# Effectifs limites
# ---------------------------------------------------------------------

def test_zero_enseignant():
    p = periode_service.creer_periode(mois=1, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    stats = statistiques_service.statistiques_generales(p.id)
    assert stats.nombre_enseignants_total == 0
    assert stats.heures.nombre == 0


def test_un_seul_enseignant():
    e = enseignant_service.creer_enseignant(nom="Solo", prenom="X", sexe="M", statut="P", taux_horaire=1000)
    p = periode_service.creer_periode(mois=2, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10})]
    )
    stats = statistiques_service.statistiques_generales(p.id)
    assert stats.nombre_enseignants_total == 1
    assert stats.heures.ecart_type is None


def test_plusieurs_centaines_enseignants():
    p = periode_service.creer_periode(mois=3, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    ids = []
    for i in range(300):
        e = enseignant_service.creer_enseignant(
            nom=f"Ens{i}", prenom="X", sexe="M" if i % 2 == 0 else "F",
            statut="P" if i % 3 == 0 else "V", taux_horaire=1000 + i,
        )
        ids.append(e.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=eid, heures_par_semaine={1: 10}) for eid in ids]
    )

    stats = statistiques_service.statistiques_generales(p.id)
    assert stats.nombre_enseignants_total == 300
    assert stats.heures.nombre == 300


def test_zero_periode():
    periodes = periode_service.lister_periodes()
    assert periodes == []


# ---------------------------------------------------------------------
# Montants et heures extrêmes
# ---------------------------------------------------------------------

def test_tres_gros_montant():
    e = enseignant_service.creer_enseignant(nom="Riche", prenom="X", sexe="M", statut="P", taux_horaire=999999)
    p = periode_service.creer_periode(mois=4, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 40, 2: 40, 3: 40, 4: 40, 5: 40})]
    )
    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.net_a_percevoir > 0
    assert isinstance(resultat.net_a_percevoir, int)


def test_taux_horaire_zero_ne_plante_pas():
    e = enseignant_service.creer_enseignant(nom="Zero", prenom="X", sexe="M", statut="P", taux_horaire=0)
    p = periode_service.creer_periode(mois=5, annee=2099)
    controle_paie_service.ouvrir_periode_avec_audit(p.id)
    donnees_paie_service.enregistrer_donnees_paie_groupe(
        p.id, [DonneesPaieEnseignant(enseignant_id=e.id, heures_par_semaine={1: 10})]
    )
    from services.paie_service import calculer_paie_enseignant
    resultat = calculer_paie_enseignant(p.id, e.id)
    assert resultat.gain_heures == 0
    assert resultat.net_a_percevoir >= 0


# ---------------------------------------------------------------------
# Chaînes de caractères
# ---------------------------------------------------------------------

def test_chaine_vide_nom_refusee():
    from utils.validators import EnseignantValidationError
    with pytest.raises((EnseignantValidationError, ValueError)):
        enseignant_service.creer_enseignant(nom="", prenom="X", sexe="M", statut="P", taux_horaire=1000)


def test_nom_tres_long_ne_plante_pas():
    nom_long = "A" * 500
    try:
        e = enseignant_service.creer_enseignant(nom=nom_long, prenom="X", sexe="M", statut="P", taux_horaire=1000)
        assert e.nom == nom_long
    except Exception as erreur:
        assert not isinstance(erreur, (AttributeError, TypeError, KeyError))


def test_caracteres_unicode_et_accentues():
    e = enseignant_service.creer_enseignant(
        nom="Müller-Özdemir", prenom="François 王", sexe="M", statut="P", taux_horaire=1000
    )
    assert "Müller" in e.nom
    assert "王" in e.prenom


def test_caracteres_speciaux_varies_ne_plantent_pas():
    """
    Stockés tels quels côté contenu (jamais interprétés comme du code,
    aucun moteur de template ni shell dans le projet) — seule la
    normalisation d'espaces déjà existante (valider_nom_ou_prenom,
    module 01) s'applique, ce qui est un comportement voulu et non lié
    à la sécurité de ces caractères.
    """
    noms_speciaux = [
        "<script>alert(1)</script>", "${jndi:ldap://evil}", "{{7*7}}",
        "Nom\twith\ttabs", "Nom\nwith\nnewlines",
    ]
    for nom in noms_speciaux:
        e = enseignant_service.creer_enseignant(nom=nom, prenom="X", sexe="M", statut="P", taux_horaire=1000)
        assert e.id is not None
        assert isinstance(e.nom, str) and len(e.nom) > 0
