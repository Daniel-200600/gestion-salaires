"""
Page Streamlit — Module 17 : Statistiques & analyse décisionnelle.

Règle d'architecture stricte : cette page ne contient AUCUN calcul
statistique ni AUCUNE formule de paie. Toutes les données proviennent
de services/statistiques_service.py (lecture seule), lui-même basé
exclusivement sur les services existants (comptabilite_service,
reporting_paie_service, historique_paie_service).
"""

import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from services import enseignant_service, permission_service, periode_service, reporting_paie_service, statistiques_service
from services.comptabilite_service import ComptabiliteError, preparer_etat_comptable
from utils.formatters import formater_fcfa, libelle_sexe, libelle_statut, libelle_statut_periode
from utils.session_auth import exiger_permission, utilisateur_courant_role
from utils.ui_helpers import config_colonnes_montants

init_database()


exiger_permission(permission_service.STATISTIQUES_CONSULTER)

peut_exporter = permission_service.a_permission(utilisateur_courant_role(), permission_service.STATISTIQUES_EXPORTER)

st.title("Statistiques & analyse décisionnelle")
st.caption(
    "Analyse en lecture seule — s'appuie exclusivement sur les calculs déjà validés par le moteur de paie. "
    "Une valeur atypique n'est jamais automatiquement une erreur : elle invite simplement à vérifier."
)


def _fmt(valeur, decimales=1):
    return "—" if valeur is None else f"{valeur:.{decimales}f}"


# =======================================================================
# 1. Filtres
# =======================================================================
st.header("1. Filtres")

periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période de référence", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]

col_s, col_x = st.columns(2)
with col_s:
    choix_statut = st.selectbox("Statut", ["Tous", "Permanent", "Vacataire"])
with col_x:
    choix_sexe = st.selectbox("Sexe", ["Tous", "Masculin", "Féminin"])

try:
    etat = preparer_etat_comptable(periode_id)
    resultats_bruts = etat.resultats
except ComptabiliteError as erreur:
    st.info(f"Aucune donnée exploitable pour cette période : {erreur}")
    resultats_bruts = []

from models.enums import Sexe, StatutEnseignant
statut_filtre = {"Permanent": StatutEnseignant.PERMANENT, "Vacataire": StatutEnseignant.VACATAIRE}.get(choix_statut)
sexe_filtre = {"Masculin": Sexe.HOMME, "Féminin": Sexe.FEMME}.get(choix_sexe)
resultats = reporting_paie_service.filtrer_resultats(resultats_bruts, statut=statut_filtre, sexe=sexe_filtre)

st.divider()

# =======================================================================
# 2. Vue générale
# =======================================================================
st.header("2. Vue générale")
stats = statistiques_service.statistiques_generales(periode_id)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Enseignants", stats.nombre_enseignants_total)
col2.metric("Actifs", stats.nombre_enseignants_actifs)
col3.metric("Vacataires", stats.nombre_vacataires)
col4.metric("Permanents", stats.nombre_permanents)
col5.metric("Masse salariale brute", formater_fcfa(stats.masse_salariale_brute))

if not resultats:
    st.info("Aucune donnée disponible pour les critères sélectionnés.")
    st.stop()

st.divider()

# =======================================================================
# 3. Analyse des heures
# =======================================================================
st.header("3. Analyse des heures")
heures_desc = statistiques_service.calculer_statistique_descriptive([r.total_heures for r in resultats])
col1, col2, col3, col4 = st.columns(4)
col1.metric("Moyenne", f"{_fmt(heures_desc.moyenne)} h")
col2.metric("Médiane", f"{_fmt(heures_desc.mediane)} h")
col3.metric("Minimum", f"{_fmt(heures_desc.minimum)} h")
col4.metric("Maximum", f"{_fmt(heures_desc.maximum)} h")
if heures_desc.ecart_type is not None:
    st.caption(f"Écart-type : {_fmt(heures_desc.ecart_type)} h (sur {heures_desc.nombre} observations)")

st.bar_chart({"Heures": [r.total_heures for r in resultats]})

st.divider()

