"""
Page Streamlit — Module 16 : Notifications.

Règle d'architecture stricte : cette page orchestre uniquement
l'interface. Toute la détection vit dans
services/alert_detection_service.py, tout le cycle de vie dans
services/alert_service.py — tous deux indépendants de Streamlit.
"""

import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.initialization import init_database
from exports.excel_export import EXPORT_DIR
from exports.word_export import EXPORT_DIR_BULLETINS
from models.enums import NiveauAlerte, StatutAlerte
from services import alert_detection_service, alert_service, enseignant_service, periode_service, permission_service
from services.alert_service import AlertServiceError
from utils.session_auth import exiger_permission, utilisateur_courant_role
from utils.ui_helpers import badge_niveau_alerte

init_database()


exiger_permission(permission_service.ALERTE_CONSULTER)

peut_gerer = permission_service.a_permission(utilisateur_courant_role(), permission_service.ALERTE_GERER)

st.title("Notifications")
st.caption("Surveillance opérationnelle — les alertes ne remplacent aucun contrôle métier existant.")

LIBELLES_NIVEAU = {
    NiveauAlerte.CRITIQUE: "Critique", NiveauAlerte.ERREUR: "Erreur",
    NiveauAlerte.AVERTISSEMENT: "Avertissement", NiveauAlerte.INFO: "Info",
}
LIBELLES_STATUT = {
    StatutAlerte.NOUVELLE: "Nouvelle", StatutAlerte.LUE: "Lue", StatutAlerte.ACQUITTEE: "Acquittée",
    StatutAlerte.RESOLUE: "Résolue", StatutAlerte.IGNOREE: "Ignorée",
}

# =======================================================================
# Synthèse (section 16)
# =======================================================================
compteurs = alert_service.compter_alertes_actives()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Critiques", compteurs.get("critique", 0))
col2.metric("Erreurs", compteurs.get("erreur", 0))
col3.metric("Avertissements", compteurs.get("avertissement", 0))
col4.metric("Informations", compteurs.get("info", 0))

if peut_gerer and st.button("Analyser maintenant", type="primary"):
    with st.spinner("Analyse en cours..."):
        alert_detection_service.detecter_alertes_enseignants()
        alert_detection_service.detecter_alertes_periodes()
        alert_detection_service.detecter_alertes_administratives()
        alert_detection_service.detecter_alertes_documents(dossiers_a_scanner=[EXPORT_DIR_BULLETINS, EXPORT_DIR])
        for p in periode_service.lister_periodes():
            if p.statut.value != "brouillon":
                alert_detection_service.detecter_alertes_controle_paie(p.id)
    st.success("Analyse terminée.")
    st.rerun()

st.divider()

# =======================================================================
# Filtres (section 17/34)
# =======================================================================
st.header("Filtres")
col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    choix_niveau = st.selectbox("Niveau", ["Tous"] + [LIBELLES_NIVEAU[n] for n in NiveauAlerte])
with col_b:
    choix_statut = st.selectbox(
        "Statut",
        ["Toutes (actives)", "Toutes (y compris résolues/ignorées)"] + [LIBELLES_STATUT[s] for s in StatutAlerte],
    )
with col_c:
    periodes = periode_service.lister_periodes()
    options_periodes = {"Toutes": None}
    options_periodes.update({p.libelle: p.id for p in periodes})
    choix_periode = st.selectbox("Période", list(options_periodes.keys()))
with col_d:
    enseignants = enseignant_service.lister_enseignants(inclure_inactifs=True)
    options_enseignants = {"Tous": None}
    options_enseignants.update({f"{e.nom} {e.prenom}": e.id for e in enseignants})
    choix_enseignant = st.selectbox("Enseignant", list(options_enseignants.keys()))

terme_recherche = st.text_input("Recherche (titre ou message)")

if st.button("Réinitialiser les filtres"):
    st.rerun()

niveau_filtre = None if choix_niveau == "Tous" else next(n for n in NiveauAlerte if LIBELLES_NIVEAU[n] == choix_niveau)
statut_filtre = None
if choix_statut not in ("Toutes (actives)", "Toutes (y compris résolues/ignorées)"):
    statut_filtre = next(s for s in StatutAlerte if LIBELLES_STATUT[s] == choix_statut)

