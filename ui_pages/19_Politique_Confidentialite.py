"""
Page Streamlit — Politique de confidentialité.

Affiche le document docs/politique_confidentialite.md (source unique, également lisible
hors de l'application). Accessible à tout utilisateur authentifié,
quel que soit son rôle.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import permission_service
from utils.session_auth import exiger_permission
from utils.ui_helpers import afficher_document

exiger_permission(permission_service.DOCUMENTATION_CONSULTER)
afficher_document("politique_confidentialite")
