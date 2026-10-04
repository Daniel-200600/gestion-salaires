"""
Page Streamlit — Module 09 : Contrôle de la paie.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de calcul de salaire. Toutes les données
proviennent de services/controle_paie_service.py (contrôle, validation
et clôture avec contrôle) et services/comptabilite_service.py
(synthèse déjà calculée), eux-mêmes entièrement basés sur
services/paie_service.py.

C'est l'écran central de préparation d'une paie : vue synthétique de
la période, détection d'anomalies (erreurs bloquantes / avertissements),
puis validation et clôture contrôlées avec confirmation explicite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from utils.formatters import formater_taxe_periode

from database.initialization import init_database
from models.enums import StatutPeriode
from services import bulletin_service, comptabilite_service, periode_service
from services.comptabilite_service import ComptabiliteError
from services.controle_paie_service import (
    ControlePaieError,
    NiveauAnomalie,
    cloturer_periode_avec_controle,
    controler_periode,
    statistiques_net,
    valider_periode_avec_controle,
)
from utils.formatters import formater_fcfa, libelle_statut_periode

init_database()


from services import permission_service
from utils.session_auth import exiger_permission, utilisateur_courant_role

exiger_permission(permission_service.PAIE_CONTROLER)
peut_valider = permission_service.a_permission(utilisateur_courant_role(), permission_service.PAIE_VALIDER)
peut_cloturer = permission_service.a_permission(utilisateur_courant_role(), permission_service.PAIE_CLOTURER)
st.title("Contrôle de la paie")
st.caption(
    "Vérifie la cohérence et la complétude des données avant validation — "
    "aucune formule de salaire n'est recalculée ici, tout provient du moteur de paie."
)

# =======================================================================
# 1. Sélection de la période
# =======================================================================
periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période à contrôler", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)

st.divider()

if periode.statut == StatutPeriode.BROUILLON:
    st.warning(
        "Cette période est encore au statut **Brouillon** : elle n'est pas prête pour un contrôle. "
        "Ouvrez-la d'abord dans « Gestion des périodes de paie »."
    )
    st.stop()

# =======================================================================
# 2. Écran de préparation — synthèse de la période
# =======================================================================
try:
    etat = comptabilite_service.preparer_etat_comptable(periode_id)
except ComptabiliteError as erreur:
    st.info(str(erreur))
    st.stop()

rapport = controler_periode(periode_id)

st.header("Synthèse de la période")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Statut", libelle_statut_periode(periode.statut))
col2.metric("Enseignants", rapport.nombre_enseignants)
col3.metric("Données conformes", rapport.nombre_conformes)
col4.metric("Enseignants incomplets/en erreur", len({a.enseignant_id for a in rapport.erreurs if a.enseignant_id}))

col5, col6, col7, col8, col9 = st.columns(5)
col5.metric("Total heures", f"{etat.totaux.total_heures:g} h")
col6.metric("Masse salariale brute", formater_fcfa(etat.totaux.total_gain_heures + etat.totaux.total_primes))
col7.metric(f"Total taxe ({formater_taxe_periode(periode)})", formater_fcfa(etat.totaux.total_taxe))
col8.metric("Total retenues", formater_fcfa(etat.totaux.total_retenues))
col9.metric("Total net à payer", formater_fcfa(etat.totaux.total_net_a_percevoir))
st.caption(f"dont total dettes : {formater_fcfa(etat.totaux.total_dette)}")

stats = statistiques_net(etat.resultats)
col_moy, col_med, col_min, col_max = st.columns(4)
col_moy.metric("Net moyen", formater_fcfa(round(stats.moyenne)))
col_med.metric("Net médian", formater_fcfa(round(stats.mediane)))
col_min.metric("Net minimum", formater_fcfa(stats.minimum))
col_max.metric("Net maximum", formater_fcfa(stats.maximum))

st.divider()

# =======================================================================
# 3. Résultat du contrôle
# =======================================================================
st.header("Résultat du contrôle")

col_e, col_a, col_c = st.columns(3)
col_e.metric("Erreurs bloquantes", len(rapport.erreurs))
col_a.metric("Avertissements", len(rapport.avertissements))
col_c.metric("Lignes conformes", rapport.nombre_conformes)

if rapport.est_bloque:
    st.error(
        f"{len(rapport.erreurs)} erreur(s) bloquante(s) détectée(s). "
        "La validation de cette période est impossible tant qu'elles ne sont pas corrigées."
    )
elif rapport.avertissements:
    st.warning(f"Aucune erreur bloquante, mais {len(rapport.avertissements)} avertissement(s) à examiner.")
else:
    st.success("Contrôle conforme : aucune anomalie détectée. Cette période est prête pour la validation.")

# --- Filtres et tableau des anomalies ---
if rapport.anomalies:
    filtre = st.radio("Filtrer les anomalies", ["Toutes", "Erreurs", "Avertissements"], horizontal=True)
    if filtre == "Erreurs":
        anomalies_affichees = rapport.erreurs
    elif filtre == "Avertissements":
        anomalies_affichees = rapport.avertissements
    else:
        anomalies_affichees = rapport.anomalies

    lignes_anomalies = [
        {
            "Enseignant": a.enseignant_nom or "—",
            "Problème": a.message,
            "Niveau": "Erreur" if a.niveau == NiveauAnomalie.ERREUR else "Avertissement",
            "Valeur": a.valeur or "—",
            "Recommandation": a.recommandation or "—",
        }
        for a in anomalies_affichees
    ]
    st.dataframe(lignes_anomalies, use_container_width=True, hide_index=True)
else:
    st.info("Aucune anomalie à afficher.")

st.divider()

# =======================================================================
# 4. Tableau récapitulatif (contrôle + bulletin par enseignant)
# =======================================================================
st.header("Tableau récapitulatif")

etats_bulletins = {
    r.enseignant_id: bulletin_service.bulletin_deja_genere(r.nom, r.prenom, periode.libelle)
    for r in etat.resultats
}
enseignants_avec_erreur = {a.enseignant_id for a in rapport.erreurs if a.enseignant_id}
enseignants_avec_avertissement = {a.enseignant_id for a in rapport.avertissements if a.enseignant_id}

lignes_recap = []
for r in etat.resultats:
    if r.enseignant_id in enseignants_avec_erreur:
        etat_controle = "Erreur"
    elif r.enseignant_id in enseignants_avec_avertissement:
        etat_controle = "Avertissement"
    else:
        etat_controle = "Conforme"
    lignes_recap.append({
        "Nom complet": f"{r.nom} {r.prenom}",
        "Sexe": r.sexe.value,
        "Statut": r.statut.value,
        "Heures S1": r.semaine_1, "Heures S2": r.semaine_2, "Heures S3": r.semaine_3,
        "Heures S4": r.semaine_4, "Heures S5": r.semaine_5,
        "Total heures": r.total_heures,
        "Taux horaire": formater_fcfa(r.taux_horaire),
        "Gain": formater_fcfa(r.gain_heures),
        "AP/PP": formater_fcfa(r.prime_ap_pp),
        "Surveillance/Secrétariat": formater_fcfa(r.surveillance_secretariat),
        "Indemnité": formater_fcfa(r.indemnite_suggestion_admin),
        "Base taxable": formater_fcfa(r.base_taxable),
        "Taxe": formater_fcfa(r.taxe_5),
        "Retenue amicale": formater_fcfa(r.retenue_amicale),
        "Dette": formater_fcfa(r.dette),
        "Net à payer": formater_fcfa(r.net_a_percevoir),
        "État du contrôle": etat_controle,
        "Bulletin disponible": "Oui" if etats_bulletins.get(r.enseignant_id) else "Non",
    })
st.dataframe(lignes_recap, use_container_width=True, hide_index=True)

st.divider()

# =======================================================================
# 5. Validation / Clôture avec contrôle et confirmation explicite
# =======================================================================
st.header("Validation et clôture")

if periode.statut == StatutPeriode.OUVERTE:
    if not peut_valider:
        st.info("Vous n'avez pas la permission de valider une période (consultation seule).")
    elif rapport.est_bloque:
        st.error("La validation est désactivée tant que des erreurs bloquantes subsistent.")
    else:
        cle_confirmation_validation = f"confirmation_validation_{periode_id}"
        if not st.session_state.get(cle_confirmation_validation, False):
            if st.button("Valider cette période", type="primary"):
                st.session_state[cle_confirmation_validation] = True
                st.rerun()
        else:
            st.warning(
                f"Confirmez-vous la validation de la période **{periode.libelle}** ? "
                "Les données de paie seront gelées."
            )
            col_confirmer, col_annuler = st.columns(2)
            with col_confirmer:
                if st.button("Confirmer la validation", type="primary"):
                    try:
                        valider_periode_avec_controle(
                            periode_id, confirmation=True, utilisateur=st.session_state.get("username")
                        )
                        st.session_state.pop(cle_confirmation_validation, None)
                        st.success("Période validée avec succès.")
                        st.rerun()
                    except ControlePaieError as erreur:
                        st.session_state.pop(cle_confirmation_validation, None)
                        st.error(str(erreur))
            with col_annuler:
                if st.button("Annuler"):
                    st.session_state.pop(cle_confirmation_validation, None)
                    st.rerun()

elif periode.statut == StatutPeriode.VALIDEE:
    if not peut_cloturer:
        st.info("Vous n'avez pas la permission de clôturer une période (réservée aux administrateurs).")
    elif rapport.est_bloque:
        st.error("La clôture est désactivée tant que des erreurs bloquantes subsistent.")
    else:
        cle_confirmation_cloture = f"confirmation_cloture_{periode_id}"
        if not st.session_state.get(cle_confirmation_cloture, False):
            if st.button("Clôturer cette période", type="primary"):
                st.session_state[cle_confirmation_cloture] = True
                st.rerun()
        else:
            st.warning(
                f"Confirmez-vous la clôture définitive de la période **{periode.libelle}** ? "
                "Cette opération est irréversible."
            )
            col_confirmer, col_annuler = st.columns(2)
            with col_confirmer:
                if st.button("Confirmer la clôture", type="primary"):
                    try:
                        cloturer_periode_avec_controle(
                            periode_id, confirmation=True, utilisateur=st.session_state.get("username")
                        )
                        st.session_state.pop(cle_confirmation_cloture, None)
                        st.success("Période clôturée définitivement.")
                        st.rerun()
                    except ControlePaieError as erreur:
                        st.session_state.pop(cle_confirmation_cloture, None)
                        st.error(str(erreur))
            with col_annuler:
                if st.button("Annuler"):
                    st.session_state.pop(cle_confirmation_cloture, None)
                    st.rerun()

else:  # CLOTUREE
    st.info("Cette période est clôturée. Les données sont historiques et consultables, mais non modifiables.")
