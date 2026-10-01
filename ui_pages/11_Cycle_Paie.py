"""
Page Streamlit — Module 12 : Cycle de paie.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de calcul de salaire. Toutes les transitions
d'état sont déléguées à services/periode_service.py et
services/controle_paie_service.py — rien n'est dupliqué ici. Les
actions « Valider » et « Clôturer », qui exigent un contrôle complet
avant confirmation, restent centralisées sur la page « Contrôle de la
paie » (module 09) : cette page y redirige plutôt que de dupliquer
cet écran de confirmation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from database.repositories import audit_log_repository
from models.enums import StatutPeriode
from services import periode_service
from services.comptabilite_service import ComptabiliteError, preparer_etat_comptable
from services.controle_paie_service import ControlePaieError, ouvrir_periode_avec_audit
from services import permission_service
from utils.session_auth import exiger_permission, utilisateur_courant_role
from utils.formatters import formater_fcfa, libelle_statut_periode
from utils.ui_helpers import badge_statut_periode

init_database()


exiger_permission(permission_service.PERIODE_CONSULTER)

peut_ouvrir = permission_service.a_permission(utilisateur_courant_role(), permission_service.PERIODE_GERER)

st.title("Cycle de paie")
st.caption(
    "Vue d'ensemble du workflow BROUILLON → OUVERTE → VALIDEE → CLOTUREE, "
    "et historique des changements d'état."
)

# =======================================================================
# 1. Sélection de la période
# =======================================================================
periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)

st.divider()

# =======================================================================
# 2. État actuel
# =======================================================================
st.header("État actuel")
col_periode, col_statut = st.columns(2)
col_periode.metric("Période", periode.libelle)
col_statut.metric("Statut", libelle_statut_periode(periode.statut))
with col_statut:
    st.markdown(badge_statut_periode(periode.statut), unsafe_allow_html=True)

# =======================================================================
# 3. Progression visuelle
# =======================================================================
st.header("Progression")

ORDRE_STATUTS = [StatutPeriode.BROUILLON, StatutPeriode.OUVERTE, StatutPeriode.VALIDEE, StatutPeriode.CLOTUREE]
LIBELLES_ETAPES = {
    StatutPeriode.BROUILLON: "Brouillon",
    StatutPeriode.OUVERTE: "Ouverte",
    StatutPeriode.VALIDEE: "Validée",
    StatutPeriode.CLOTUREE: "Clôturée",
}
index_actuel = ORDRE_STATUTS.index(periode.statut)

colonnes_etapes = st.columns(len(ORDRE_STATUTS))
for i, statut_etape in enumerate(ORDRE_STATUTS):
    with colonnes_etapes[i]:
        # Chaque état est explicitement libellé : jamais porté par la seule couleur.
        if i < index_actuel:
            st.success(f"{i + 1}. {LIBELLES_ETAPES[statut_etape]} — étape terminée")
        elif i == index_actuel:
            st.info(f"{i + 1}. {LIBELLES_ETAPES[statut_etape]} — étape actuelle")
        else:
            st.caption(f"{i + 1}. {LIBELLES_ETAPES[statut_etape]} — étape à venir")

st.divider()

# =======================================================================
# 4. Actions disponibles (uniquement celles autorisées)
# =======================================================================
st.header("Actions disponibles")

if periode.statut == StatutPeriode.BROUILLON:
    if not peut_ouvrir:
        st.info("Vous n'avez pas la permission d'ouvrir cette période.")
    else:
        cle_confirmation_ouverture = f"confirmation_ouverture_{periode_id}"
        if not st.session_state.get(cle_confirmation_ouverture, False):
            if st.button("Ouvrir la période", type="primary"):
                st.session_state[cle_confirmation_ouverture] = True
                st.rerun()
        else:
            st.warning(f"Confirmez-vous l'ouverture de la période **{periode.libelle}** à la saisie des données ?")
            col_confirmer, col_annuler = st.columns(2)
            with col_confirmer:
                if st.button("Confirmer l'ouverture", type="primary"):
                    try:
                        ouvrir_periode_avec_audit(periode_id, utilisateur=st.session_state.get("username"))
                        st.session_state.pop(cle_confirmation_ouverture, None)
                        st.success("Période ouverte.")
                        st.rerun()
                    except ControlePaieError as erreur:
                        st.session_state.pop(cle_confirmation_ouverture, None)
                        st.error(str(erreur))
            with col_annuler:
                if st.button("Annuler"):
                    st.session_state.pop(cle_confirmation_ouverture, None)
                    st.rerun()

elif periode.statut == StatutPeriode.OUVERTE:
    st.info(
        "La validation exige un contrôle complet des données de paie. "
        "Rendez-vous sur la page **« Contrôle de la paie »**."
    )
    st.page_link("ui_pages/9_Controle_Paie.py", label="Aller au contrôle de la paie", icon=":material/arrow_forward:")

elif periode.statut == StatutPeriode.VALIDEE:
    st.info(
        "La clôture exige un contrôle complet des données de paie. "
        "Rendez-vous sur la page **« Contrôle de la paie »**."
    )
    st.page_link("ui_pages/9_Controle_Paie.py", label="Aller au contrôle de la paie", icon=":material/arrow_forward:")

    try:
        etat = preparer_etat_comptable(periode_id)
        st.markdown("**Aperçu avant clôture**")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Enseignants", len(etat.resultats))
        col2.metric("Total brut", formater_fcfa(etat.totaux.total_gain_heures + etat.totaux.total_primes))
        col3.metric("Total taxe", formater_fcfa(etat.totaux.total_taxe))
        col4.metric("Total net à payer", formater_fcfa(etat.totaux.total_net_a_percevoir))
    except ComptabiliteError:
        pass

else:  # CLOTUREE
    st.success(
        "Cette période est **clôturée**. Ses données de paie ne sont plus modifiables par les opérations "
        "normales de l'application. Consultation, export et bulletins restent disponibles."
    )

st.divider()

# =======================================================================
# 5. Historique du cycle (à partir de l'audit existant)
# =======================================================================
st.header("Historique du cycle")

entrees_audit = audit_log_repository.lister_par_entite("periode_paie", periode_id)
evenements_cycle = {
    "periode_ouverte", "validation_periode", "cloture_periode",
    "validation_refusee", "cloture_refusee", "suppression_definitive",
}
entrees_pertinentes = [e for e in entrees_audit if e.type_action.value in evenements_cycle]

LIBELLES_EVENEMENTS = {
    "periode_ouverte": "Ouverture",
    "validation_periode": "Validation",
    "cloture_periode": "Clôture",
    "validation_refusee": "Validation refusée",
    "cloture_refusee": "Clôture refusée",
    "suppression_definitive": "Suppression définitive",
}

if not entrees_pertinentes:
    st.info("Aucune donnée disponible : aucun événement de cycle n'est enregistré pour cette période.")
else:
    lignes_historique = [
        {
            "Date": e.date_action,
            "Événement": LIBELLES_EVENEMENTS.get(e.type_action.value, e.type_action.value),
            "Utilisateur": e.utilisateur or "—",
            "Détail": e.details or "—",
        }
        for e in entrees_pertinentes
    ]
    st.dataframe(lignes_historique, use_container_width=True, hide_index=True)