alertes = alert_service.lister_alertes(
    niveau=niveau_filtre, statut=statut_filtre, periode_id=options_periodes[choix_periode],
    enseignant_id=options_enseignants[choix_enseignant], terme=terme_recherche if terme_recherche.strip() else None,
)
if choix_statut == "Toutes (actives)":
    alertes = [a for a in alertes if a.statut not in (StatutAlerte.RESOLUE, StatutAlerte.IGNOREE)]

st.divider()

# =======================================================================
# Liste des alertes (section 17/44)
# =======================================================================
st.header(f"Alertes ({len(alertes)})")

periodes_par_id = {p.id: p for p in periodes}
enseignants_par_id = {e.id: e for e in enseignants}

if not alertes:
    st.info("Aucune alerte ne correspond aux critères sélectionnés.")
else:
    for alerte in alertes:
        with st.expander(f"{LIBELLES_NIVEAU[alerte.niveau]} — {alerte.titre} [{LIBELLES_STATUT[alerte.statut]}]"):
            st.markdown(badge_niveau_alerte(alerte.niveau), unsafe_allow_html=True)
            st.write(alerte.message)
            col_ctx1, col_ctx2, col_ctx3 = st.columns(3)
            libelle_periode_ctx = periodes_par_id[alerte.periode_id].libelle if alerte.periode_id in periodes_par_id else "—"
            libelle_enseignant_ctx = "—"
            if alerte.enseignant_id in enseignants_par_id:
                ens = enseignants_par_id[alerte.enseignant_id]
                libelle_enseignant_ctx = f"{ens.nom} {ens.prenom}"
            col_ctx1.caption(f"Période : {libelle_periode_ctx}")
            col_ctx2.caption(f"Enseignant : {libelle_enseignant_ctx}")
            col_ctx3.caption(f"Détecté le : {alerte.date_derniere_detection}")

            if peut_gerer and alerte.statut not in (StatutAlerte.RESOLUE, StatutAlerte.IGNOREE):
                col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                with col_b1:
                    if alerte.statut == StatutAlerte.NOUVELLE and st.button("Marquer lue", key=f"lue_{alerte.id}"):
                        alert_service.marquer_lue(alerte.id, utilisateur=st.session_state.get("username"))
                        st.rerun()
                with col_b2:
                    if alerte.statut in (StatutAlerte.NOUVELLE, StatutAlerte.LUE) and st.button("Acquitter", key=f"acq_{alerte.id}"):
                        alert_service.acquitter(alerte.id, utilisateur=st.session_state.get("username"))
                        st.rerun()
                with col_b3:
                    if st.button("Résoudre", key=f"res_{alerte.id}"):
                        try:
                            alert_service.resoudre(alerte.id, utilisateur=st.session_state.get("username"))
                            st.rerun()
                        except AlertServiceError as erreur:
                            st.error(str(erreur))
                with col_b4:
                    if st.button("Ignorer", key=f"ign_{alerte.id}"):
                        alert_service.ignorer(alerte.id, utilisateur=st.session_state.get("username"))
                        st.rerun()

st.divider()

# =======================================================================
# Export (section 45)
# =======================================================================
st.header("Export des alertes filtrées")
if alertes:
    lignes_export = []
    for a in alertes:
        libelle_ens = "—"
        if a.enseignant_id in enseignants_par_id:
            ens = enseignants_par_id[a.enseignant_id]
            libelle_ens = f"{ens.nom} {ens.prenom}"
        lignes_export.append({
            "Date": a.date_derniere_detection, "Niveau": a.niveau.value.upper(), "Type": a.type_alerte,
            "Message": a.message, "Enseignant": libelle_ens,
            "Période": periodes_par_id[a.periode_id].libelle if a.periode_id in periodes_par_id else "—",
            "Statut": a.statut.value, "Résolue par": a.resolue_par or "—",
        })
    tampon_brut = BytesIO()
    pd.DataFrame(lignes_export).to_excel(tampon_brut, index=False, engine="openpyxl")
    from openpyxl import load_workbook

    from exports.logo_excel import ajouter_logo

    tampon = BytesIO()
    ajouter_logo(load_workbook(tampon_brut)).save(tampon)
    st.download_button(
        "Télécharger (Excel)", data=tampon.getvalue(), file_name="alertes_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Aucune alerte à exporter.")
