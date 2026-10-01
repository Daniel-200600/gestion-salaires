"""
Page Streamlit — Guide administrateur (réservée au rôle ADMIN).

Affiche docs/guide_administrateur.md, puis la matrice des permissions
réellement appliquée, générée à partir de services/permission_service.py
(elle ne peut donc jamais diverger de la configuration effective).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from services import permission_service
from utils.session_auth import exiger_permission
from utils.ui_helpers import afficher_document

exiger_permission(permission_service.ADMINISTRATION_CONSULTER)
afficher_document("guide_administrateur")

st.header("Matrice des permissions appliquée")
st.caption(
    "Tableau généré à partir de la configuration de l'application au moment de l'affichage. "
    "« Oui » : le rôle dispose de la permission ; « Non » : l'opération est refusée."
)
st.dataframe(permission_service.matrice_lisible(), use_container_width=True, hide_index=True)
