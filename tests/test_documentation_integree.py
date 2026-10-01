"""
Documentation intégrée : guide utilisateur, guide administrateur,
politique de confidentialité, conditions générales d'utilisation.

Vérifie la présence des pages et de leur contenu obligatoire, l'absence
de coordonnées ou d'engagements juridiques inventés, et la cohérence
des valeurs citées avec la configuration réelle du logiciel.
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest

from config import settings
from models.enums import RoleUtilisateur
from services import permission_service
from utils.documentation import DOCUMENTS, lire_document, sommaire
from utils.navigation import PAGES_DOCUMENTATION, construire_blocs_visibles, toutes_les_entrees

RACINE = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------
# Présence des pages
# ---------------------------------------------------------------------

@pytest.mark.parametrize("cle", sorted(DOCUMENTS))
def test_document_present_et_non_vide(cle):
    texte = lire_document(cle)
    assert texte.startswith("# ")
    assert len(texte) > 2000


def test_document_inconnu_refuse():
    with pytest.raises(KeyError):
        lire_document("inexistant")


@pytest.mark.parametrize("chemin", PAGES_DOCUMENTATION)
def test_page_de_documentation_presente_et_protegee(chemin):
    contenu = (RACINE / chemin).read_text(encoding="utf-8")
    assert "exiger_permission(" in contenu
    assert "afficher_document(" in contenu


@pytest.mark.parametrize("titre", ["Guide utilisateur", "Politique de confidentialité", "Conditions d'utilisation"])
@pytest.mark.parametrize("role", list(RoleUtilisateur))
def test_documentation_accessible_a_tous_les_roles(titre, role):
    titres = [e.titre for entrees in construire_blocs_visibles(role).values() for e in entrees]
    assert titre in titres


def test_guide_administrateur_reserve_a_admin():
    for role in RoleUtilisateur:
        titres = [e.titre for entrees in construire_blocs_visibles(role).values() for e in entrees]
        assert ("Guide administrateur" in titres) == (role == RoleUtilisateur.ADMIN)


def test_pages_de_documentation_dans_les_blocs_existants():
    blocs_des_pages = {e.chemin for e in toutes_les_entrees()}
    assert set(PAGES_DOCUMENTATION) <= blocs_des_pages


def test_ecran_d_accueil_donne_acces_a_la_politique_et_aux_conditions():
    contenu = (RACINE / "utils" / "session_auth.py").read_text(encoding="utf-8")
    assert '"politique_confidentialite"' in contenu and '"conditions_utilisation"' in contenu


# ---------------------------------------------------------------------
# Contenu du guide utilisateur (15 sections)
# ---------------------------------------------------------------------

SECTIONS_GUIDE = [
    "1. Première connexion", "2. Navigation", "3. Gestion des enseignants", "4. Gestion des périodes",
    "5. Saisie de la paie", "6. Calcul", "7. Bulletins", "8. Contrôle", "9. Rapports et statistiques",
    "10. Documents", "11. Importation", "12. Automatisation", "13. Notifications", "14. Administration",
    "15. Réinitialisation des données",
]


def test_guide_utilisateur_couvre_les_quinze_sections_dans_l_ordre():
    assert sommaire(lire_document("guide_utilisateur")) == SECTIONS_GUIDE


def _section(texte, titre):
    debut = texte.index(f"## {titre}")
    suite = texte.find("\n## ", debut + 1)
    return texte[debut: suite if suite != -1 else None]


@pytest.mark.parametrize("section, mots", [
    ("1. Première connexion", ["premier", "Se connecter", "Se déconnecter"]),
    ("2. Navigation", ["Tableau de bord", "Gestion", "Paie", "Contrôle & Historique", "Analyse & Rapports",
                       "Documents & Opérations", "Administration & Sécurité"]),
    ("3. Gestion des enseignants", ["Création", "Modification", "Désactivation", "Suppression"]),
    ("4. Gestion des périodes", ["Création", "Ouverture", "Validation", "Clôture"]),
    ("5. Saisie de la paie", ["Heures", "Taux", "Primes", "indemnités", "Retenues"]),
    ("6. Calcul", ["Lancer le calcul", "Contrôle du résultat"]),
    ("7. Bulletins", ["Génération", "Consultation", "Export"]),
    ("8. Contrôle", ["Anomalies", "Validation", "Clôture"]),
    ("9. Rapports et statistiques", ["Consultation", "Filtres", "Exports"]),
    ("10. Documents", ["Gestion", "Intégrité", "Archivage"]),
    ("11. Importation", ["Fichiers acceptés", "Prévisualisation", "Validation", "Rollback"]),
    ("12. Automatisation", ["Génération groupée", "Exports"]),
    ("13. Notifications", ["Consultation", "Acquittement", "Résolution"]),
    ("14. Administration", ["Utilisateurs", "Rôles", "Paramètres", "Sauvegardes", "Restauration", "Diagnostics"]),
    ("15. Réinitialisation des données", ["Ce qui est supprimé", "Ce qui est conservé",
                                           "Les comptes ne sont PAS supprimés", "Confirmation",
                                           "Sauvegarde préalable"]),
])
def test_guide_utilisateur_contenu_de_chaque_section(section, mots):
    texte = _section(lire_document("guide_utilisateur"), section)
    for mot in mots:
        assert mot in texte, f"Section {section} : « {mot} » absent"


def test_guide_administrateur_couvre_les_operations_sensibles():
    titres = " ".join(sommaire(lire_document("guide_administrateur"))).lower()
    for sujet in ("comptes", "rôles", "permissions", "sauvegarde", "restauration", "diagnostics",
                  "réinitialisation des données", "maintenance"):
        assert sujet in titres, sujet


# ---------------------------------------------------------------------
# Politique de confidentialité et CGU
# ---------------------------------------------------------------------

def test_politique_couvre_les_sujets_demandes():
    titres = " ".join(sommaire(lire_document("politique_confidentialite"))).lower()
    for sujet in ("données traitées", "finalités", "lieu de stockage", "protection", "rôles", "sauvegardes",
                  "demandes"):
        assert sujet in titres, sujet


def test_cgu_couvrent_les_sujets_demandes():
    titres = " ".join(sommaire(lire_document("conditions_utilisation"))).lower()
    for sujet in ("objet", "conditions d'accès", "responsabilités des utilisateurs", "responsabilités de l'administrateur",
                  "utilisation des comptes", "confidentialité", "utilisation correcte des données", "sauvegardes",
                  "sécurité", "comportements interdits", "limitation de responsabilité", "évolution du logiciel",
                  "contact"):
        assert sujet in titres, sujet


@pytest.mark.parametrize("cle", ["politique_confidentialite", "conditions_utilisation"])
def test_textes_juridiques_signalent_la_validation_necessaire(cle):
    texte = lire_document(cle)
    avertissement = texte.split("\n\n", 2)[1]  # encadré placé juste sous le titre
    assert re.search(r"valid(er|é|ation)", avertissement) and "juridique" in avertissement
    assert "[" in texte and "à compléter" in texte


def test_cgu_marquent_les_clauses_a_valider():
    assert lire_document("conditions_utilisation").count("[validation juridique requise]") >= 2


@pytest.mark.parametrize("cle", sorted(DOCUMENTS))
def test_aucune_coordonnee_inventee(cle):
    texte = lire_document(cle)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texte), "adresse électronique inventée"
    assert not re.search(r"https?://", texte), "lien externe"
    assert not re.search(r"(\+\d{3}|\b\d{2,3}[ .]\d{2}[ .]\d{2}[ .]\d{2}\b)", texte), "numéro de téléphone"


@pytest.mark.parametrize("cle", sorted(DOCUMENTS))
def test_aucune_garantie_ou_obligation_inventee(cle):
    texte = lire_document(cle).lower()
    for formule in ("100 % conforme", "entièrement conforme", "conforme au rgpd", "garantit la conformité",
                    "certifié", "certification", "garantie totale", "sécurité absolue", "infaillible"):
        assert formule not in texte, formule


# ---------------------------------------------------------------------
# Cohérence des valeurs citées avec la configuration réelle
# ---------------------------------------------------------------------

def test_valeurs_citees_conformes_a_la_configuration():
    guide = lire_document("guide_utilisateur")
    politique = lire_document("politique_confidentialite")
    from services.import_service import TAILLE_MAX_OCTETS
    from services.reinitialisation_service import PHRASE_CONFIRMATION

    assert settings.PASSWORD_MIN_LENGTH == 8 and "8 caractères minimum" in guide
    assert settings.MAX_LOGIN_ATTEMPTS == 5 and "cinq tentatives" in guide and "cinq tentatives" in politique
    assert settings.SESSION_TIMEOUT_SECONDES == 2 * 60 * 60 and "deux heures" in guide
    assert settings.TAUX_TAXE == Decimal("0.05") and "5 %" in guide
    assert TAILLE_MAX_OCTETS == 10 * 1024 * 1024 and "10 Mo" in guide
    assert PHRASE_CONFIRMATION in guide
    assert settings.NB_SEMAINES_PAR_PERIODE == 5 and "cinq semaines" in guide
    assert "208 250 FCFA" in guide  # cas de référence, identique à tests/test_paie_service.py


def test_pages_citees_par_le_guide_existent_dans_la_navigation():
    guide = lire_document("guide_utilisateur")
    for entree in toutes_les_entrees():
        assert entree.titre in guide, f"Page « {entree.titre} » absente du guide"


def test_matrice_lisible_couvre_toutes_les_permissions():
    lignes = permission_service.matrice_lisible()
    assert len(lignes) == len(permission_service._MATRICE)
    assert all(ligne["Permission"] != ligne["Identifiant"] for ligne in lignes)
    reinit = next(l for l in lignes if l["Identifiant"] == permission_service.DONNEES_REINITIALISER)
    assert (reinit["Administrateur"], reinit["Gestionnaire de paie"], reinit["Consultation"]) == ("Oui", "Non", "Non")
