"""
Page Streamlit — À propos : version installée, nouveautés, licence, contact.

Affiche le document docs/a_propos.md. Accessible à tout utilisateur
authentifié, quel que soit son rôle.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from config.settings import AUTEUR, CONTACT_AUTEUR, NOM_APPLICATION, VERSION
from services import permission_service
from utils.session_auth import exiger_permission
from utils.ui_helpers import afficher_document

exiger_permission(permission_service.DOCUMENTATION_CONSULTER)
st.caption(f"{NOM_APPLICATION} — version installée : {VERSION} — auteur : {AUTEUR} ({CONTACT_AUTEUR})")
afficher_document("a_propos")
