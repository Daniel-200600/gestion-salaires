"""
Page Streamlit — Module 08 : Historique de paie.

Règle d'architecture stricte : aucune requête SQL, aucune formule de
calcul de salaire dans cette page. Toutes les données proviennent de
services/historique_paie_service.py, lui-même basé exclusivement sur
services/paie_service.py (aucune deuxième formule de gain, taxe ou net).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.initialization import init_database
from services import enseignant_service, historique_paie_service, periode_service
from services.comptabilite_service import ComptabiliteError
from utils.formatters import formater_fcfa, libelle_statut_periode

init_database()


from services import permission_service
from utils.session_auth import exiger_permission
from utils.ui_helpers import config_colonnes_montants

exiger_permission(permission_service.HISTORIQUE_CONSULTER)
st.title("Historique de paie")
st.caption("Consultation multi-périodes — les résultats affichés proviennent exclusivement du moteur de paie.")

# =======================================================================
# Sélection de l'enseignant
# =======================================================================
st.header("1. Enseignant")

tous_enseignants = enseignant_service.lister_enseignants(inclure_inactifs=True)
if not tous_enseignants:
    st.info("Aucune donnée disponible. Aucun enseignant n'est enregistré.")
    st.stop()

options_enseignants = {f"{e.nom} {e.prenom}": e.id for e in tous_enseignants}
choix_enseignant = st.selectbox("Sélectionner un enseignant", list(options_enseignants.keys()))
enseignant_id = options_enseignants[choix_enseignant]

st.divider()

# =======================================================================
# Sélection de la ou des périodes
# =======================================================================
st.header("2. Périodes à consulter")

periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

mode = st.radio(
    "Étendue de la consultation", ["Toutes les périodes disponibles", "Sélection de périodes"], horizontal=True
)

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
if mode == "Sélection de périodes":
    choix_libelles = st.multiselect("Période(s)", list(options_periodes.keys()))
    periode_ids = [options_periodes[libelle] for libelle in choix_libelles]
    if not periode_ids:
        st.info("Sélectionnez au moins une période.")
        st.stop()
else:
    periode_ids = None  # toutes les périodes

st.divider()

# =======================================================================
# 3. Historique
# =======================================================================
st.header("3. Historique")

lignes = historique_paie_service.historique_enseignant(enseignant_id, periode_ids=periode_ids)

if not lignes:
    st.info(
        "Aucune donnée de paie exploitable pour cet enseignant sur les périodes sélectionnées "
        "(périodes en brouillon ou sans aucune saisie ignorées)."
    )
    st.stop()

tableau = [
    {
        "Période": ligne.libelle_periode,
        "Statut": libelle_statut_periode(periode_service.obtenir_periode(ligne.periode_id).statut),
        "Heures": ligne.resultat.total_heures,
        "Gain": formater_fcfa(ligne.resultat.gain_heures),
        "Taxe": formater_fcfa(ligne.resultat.taxe_5),
        "Retenues": formater_fcfa(ligne.resultat.retenue_amicale + ligne.resultat.dette),
        "Dette": formater_fcfa(ligne.resultat.dette),
        "Net": formater_fcfa(ligne.resultat.net_a_percevoir),
        "Date de clôture": periode_service.obtenir_periode(ligne.periode_id).date_cloture or "—",
    }
    for ligne in lignes
]
st.dataframe(
    tableau, use_container_width=True, hide_index=True,
    column_config=config_colonnes_montants(["Gain", "Taxe", "Retenues", "Dette", "Net"]),
)

# =======================================================================
# Totaux sur l'historique consulté
# =======================================================================
st.header("Totaux sur la période consultée")
totaux = historique_paie_service.totaux_historique(lignes)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total heures", f"{totaux.total_heures:g} h")
col2.metric("Total gains", formater_fcfa(totaux.total_gain_heures))
col3.metric("Total taxe", formater_fcfa(totaux.total_taxe))
col4.metric("Total net", formater_fcfa(totaux.total_net_a_percevoir))

# =======================================================================
# Évolution du net sur l'historique consulté
# =======================================================================
if len(lignes) >= 2:
    st.subheader("Évolution du net à percevoir")
    df_graphique = pd.DataFrame(
        {"Net": [ligne.resultat.net_a_percevoir for ligne in lignes]},
        index=[ligne.libelle_periode for ligne in lignes],
    )
    st.line_chart(df_graphique)

st.divider()

# =======================================================================
# 4. Comparaison entre deux périodes (module 09)
# =======================================================================
st.header("Comparaison entre deux périodes")
st.caption("Compare les totaux globaux de deux périodes — aucune formule de paie recalculée, uniquement des écarts entre totaux déjà produits.")

col_periode_a, col_periode_b = st.columns(2)
with col_periode_a:
    choix_a = st.selectbox("Période A (référence)", list(options_periodes.keys()), key="comparaison_periode_a")
with col_periode_b:
    choix_b = st.selectbox("Période B", list(options_periodes.keys()), index=min(1, len(options_periodes) - 1), key="comparaison_periode_b")

if choix_a == choix_b:
    st.info("Sélectionnez deux périodes différentes pour lancer la comparaison.")
else:
    try:
        comparaison = historique_paie_service.comparer_periodes(
            options_periodes[choix_a], options_periodes[choix_b]
        )
        lignes_comparaison = []
        for indicateur in comparaison.indicateurs:
            variation_pct = indicateur.variation_pourcentage
            lignes_comparaison.append({
                "Indicateur": indicateur.libelle,
                f"{comparaison.periode_a.libelle}": f"{indicateur.valeur_a:g}",
                f"{comparaison.periode_b.libelle}": f"{indicateur.valeur_b:g}",
                "Écart absolu": f"{indicateur.variation_absolue:+g}",
                "Écart %": f"{variation_pct:+.1f} %" if variation_pct is not None else "—",
            })
        st.dataframe(
            lignes_comparaison, use_container_width=True, hide_index=True,
            column_config=config_colonnes_montants([
                comparaison.periode_a.libelle, comparaison.periode_b.libelle, "Écart absolu", "Écart %",
            ]),
        )
    except ComptabiliteError as erreur:
        st.info(str(erreur))
