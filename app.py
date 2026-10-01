"""
Point d'entrée officiel de l'application Streamlit.

Lancer avec :
    streamlit run app.py

Ce fichier ne contient AUCUNE logique métier, AUCUN calcul de salaire
et AUCUNE requête SQL : il se contente d'initialiser la base de
données si nécessaire, puis d'orchestrer la navigation.

CORRECTION FINALE — consolidation réelle de la navigation : les pages
métier ne vivent plus dans un dossier nommé `pages/`, seul nom que le
mécanisme multipage AUTOMATIQUE de Streamlit redécouvre et affiche à
plat dans la barre latérale, quel que soit le code de ce fichier.
Elles ont été déplacées telles quelles (aucune logique modifiée) vers
`ui_pages/`, un nom sans signification particulière pour Streamlit,
ce qui élimine catégoriquement tout risque de double affichage.
La structure des 7 blocs (définie dans `utils/navigation.py`, testée
indépendamment de tout rendu Streamlit) est ensuite construite ici en
objets `st.Page`, regroupés via `st.navigation()`. Une section
n'apparaît dans la barre latérale QUE si le rôle courant possède la
permission correspondante — la vérification de permission propre à
chaque page (`exiger_permission`, inchangée) reste la véritable
barrière de sécurité ; ce filtrage n'est qu'un confort d'affichage.
"""

import sys
from pathlib import Path

# Garantit que la racine du projet est importable, quel que soit le
# répertoire depuis lequel `streamlit run app.py` est invoqué.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from config.settings import FAVICON_PATH, LOGO_HORIZONTAL_PATH, LOGO_SYMBOLE_PATH, NOM_APPLICATION, VERSION
from database.initialization import init_database
from exports.excel_export import EXPORT_DIR
from exports.word_export import EXPORT_DIR_BULLETINS
from utils.navigation import construire_blocs_visibles
from utils.session_auth import afficher_bandeau_utilisateur, exiger_authentification, utilisateur_courant_role

# Idempotent : garantit que les tables existent (et migre une base
# ancienne si nécessaire, voir database/migrations.py) dès le tout
# premier lancement.
init_database()
# Idempotent également : garantit une structure de dossiers complète dès
# l'installation, sur n'importe quelle machine (portabilité, module 10).
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR_BULLETINS.mkdir(parents=True, exist_ok=True)

# Favicon : fichier image dédié (assets/favicon.png), jamais un emoji.
# Résolu via config.paths.resource_root(), donc identique en
# développement et dans l'exécutable Windows.
st.set_page_config(
    page_title=NOM_APPLICATION,
    page_icon=str(FAVICON_PATH) if FAVICON_PATH.exists() else None,
    layout="wide",
    menu_items={
        "Get help": None,
        "Report a bug": None,
        "About": f"**{NOM_APPLICATION}** — version {VERSION}. Logiciel de gestion de la paie des enseignants.",
    },
)

if LOGO_HORIZONTAL_PATH.exists():
    st.logo(
        str(LOGO_HORIZONTAL_PATH),
        icon_image=str(LOGO_SYMBOLE_PATH) if LOGO_SYMBOLE_PATH.exists() else None,
        size="large",
    )

# Habillage visuel commun à tous les écrans : cartes d'indicateurs
# sobres (fond blanc, bordure grise, angles faiblement arrondis) et
# contour de focus clavier bien visible (accessibilité). Aucune
# animation, aucun dégradé, aucun effet de transparence.
st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #D5DBE3;
        border-left: 3px solid #1F3A6E;
        border-radius: 4px;
        padding: 0.75rem 1rem;
    }
    div[data-testid="stMetricLabel"] p {
        font-weight: 600;
        color: #4A5566;
    }
    /* Textes secondaires (légendes) : gris foncé, contraste 7,5:1 sur fond blanc. */
    div[data-testid="stCaptionContainer"],
    div[data-testid="stCaptionContainer"] p {
        color: #4A5566;
    }
    :focus-visible {
        outline: 2px solid #1F3A6E !important;
        outline-offset: 2px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

exiger_authentification()
afficher_bandeau_utilisateur()

role_courant = utilisateur_courant_role()
blocs_visibles = construire_blocs_visibles(role_courant)

blocs_streamlit = {
    nom_bloc: [
        st.Page(
            entree.chemin,
            title=entree.titre,
            icon=entree.icone,
            default=entree.defaut,
            url_path=None if entree.defaut else entree.url_path,
        )
        for entree in entrees
    ]
    for nom_bloc, entrees in blocs_visibles.items()
}

page_courante = st.navigation(blocs_streamlit)
page_courante.run()
