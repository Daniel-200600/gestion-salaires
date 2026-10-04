"""
Construction de la structure de navigation en 7 grands blocs
(correction finale — consolidation de la navigation).

Ce module ne contient AUCUN appel Streamlit (`st.Page`, `st.navigation`)
: uniquement des données pures, pour être entièrement testable en
dehors d'une session Streamlit active. `app.py` convertit ensuite
cette structure en objets `st.Page` et appelle `st.navigation()`.

La définition des 7 blocs est figée ici (section 3 du cahier des
charges) — aucun fichier de page n'est déplacé ni sa logique modifiée
par ce module ; seul le chemin (`ui_pages/`, et non plus `pages/`,
pour empêcher toute redécouverte automatique par le mécanisme
multipage natif de Streamlit — voir docs/correction_consolidation.md)
et le regroupement changent.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from services import permission_service

DOSSIER_PAGES = "ui_pages"


@dataclass(frozen=True)
class EntreeNavigation:
    titre: str
    icone: str  # icône Material Symbols (bibliothèque cohérente fournie par Streamlit), jamais un emoji
    chemin: str  # relatif à la racine du projet
    permission: str
    defaut: bool = False
    # Adresse stable et lisible de la page (ex : /enseignants), utile pour
    # une navigation déterministe, y compris par des outils automatisés.
    # La page par défaut est servie à la racine et n'en a pas besoin.
    url_path: Optional[str] = None


def _icone(nom: str) -> str:
    return f":material/{nom}:"


# Pages de documentation : accessibles à tout utilisateur authentifié,
# regroupées dans le bloc d'accueil (aucun 8e bloc n'est créé).
PAGES_DOCUMENTATION = (
    f"{DOSSIER_PAGES}/18_Guide_Utilisateur.py",
    f"{DOSSIER_PAGES}/19_Politique_Confidentialite.py",
    f"{DOSSIER_PAGES}/20_Conditions_Utilisation.py",
    f"{DOSSIER_PAGES}/21_Guide_Administrateur.py",
    f"{DOSSIER_PAGES}/22_A_Propos.py",
)

DEFINITION_BLOCS: Dict[str, List[EntreeNavigation]] = {
    "Tableau de bord": [
        EntreeNavigation(
            "Tableau de bord", _icone("dashboard"), f"{DOSSIER_PAGES}/7_Tableau_de_Bord.py",
            permission_service.PAIE_CONSULTER, defaut=True,
        ),
        EntreeNavigation(
            "Guide utilisateur", _icone("menu_book"), f"{DOSSIER_PAGES}/18_Guide_Utilisateur.py",
            permission_service.DOCUMENTATION_CONSULTER, url_path="guide-utilisateur",
        ),
        EntreeNavigation(
            "Politique de confidentialité", _icone("privacy_tip"), f"{DOSSIER_PAGES}/19_Politique_Confidentialite.py",
            permission_service.DOCUMENTATION_CONSULTER, url_path="politique-confidentialite",
        ),
        EntreeNavigation(
            "Conditions d'utilisation", _icone("gavel"), f"{DOSSIER_PAGES}/20_Conditions_Utilisation.py",
            permission_service.DOCUMENTATION_CONSULTER, url_path="conditions-utilisation",
        ),
        EntreeNavigation(
            "À propos", _icone("info"), f"{DOSSIER_PAGES}/22_A_Propos.py",
            permission_service.DOCUMENTATION_CONSULTER, url_path="a-propos",
        ),
    ],
    "Gestion": [
        EntreeNavigation("Enseignants", _icone("group"), f"{DOSSIER_PAGES}/1_Enseignants.py",
                         permission_service.ENSEIGNANT_CONSULTER, url_path="enseignants"),
        EntreeNavigation("Périodes de paie", _icone("calendar_month"), f"{DOSSIER_PAGES}/2_Periodes_Paie.py",
                         permission_service.PERIODE_CONSULTER, url_path="periodes-paie"),
    ],
    "Paie": [
        EntreeNavigation("Données de paie", _icone("edit_note"), f"{DOSSIER_PAGES}/3_Donnees_Paie.py",
                         permission_service.PAIE_MODIFIER, url_path="donnees-paie"),
        EntreeNavigation("Import du fichier de paie", _icone("upload_file"),
                         f"{DOSSIER_PAGES}/23_Import_Fichier_Paie.py",
                         permission_service.IMPORT_DONNEES, url_path="import-fichier-paie"),
        EntreeNavigation("Calcul de paie", _icone("calculate"), f"{DOSSIER_PAGES}/4_Calcul_Paie.py",
                         permission_service.PAIE_CONSULTER, url_path="calcul-paie"),
        EntreeNavigation("Cycle de paie", _icone("sync_alt"), f"{DOSSIER_PAGES}/11_Cycle_Paie.py",
                         permission_service.PERIODE_CONSULTER, url_path="cycle-paie"),
        EntreeNavigation("Bulletins de solde", _icone("description"), f"{DOSSIER_PAGES}/6_Bulletins_Paie.py",
                         permission_service.BULLETIN_CONSULTER, url_path="bulletins"),
        EntreeNavigation("Génération comptable", _icone("table_chart"), f"{DOSSIER_PAGES}/5_Generation_Comptable.py",
                         permission_service.EXPORT_GENERER, url_path="generation-comptable"),
    ],
    "Contrôle & Historique": [
        EntreeNavigation("Contrôle de la paie", _icone("fact_check"), f"{DOSSIER_PAGES}/9_Controle_Paie.py",
                         permission_service.PAIE_CONTROLER, url_path="controle-paie"),
        EntreeNavigation("Historique de paie", _icone("history"), f"{DOSSIER_PAGES}/8_Historique_Paie.py",
                         permission_service.HISTORIQUE_CONSULTER, url_path="historique-paie"),
    ],
    "Analyse & Rapports": [
        EntreeNavigation("Rapports comptables", _icone("summarize"), f"{DOSSIER_PAGES}/12_Rapports_Comptables.py",
                         permission_service.REPORTING_CONSULTER, url_path="rapports-comptables"),
        EntreeNavigation("Statistiques", _icone("bar_chart"), f"{DOSSIER_PAGES}/16_Statistiques.py",
                         permission_service.STATISTIQUES_CONSULTER, url_path="statistiques"),
    ],
    "Documents & Opérations": [
        EntreeNavigation("Gestion des documents", _icone("folder_open"), f"{DOSSIER_PAGES}/13_Gestion_Documents.py",
                         permission_service.DOCUMENT_CONSULTER, url_path="documents"),
        EntreeNavigation("Importation", _icone("upload_file"), f"{DOSSIER_PAGES}/14_Importation_Donnees.py",
                         permission_service.IMPORT_DONNEES, url_path="importation"),
        EntreeNavigation("Notifications", _icone("notifications"), f"{DOSSIER_PAGES}/15_Notifications.py",
                         permission_service.ALERTE_CONSULTER, url_path="notifications"),
        EntreeNavigation("Automatisation", _icone("playlist_play"), f"{DOSSIER_PAGES}/17_Automatisation.py",
                         permission_service.AUTOMATISATION_EXECUTER, url_path="automatisation"),
    ],
    "Administration & Sécurité": [
        EntreeNavigation("Administration", _icone("admin_panel_settings"), f"{DOSSIER_PAGES}/10_Administration.py",
                         permission_service.ADMINISTRATION_CONSULTER, url_path="administration"),
        EntreeNavigation("Guide administrateur", _icone("manage_accounts"), f"{DOSSIER_PAGES}/21_Guide_Administrateur.py",
                         permission_service.ADMINISTRATION_CONSULTER, url_path="guide-administrateur"),
    ],
}


def construire_blocs_visibles(role: Optional[object]) -> Dict[str, List[EntreeNavigation]]:
    """
    Filtre `DEFINITION_BLOCS` selon les permissions réelles du rôle
    donné (matrice centrale du module 11, jamais dupliquée ici). Un
    bloc n'est retourné que s'il contient au moins une entrée visible
    — jamais de bloc vide affiché. Fonction pure : aucun appel
    Streamlit, testable directement.
    """
    resultat: Dict[str, List[EntreeNavigation]] = {}
    for nom_bloc, entrees in DEFINITION_BLOCS.items():
        visibles = [e for e in entrees if permission_service.a_permission(role, e.permission)]
        if visibles:
            resultat[nom_bloc] = visibles
    return resultat


def toutes_les_entrees() -> List[EntreeNavigation]:
    """Liste à plat de toutes les entrées définies, tous blocs confondus — utile pour les tests d'exhaustivité."""
    return [e for entrees in DEFINITION_BLOCS.values() for e in entrees]


def entrees_fonctionnelles() -> List[EntreeNavigation]:
    """Les 17 pages fonctionnelles de l'application (hors pages de documentation)."""
    return [e for e in toutes_les_entrees() if e.chemin not in PAGES_DOCUMENTATION]
