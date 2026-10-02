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
from services import licence_service, permission_service
from utils.session_auth import exiger_permission
from utils.ui_helpers import afficher_document

exiger_permission(permission_service.DOCUMENTATION_CONSULTER)
st.caption(f"{NOM_APPLICATION} — version installée : {VERSION} — auteur : {AUTEUR} ({CONTACT_AUTEUR})")
etat_licence = licence_service.etat_licence()
if etat_licence.active:
    st.caption(
        f"Licence n° {etat_licence.licence.numero} : {etat_licence.licence.etablissement}, "
        f"{etat_licence.licence.libelle_validite}."
    )
else:
    st.caption(
        f"Mode démonstration ({licence_service.LIMITE_DEMO_ENSEIGNANTS} enseignants au maximum). "
        f"Code de cet ordinateur : {licence_service.code_machine()}."
    )
afficher_document("a_propos")
