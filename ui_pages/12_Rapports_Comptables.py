"""
Page Streamlit — Module 13 : Rapports comptables et rapprochement.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de calcul de salaire. Toutes les données
proviennent de services/reporting_paie_service.py (lecture seule,
lui-même basé sur services/comptabilite_service.py et
services/paie_service.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from database.repositories import audit_log_repository
from models.audit_log import AuditLog
from models.enums import TypeActionAudit
from services import periode_service, permission_service, reporting_paie_service
from services.comptabilite_service import ComptabiliteError
from services.historique_paie_service import comparer_periodes
from utils.formatters import (
    formater_fcfa,
    libelle_sexe,
    libelle_statut,
    libelle_statut_periode,
    sexe_depuis_libelle,
    statut_depuis_libelle,
)
from utils.session_auth import exiger_permission, utilisateur_courant_role
from utils.ui_helpers import config_colonnes_montants

init_database()


exiger_permission(permission_service.REPORTING_CONSULTER)

peut_exporter = permission_service.a_permission(utilisateur_courant_role(), permission_service.REPORTING_EXPORTER)

st.title("Rapports comptables")
st.caption(
    "Reporting financier de la paie — lecture seule, aucune donnée n'est modifiée ici. "
    "Toutes les valeurs proviennent du moteur de paie déjà validé."
)

# =======================================================================
# 1. Sélection de la période et des filtres
# =======================================================================
periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)

col_statut, col_sexe = st.columns(2)
with col_statut:
    choix_statut = st.selectbox("Statut", ["Tous", "Permanent", "Vacataire"])
with col_sexe:
    choix_sexe = st.selectbox("Sexe", ["Tous", "Masculin", "Féminin"])

try:
    rapport = reporting_paie_service.construire_etat_paie_complet(
        periode_id, etablissement="Établissement scolaire", utilisateur=st.session_state.get("username")
    )
except ComptabiliteError as erreur:
    st.info(str(erreur))
    st.stop()

# Filtres statut/sexe appliqués sur les résultats déjà calculés (aucun recalcul).
resultats_filtres = reporting_paie_service.filtrer_resultats(
    rapport.etat_comptable.resultats,
    statut=statut_depuis_libelle(choix_statut) if choix_statut != "Tous" else None,
    sexe=sexe_depuis_libelle(choix_sexe) if choix_sexe != "Tous" else None,
)

st.divider()

# =======================================================================
# 2. Synthèse générale
# =======================================================================
st.header("État général de la période")

etat = rapport.etat_comptable
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Enseignants", len(etat.resultats))
col2.metric("Total heures", f"{etat.totaux.total_heures:g} h")
col3.metric("Total brut", formater_fcfa(etat.totaux.total_gain_heures + etat.totaux.total_primes))
col4.metric("Total taxe", formater_fcfa(etat.totaux.total_taxe))
col5.metric("Total net à payer", formater_fcfa(etat.totaux.total_net_a_percevoir))

if rapport.rapprochement.toutes_ok:
    st.success("Rapprochement conforme : écart de 0 FCFA.")
else:
    st.error("Écart détecté : consultez la section Rapprochement ci-dessous.")

st.divider()

# =======================================================================
# 3. Tableau détaillé (filtré)
# =======================================================================
st.header("Détail par enseignant")
if not resultats_filtres:
    st.info("Aucun enseignant ne correspond aux critères sélectionnés.")
else:
    lignes_detail = [
        {
            "Nom": r.nom, "Prénom": r.prenom, "Sexe": libelle_sexe(r.sexe), "Statut": libelle_statut(r.statut),
            "Heures": r.total_heures, "Taux horaire": formater_fcfa(r.taux_horaire),
            "Gain": formater_fcfa(r.gain_heures), "AP/PP": formater_fcfa(r.prime_ap_pp),
            "Surveillance": formater_fcfa(r.surveillance_secretariat),
            "Indemnité": formater_fcfa(r.indemnite_suggestion_admin),
            "Base taxable": formater_fcfa(r.base_taxable), "Taxe": formater_fcfa(r.taxe_5),
            "Retenue amicale": formater_fcfa(r.retenue_amicale), "Dette": formater_fcfa(r.dette),
            "Net à payer": formater_fcfa(r.net_a_percevoir),
        }
        for r in resultats_filtres
    ]
    st.dataframe(
        lignes_detail, use_container_width=True, hide_index=True,
        column_config=config_colonnes_montants([
            "Taux horaire", "Gain", "AP/PP", "Surveillance", "Indemnité",
            "Base taxable", "Taxe", "Retenue amicale", "Dette", "Net à payer",
        ]),
    )

st.divider()

# =======================================================================
# 4. Classement
# =======================================================================
st.header("Classement des enseignants")
col_critere, col_ordre = st.columns(2)
with col_critere:
    libelles_criteres = {
        "Net à payer": "net_a_percevoir", "Gain": "gain", "Base taxable": "base_taxable", "Heures": "total_heures",
    }
    choix_critere = st.selectbox("Classer par", list(libelles_criteres.keys()))
with col_ordre:
    ordre_decroissant = st.selectbox("Ordre", ["Décroissant", "Croissant"]) == "Décroissant"

if resultats_filtres:
    critere_technique = libelles_criteres[choix_critere]
    classement = reporting_paie_service.classer_enseignants(
        resultats_filtres, critere=critere_technique, decroissant=ordre_decroissant
    )
    lignes_classement = []
    for i, r in enumerate(classement, start=1):
        valeur = getattr(r, critere_technique)
        valeur_affichee = f"{valeur:g} h" if critere_technique == "total_heures" else formater_fcfa(valeur)
        lignes_classement.append({"Rang": i, "Nom complet": f"{r.nom} {r.prenom}", choix_critere: valeur_affichee})
    st.dataframe(
        lignes_classement, use_container_width=True, hide_index=True,
        column_config=config_colonnes_montants([choix_critere]),
    )

st.divider()

# =======================================================================
# 5. Synthèses par statut / sexe
# =======================================================================
st.header("Synthèses par groupe")
col_stat, col_sx = st.columns(2)
with col_stat:
    st.markdown("**Par statut**")
    lignes_stat = [
        {
            "Statut": g.libelle, "Effectif": g.nombre, "Heures": g.total_heures,
            "Gains": formater_fcfa(g.total_gain_heures), "Net": formater_fcfa(g.total_net),
        }
        for g in rapport.synthese_statut
    ]
    st.dataframe(
        lignes_stat, use_container_width=True, hide_index=True,
        column_config=config_colonnes_montants(["Gains", "Net"]),
    )
with col_sx:
    st.markdown("**Par sexe** *(descriptif uniquement)*")
    lignes_sx = [
        {
            "Sexe": g.libelle, "Effectif": g.nombre, "Heures": g.total_heures,
            "Gains": formater_fcfa(g.total_gain_heures), "Net": formater_fcfa(g.total_net),
        }
        for g in rapport.synthese_sexe
    ]
    st.dataframe(
        lignes_sx, use_container_width=True, hide_index=True,
        column_config=config_colonnes_montants(["Gains", "Net"]),
    )

st.divider()

# =======================================================================
# 6. État des retenues
# =======================================================================
st.header("État des retenues")
lignes_retenues = [
    {
        "Enseignant": f"{r.nom} {r.prenom}", "Taxe": formater_fcfa(r.taxe),
        "Retenue amicale": formater_fcfa(r.retenue_amicale), "Dette": formater_fcfa(r.dette),
        "Total retenues": formater_fcfa(r.total_retenues), "Net": formater_fcfa(r.net),
    }
    for r in rapport.retenues
]
if lignes_retenues:
    st.dataframe(
        lignes_retenues, use_container_width=True, hide_index=True,
        column_config=config_colonnes_montants(["Taxe", "Retenue amicale", "Dette", "Total retenues", "Net"]),
    )
else:
    st.info("Aucune retenue à afficher pour cette période.")

st.divider()

# =======================================================================
# 7. Rapprochement
# =======================================================================
st.header("Rapprochement")
if st.button("Exécuter le rapprochement"):
    entree_audit = AuditLog(
        type_action=TypeActionAudit.RAPPROCHEMENT_EXECUTE,
        entite="periode_paie", entite_id=periode_id,
        utilisateur=st.session_state.get("username"),
        details=f"{periode.libelle} — {'OK' if rapport.rapprochement.toutes_ok else 'Écart détecté'}",
    )
    audit_log_repository.enregistrer(entree_audit)
    st.rerun()

lignes_rapprochement = [
    {
        "Élément": l.element, "Montant attendu": formater_fcfa(l.montant_attendu),
        "Montant enregistré": formater_fcfa(l.montant_enregistre), "Écart": formater_fcfa(l.ecart),
        "Statut": l.statut.value,
    }
    for l in rapport.rapprochement.lignes
]
st.dataframe(lignes_rapprochement, use_container_width=True, hide_index=True)

if rapport.observations:
    for observation in rapport.observations:
        st.caption(f"• {observation}")

st.divider()

# =======================================================================
# 8. Comparaison entre périodes
# =======================================================================
st.header("Comparaison entre périodes")
autres_periodes = {k: v for k, v in options_periodes.items() if v != periode_id}
comparaison = None
if autres_periodes:
    choix_periode_b = st.selectbox("Comparer avec", list(autres_periodes.keys()))
    try:
        comparaison = comparer_periodes(periode_id, autres_periodes[choix_periode_b])
        lignes_comparaison = [
            {
                "Indicateur": i.libelle,
                comparaison.periode_a.libelle: f"{i.valeur_a:g}",
                comparaison.periode_b.libelle: f"{i.valeur_b:g}",
                "Variation": f"{i.variation_absolue:+g}",
                "Variation %": f"{i.variation_pourcentage:+.1f} %" if i.variation_pourcentage is not None else "—",
            }
            for i in comparaison.indicateurs
        ]
        st.dataframe(lignes_comparaison, use_container_width=True, hide_index=True)

        observations_variations = reporting_paie_service.analyser_variations(comparaison)
        if observations_variations:
            st.markdown(f"**Évolutions notables (seuil {reporting_paie_service.SEUIL_VARIATION_NOTABLE_POURCENT:g} %)**")
            for obs in observations_variations:
                st.warning(obs)
    except ComptabiliteError as erreur:
        st.info(str(erreur))
        comparaison = None
else:
    st.info("Une seule période disponible : aucune comparaison possible.")

st.divider()

# =======================================================================
# 9. Export Excel complet
# =======================================================================
st.header("Export de l'état de paie")
if not peut_exporter:
    st.info("Vous n'avez pas la permission d'exporter (consultation seule).")
else:
    if st.button("Générer l'état de paie Excel", type="primary"):
        from exports.reporting_export import generer_fichier_etat_paie

        chemin_export = generer_fichier_etat_paie(rapport, comparaison=comparaison)

        audit_log_repository.enregistrer(AuditLog(
            type_action=TypeActionAudit.REPORTING_EXPORTE,
            entite="periode_paie", entite_id=periode_id,
            utilisateur=st.session_state.get("username"),
            details=f"{periode.libelle} — {chemin_export.name}",
        ))

        with open(chemin_export, "rb") as fichier:
            st.download_button(
                f"Télécharger {chemin_export.name}",
                data=fichier.read(),
                file_name=chemin_export.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