# =======================================================================
# 4. Analyse des rémunérations
# =======================================================================
st.header("4. Analyse des rémunérations")
net_desc = statistiques_service.calculer_statistique_descriptive([r.net_a_percevoir for r in resultats])
col1, col2, col3, col4 = st.columns(4)
col1.metric("Moyenne", formater_fcfa(int(net_desc.moyenne)) if net_desc.moyenne else "—")
col2.metric("Médiane", formater_fcfa(int(net_desc.mediane)) if net_desc.mediane else "—")
col3.metric("Minimum", formater_fcfa(int(net_desc.minimum)) if net_desc.minimum is not None else "—")
col4.metric("Maximum", formater_fcfa(int(net_desc.maximum)) if net_desc.maximum is not None else "—")

st.bar_chart({"Net à payer": [r.net_a_percevoir for r in resultats]})

st.divider()

# =======================================================================
# 5. Analyse par groupe
# =======================================================================
st.header("5. Analyse par groupe")
onglet_statut, onglet_sexe, onglet_croise = st.tabs(["Par statut", "Par sexe", "Statut × Sexe"])
with onglet_statut:
    groupes_statut = reporting_paie_service.synthese_detaillee_par_statut(resultats)
    st.dataframe([{"Groupe": g.libelle, "Effectif": g.nombre, "Heures": g.total_heures, "Net total": formater_fcfa(g.total_net), "Net moyen": formater_fcfa(g.total_net // g.nombre) if g.nombre else "—"} for g in groupes_statut], use_container_width=True, hide_index=True, column_config=config_colonnes_montants(["Net total", "Net moyen"]))
with onglet_sexe:
    groupes_sexe = reporting_paie_service.synthese_detaillee_par_sexe(resultats)
    st.dataframe([{"Groupe": g.libelle, "Effectif": g.nombre, "Heures": g.total_heures, "Net total": formater_fcfa(g.total_net), "Net moyen": formater_fcfa(g.total_net // g.nombre) if g.nombre else "—"} for g in groupes_sexe], use_container_width=True, hide_index=True, column_config=config_colonnes_montants(["Net total", "Net moyen"]))
with onglet_croise:
    groupes_croises = statistiques_service.synthese_croisee_statut_sexe(resultats)
    st.dataframe([{"Groupe": g.libelle, "Effectif": g.nombre, "Heures": g.total_heures, "Net total": formater_fcfa(g.total_net)} for g in groupes_croises], use_container_width=True, hide_index=True, column_config=config_colonnes_montants(["Net total"]))

st.divider()

# =======================================================================
# 6. Évolution temporelle
# =======================================================================
st.header("6. Évolution temporelle")
choix_periodes_evolution = st.multiselect(
    "Périodes à comparer (chronologique)", list(options_periodes.keys()),
    default=[choix_periode_libelle] if len(periodes) == 1 else list(options_periodes.keys())[:min(3, len(periodes))],
)
points_periodes = None
if len(choix_periodes_evolution) >= 1:
    ids_choisis = [options_periodes[c] for c in choix_periodes_evolution]
    points_periodes = statistiques_service.analyser_periodes(ids_choisis)
    st.dataframe([
        {
            "Période": p.periode.libelle, "Enseignants": p.nombre_enseignants,
            "Masse brute": formater_fcfa(p.masse_salariale_brute), "Net total": formater_fcfa(p.total_net),
            "Variation nette": formater_fcfa(p.variation_net_absolue) if p.variation_net_absolue is not None else "—",
            "Variation %": f"{p.variation_net_pourcentage:+.1f} %" if p.variation_net_pourcentage is not None else "—",
        }
        for p in points_periodes
    ], use_container_width=True, hide_index=True, column_config=config_colonnes_montants(["Masse brute", "Net total", "Variation nette", "Variation %"]))
    if len(points_periodes) > 1:
        st.line_chart({"Masse salariale brute": [p.masse_salariale_brute for p in points_periodes]})
else:
    st.info("Sélectionnez au moins une période pour l'analyse d'évolution.")

st.divider()

# =======================================================================
# 7. Analyse des composantes
# =======================================================================
st.header("7. Analyse des composantes")
composantes = statistiques_service.analyser_composantes(resultats)
st.dataframe([{"Composante": c.libelle, "Montant": formater_fcfa(c.montant_total), "Part": f"{c.part_pourcentage:.1f} %" if c.part_pourcentage is not None else "—"} for c in composantes], use_container_width=True, hide_index=True, column_config=config_colonnes_montants(["Montant", "Part"]))
composante_principale = max(composantes, key=lambda c: c.montant_total, default=None)
if composante_principale and composante_principale.montant_total > 0:
    st.caption(f"Composante la plus importante : **{composante_principale.libelle}** ({_fmt(composante_principale.part_pourcentage)} % du brut).")

st.divider()

# =======================================================================
# 8. Valeurs atypiques
# =======================================================================
st.header("8. Valeurs atypiques")
st.caption("Méthode IQR (écart interquartile) — une valeur signalée n'est pas nécessairement une erreur, elle mérite simplement d'être vérifiée.")
champ_outlier = st.selectbox("Champ analysé", ["net_a_percevoir", "taux_horaire", "total_heures", "gain_heures"], format_func=lambda c: {"net_a_percevoir": "Net à payer", "taux_horaire": "Taux horaire", "total_heures": "Heures", "gain_heures": "Gain"}[c])
outliers = statistiques_service.detecter_valeurs_atypiques(resultats, champ_outlier)
if not outliers:
    st.info("Aucune valeur atypique détectée (ou données insuffisantes pour une détection significative).")
else:
    st.dataframe([{"Enseignant": f"{o.nom} {o.prenom}", "Valeur": o.valeur, "Borne basse": round(o.borne_basse, 1), "Borne haute": round(o.borne_haute, 1), "Niveau": o.niveau} for o in outliers], use_container_width=True, hide_index=True)

st.divider()

# =======================================================================
# 9. Analyse individuelle
# =======================================================================
st.header("9. Analyse individuelle")
options_enseignants_dispo = {f"{r.nom} {r.prenom}": r for r in resultats}
if options_enseignants_dispo:
    choix_ens = st.selectbox("Enseignant", list(options_enseignants_dispo.keys()))
    resultat_choisi = options_enseignants_dispo[choix_ens]
    ecarts = statistiques_service.comparer_enseignant_au_groupe(resultat_choisi, resultats)
    st.dataframe([
        {
            "Indicateur": e.libelle, "Enseignant": round(e.valeur_enseignant, 1), "Moyenne groupe": round(e.valeur_groupe, 1),
            "Écart": round(e.ecart_absolu, 1), "Écart %": f"{e.ecart_pourcentage:+.1f} %" if e.ecart_pourcentage is not None else "—",
        }
        for e in ecarts
    ], use_container_width=True, hide_index=True, column_config=config_colonnes_montants(["Enseignant", "Moyenne groupe", "Écart", "Écart %"]))

    with st.expander("Historique multi-périodes de cet enseignant"):
        from services import historique_paie_service
        enseignant_obj = next((e for e in enseignant_service.lister_enseignants(inclure_inactifs=True) if e.nom == resultat_choisi.nom and e.prenom == resultat_choisi.prenom), None)
        if enseignant_obj:
            historique = historique_paie_service.historique_enseignant(enseignant_obj.id)
            if historique:
                st.dataframe([{"Période": h.libelle_periode, "Heures": h.resultat.total_heures, "Net": formater_fcfa(h.resultat.net_a_percevoir)} for h in historique], use_container_width=True, hide_index=True, column_config=config_colonnes_montants(["Net"]))
            else:
                st.info("Aucun historique disponible pour cet enseignant.")
else:
    st.info("Aucun enseignant disponible pour l'analyse individuelle avec les filtres actuels.")

st.divider()

# =======================================================================
# 10. Export
# =======================================================================
st.header("10. Export")
if not peut_exporter:
    st.info("Vous n'avez pas la permission d'exporter les statistiques (consultation seule).")
else:
    if st.button("Générer l'export Excel", type="primary"):
        from exports.statistiques_export import generer_fichier_statistiques

        groupes_statut_export = reporting_paie_service.synthese_detaillee_par_statut(resultats)
        groupes_sexe_export = reporting_paie_service.synthese_detaillee_par_sexe(resultats)
        chemin_export = generer_fichier_statistiques(
            stats, resultats, groupes_statut_export, groupes_sexe_export, composantes,
            outliers=outliers, points_periodes=points_periodes,
        )
        with open(chemin_export, "rb") as fichier:
            st.download_button(
                f"Télécharger {chemin_export.name}", data=fichier.read(), file_name=chemin_export.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
