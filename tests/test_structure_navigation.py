"""
Garde-fou anti-régression (correction définitive — section 7 du
cahier des charges) : empêche qu'un futur changement ne recrée,
même accidentellement, un dossier `pages/` à la racine du projet.

Rappel du problème que ce test empêche de reproduire : Streamlit
redécouvre et affiche AUTOMATIQUEMENT, en liste plate, tout fichier
`.py` présent dans un dossier littéralement nommé `pages/` situé à
côté du script principal — indépendamment de toute logique Python
(y compris `st.navigation()`). La seule protection structurelle
fiable est qu'un tel dossier n'existe simplement jamais.
"""

from pathlib import Path

RACINE_PROJET = Path(__file__).resolve().parent.parent

NOMS_ANCIENNES_PAGES = [
    "1_Enseignants.py", "2_Periodes_Paie.py", "3_Donnees_Paie.py", "4_Calcul_Paie.py",
    "5_Generation_Comptable.py", "6_Bulletins_Paie.py", "7_Tableau_de_Bord.py", "8_Historique_Paie.py",
    "9_Controle_Paie.py", "10_Administration.py", "11_Cycle_Paie.py", "12_Rapports_Comptables.py",
    "13_Gestion_Documents.py", "14_Importation_Donnees.py", "15_Notifications.py", "16_Statistiques.py",
    "17_Automatisation.py",
]


def test_aucun_dossier_pages_a_la_racine_du_projet():
    """
    Le dossier `pages/` (nom reconnu automatiquement par Streamlit)
    ne doit JAMAIS exister à la racine du projet, sous peine de
    réintroduire l'affichage automatique en liste plate des 17 pages.
    """
    dossier_pages = RACINE_PROJET / "pages"
    assert not dossier_pages.exists(), (
        f"Le dossier {dossier_pages} existe — Streamlit le redécouvrira automatiquement "
        "et affichera de nouveau une liste plate de pages dans la sidebar."
    )


def test_aucune_ancienne_page_individuelle_dans_pages():
    """
    Même si `pages/` existait pour une autre raison légitime (peu
    probable), il ne doit jamais contenir l'un des 17 anciens
    fichiers de page applicatifs — condition suffisante pour que
    l'auto-découverte de Streamlit les affiche à plat.
    """
    dossier_pages = RACINE_PROJET / "pages"
    if not dossier_pages.exists():
        return
    for nom_fichier in NOMS_ANCIENNES_PAGES:
        assert not (dossier_pages / nom_fichier).exists(), (
            f"{dossier_pages / nom_fichier} existe — régression du bug de navigation à plat."
        )


def test_dossier_ui_pages_existe_et_contient_les_dix_sept_pages():
    """Les 17 pages doivent toutes vivre dans ui_pages/, jamais dans pages/."""
    dossier_ui_pages = RACINE_PROJET / "ui_pages"
    assert dossier_ui_pages.is_dir(), f"{dossier_ui_pages} doit exister."
    for nom_fichier in NOMS_ANCIENNES_PAGES:
        assert (dossier_ui_pages / nom_fichier).exists(), (
            f"{dossier_ui_pages / nom_fichier} est absent — fonctionnalité potentiellement perdue."
        )


def test_app_py_ne_reference_jamais_le_dossier_pages():
    """`app.py` doit construire ses `st.Page(...)` à partir de `ui_pages/`, jamais de `pages/`."""
    contenu = (RACINE_PROJET / "app.py").read_text(encoding="utf-8")
    assert '"pages/' not in contenu
    assert "'pages/" not in contenu


def test_utils_navigation_ne_reference_jamais_le_dossier_pages():
    """Idem pour le module de construction de la navigation."""
    contenu = (RACINE_PROJET / "utils" / "navigation.py").read_text(encoding="utf-8")
    assert '"pages/' not in contenu
    assert "'pages/" not in contenu
    assert "ui_pages" in contenu


# ---------------------------------------------------------------------
# Point d'entrée unique (section 8)
# ---------------------------------------------------------------------

def test_un_seul_point_dentree_streamlit_officiel():
    """
    Seul `app.py` doit être le point d'entrée invoqué par
    `streamlit run` ; `launcher.py` (utilisé uniquement pour produire
    l'exécutable Windows) doit se contenter de charger `app.py` par
    programmation, jamais dupliquer sa propre logique de navigation.
    """
    contenu_launcher = (RACINE_PROJET / "launcher.py").read_text(encoding="utf-8")
    assert "st.navigation(" not in contenu_launcher
    assert "app.py" in contenu_launcher


def test_app_py_est_le_seul_fichier_a_construire_la_navigation():
    """Aucun autre fichier Python à la racine du projet ne doit appeler st.navigation()."""
    for fichier in RACINE_PROJET.glob("*.py"):
        if fichier.name == "app.py":
            continue
        contenu = fichier.read_text(encoding="utf-8")
        assert "st.navigation(" not in contenu, f"{fichier.name} appelle st.navigation() — point d'entrée concurrent."
