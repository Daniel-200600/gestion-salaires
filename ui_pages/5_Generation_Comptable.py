"""
Page Streamlit — Module 06 : Génération comptable Excel.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de calcul de salaire, et ne génère AUCUN fichier
Excel directement. Elle appelle exclusivement
services/comptabilite_service.py (préparation des données, lui-même
basé sur services/paie_service.py) et exports/excel_export.py
(génération du classeur).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from exports.excel_export import generer_fichier_excel, generer_nom_fichier
from models.enums import StatutPeriode
from services import periode_service
from services.comptabilite_service import ComptabiliteError, preparer_etat_comptable
from utils.formatters import dates_periode, formater_fcfa, libelle_statut_periode

init_database()


from services import permission_service
from utils.session_auth import exiger_permission

exiger_permission(permission_service.EXPORT_GENERER)
st.title("Génération comptable Excel")
st.caption("Génère un état comptable Excel à partir des résultats déjà calculés par le moteur de paie.")

# =======================================================================
# Étape 1 — Sélection de la période
# =======================================================================
st.header("1. Sélection de la période")

periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période de paie", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)
date_debut, date_fin = dates_periode(periode.mois, periode.annee)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Libellé", periode.libelle)
col2.metric("Statut", libelle_statut_periode(periode.statut))
col3.metric("Du", date_debut.strftime("%d/%m/%Y"))
col4.metric("Au", date_fin.strftime("%d/%m/%Y"))

st.divider()

if periode.statut == StatutPeriode.BROUILLON:
    st.warning(
        "Cette période est encore au statut **Brouillon** : elle n'est pas prête pour un état "
        "comptable. Ouvrez-la d'abord dans « Gestion des périodes de paie »."
    )
    st.stop()

if periode.statut == StatutPeriode.OUVERTE:
    st.info(
        "Période **ouverte** : l'état généré sera **provisoire**, les données peuvent encore changer."
    )
elif periode.statut == StatutPeriode.VALIDEE:
    st.info("Période **validée** : l'état comptable généré est définitif.")
elif periode.statut == StatutPeriode.CLOTUREE:
    st.info("Période **clôturée** : consultation de l'état comptable historique, données figées.")

etablissement = st.text_input("Nom de l'établissement (figurera sur le document)", value="Établissement scolaire")

# =======================================================================
# Préparation de l'état comptable (toujours via comptabilite_service)
# =======================================================================
try:
    etat = preparer_etat_comptable(periode_id)
except ComptabiliteError as erreur:
    st.error(str(erreur))
    st.stop()

# =======================================================================
# Étape 2 — Nombre d'enseignants concernés
# =======================================================================
st.header("2. Enseignants concernés")
st.metric("Nombre d'enseignants", len(etat.resultats))

if etat.erreurs:
    details = "\n".join(f"- Enseignant id {eid} : {message}" for eid, message in etat.erreurs.items())
    st.warning(f"{len(etat.erreurs)} enseignant(s) n'ont pas pu être calculé(s) et seront absents du fichier :\n{details}")

st.divider()

# =======================================================================
# Étape 3 — Prévisualisation du tableau comptable
# =======================================================================
st.header("3. Prévisualisation")

lignes_apercu = [
    {
        "N°": numero,
        "Nom": r.nom,
        "Prénom": r.prenom,
        "Statut": r.statut.value,
        "Total heures": r.total_heures,
        "Taux horaire": formater_fcfa(r.taux_horaire),
        "Gain heures": formater_fcfa(r.gain_heures),
        "Base taxable": formater_fcfa(r.base_taxable),
        "Taxe 5 %": formater_fcfa(r.taxe_5),
        "Net à percevoir": formater_fcfa(r.net_a_percevoir),
    }
    for numero, r in enumerate(etat.resultats, start=1)
]
st.dataframe(lignes_apercu, use_container_width=True, hide_index=True)

col_t1, col_t2, col_t3 = st.columns(3)
col_t1.metric("Total heures", f"{etat.totaux.total_heures:g} h")
col_t2.metric("Total taxe (5 %)", formater_fcfa(etat.totaux.total_taxe))
col_t3.metric("Total net à percevoir", formater_fcfa(etat.totaux.total_net_a_percevoir))

st.divider()

# =======================================================================
# Étape 4 & 5 — Génération et téléchargement du fichier Excel
# =======================================================================
st.header("4. Génération du fichier Excel")

nom_fichier_previsualise = generer_nom_fichier(etat)
st.caption(f"Nom du fichier : `{nom_fichier_previsualise}`")

if st.button("Générer l'état comptable Excel", type="primary"):
    try:
        chemin_fichier = generer_fichier_excel(etat, etablissement=etablissement)
        with open(chemin_fichier, "rb") as fichier:
            contenu = fichier.read()
        st.success(f"Fichier généré avec succès : {chemin_fichier.name}")
        st.session_state["dernier_export_excel"] = {
            "nom": chemin_fichier.name,
            "contenu": contenu,
        }
    except ComptabiliteError as erreur:
        st.error(str(erreur))

# =======================================================================
# Étape 5 — Téléchargement (affiché si un export vient d'être généré)
# =======================================================================
dernier_export = st.session_state.get("dernier_export_excel")
if dernier_export:
    st.header("5. Téléchargement")
    st.download_button(
        "Télécharger le fichier Excel",
        data=dernier_export["contenu"],
        file_name=dernier_export["nom"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
