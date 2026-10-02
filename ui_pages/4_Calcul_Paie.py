"""
Page Streamlit — Module 05 : Calcul de paie.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de calcul de salaire. Tous les calculs
(individuels, groupés, totaux) proviennent exclusivement de
services/paie_service.py. Aucun export (Excel/Word) ni génération de
bulletin définitif n'est effectué ici : ce module se limite à la
prévisualisation à l'écran.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from utils.formatters import formater_taux_taxe

from database.initialization import init_database
from models.enums import StatutPeriode
from services import enseignant_service, heures_service, periode_service, remuneration_service, retenue_service
from services.paie_service import CalculPaieError, calculer_paie_groupe, calculer_totaux_groupe
from utils.formatters import formater_fcfa, libelle_statut, libelle_statut_periode

init_database()


from services import permission_service
from utils.session_auth import exiger_permission

exiger_permission(permission_service.PAIE_CONSULTER)
st.title("Calcul de paie")
st.caption("Prévisualisation du calcul — aucun bulletin n'est encore généré à cette étape.")

# =======================================================================
# 1. Sélection de la période
# =======================================================================
periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période de paie", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)

st.divider()

if periode.statut == StatutPeriode.BROUILLON:
    st.warning(
        "Cette période est encore au statut **Brouillon** : elle n'est pas prête pour un calcul "
        "de paie. Ouvrez-la d'abord dans « Gestion des périodes de paie »."
    )
    st.stop()

if periode.statut == StatutPeriode.OUVERTE:
    st.info("Période **ouverte** : ce calcul est une simple prévisualisation, les données peuvent encore changer.")
elif periode.statut == StatutPeriode.VALIDEE:
    st.info("Période **validée** : ce calcul prépare la future génération des bulletins.")
elif periode.statut == StatutPeriode.CLOTUREE:
    st.info("Période **clôturée** : ce calcul porte sur des données historiques figées.")

# =======================================================================
# 2. Sélection des enseignants
# =======================================================================
heures_existantes = heures_service.lister_heures_periode(periode_id)
remuneration_existante = remuneration_service.lister_remuneration_periode(periode_id)
retenues_existantes = retenue_service.lister_retenues_periode(periode_id)
ids_avec_donnees = set(heures_existantes) | set(remuneration_existante) | set(retenues_existantes)

tous_enseignants = enseignant_service.lister_enseignants(inclure_inactifs=True)
enseignants_disponibles = [e for e in tous_enseignants if e.id in ids_avec_donnees]

if not enseignants_disponibles:
    st.info("Aucune donnée disponible : aucune donnée de paie n'a été saisie pour cette période (voir Paie › Données de paie).")
    st.stop()

options_enseignants = {f"{e.nom} {e.prenom}": e.id for e in enseignants_disponibles}
enseignants_choisis_libelles = st.multiselect(
    "Sélectionner un ou plusieurs enseignants",
    list(options_enseignants.keys()),
    default=list(options_enseignants.keys()),
)
enseignant_ids = [options_enseignants[libelle] for libelle in enseignants_choisis_libelles]

if not enseignant_ids:
    st.info("Sélectionnez au moins un enseignant pour lancer un calcul.")
    st.stop()

st.divider()

# =======================================================================
# 3. Lancement du calcul
# =======================================================================
if st.button("Lancer le calcul", type="primary"):
    try:
        groupe = calculer_paie_groupe(periode_id, enseignant_ids)
    except CalculPaieError as erreur:
        st.error(str(erreur))
        st.stop()

    if groupe.erreurs:
        details = "\n".join(f"- Enseignant id {eid} : {message}" for eid, message in groupe.erreurs.items())
        st.warning(f"Certains enseignants n'ont pas pu être calculés :\n{details}")

    if not groupe.resultats:
        st.info("Aucun résultat à afficher.")
        st.stop()

    # ---------------------------------------------------------------
    # 4. Tableau des résultats
    # ---------------------------------------------------------------
    st.subheader("Résultats")
    lignes = [
        {
            "Nom": r.nom,
            "Prénom": r.prenom,
            "Statut": libelle_statut(r.statut),
            "Total heures": r.total_heures,
            "Taux horaire": formater_fcfa(r.taux_horaire),
            "Gain heures": formater_fcfa(r.gain_heures),
            "Prime AP/PP": formater_fcfa(r.prime_ap_pp),
            "Surveillance/Secrétariat": formater_fcfa(r.surveillance_secretariat),
            "Indemnité suggestion/admin": formater_fcfa(r.indemnite_suggestion_admin),
            "Taxe": formater_fcfa(r.taxe_5),
            "Retenue amicale": formater_fcfa(r.retenue_amicale),
            "Dette": formater_fcfa(r.dette),
            "Net à percevoir": formater_fcfa(r.net_a_percevoir),
        }
        for r in groupe.resultats
    ]
    st.dataframe(lignes, use_container_width=True, hide_index=True)

    # ---------------------------------------------------------------
    # 5. Totaux globaux
    # ---------------------------------------------------------------
    st.subheader("Totaux globaux")
    totaux = calculer_totaux_groupe(groupe.resultats)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total heures", f"{totaux.total_heures:g} h")
    col2.metric("Total gains", formater_fcfa(totaux.total_gain_heures))
    col3.metric("Total primes", formater_fcfa(totaux.total_primes))

    col4, col5, col6 = st.columns(3)
    col4.metric(f"Total taxe ({formater_taux_taxe(periode.taux_taxe)})", formater_fcfa(totaux.total_taxe))
    col5.metric("Total retenues", formater_fcfa(totaux.total_retenues))
    col6.metric("Total net à percevoir", formater_fcfa(totaux.total_net_a_percevoir))
