"""
Page Streamlit — Module 08 : Tableau de bord.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de calcul de salaire. Toutes les données
proviennent de services/dashboard_service.py, lui-même entièrement
basé sur services/paie_service.py (via services/comptabilite_service.py)
et sur les systèmes déjà existants des modules 02 à 07 — aucune
nouvelle formule, aucune nouvelle génération Excel/Word.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.initialization import init_database
from services import bulletin_service, dashboard_service, enseignant_service, periode_service
from services.comptabilite_service import ComptabiliteError, preparer_etat_comptable
from utils.formatters import (
    formater_fcfa,
    libelle_sexe,
    libelle_statut,
    libelle_statut_periode,
    sexe_depuis_libelle,
    statut_depuis_libelle,
)

init_database()


from services import permission_service
from utils.session_auth import exiger_permission, utilisateur_courant_role

exiger_permission(permission_service.PAIE_CONSULTER)

peut_exporter = permission_service.a_permission(utilisateur_courant_role(), permission_service.EXPORT_GENERER)
st.title("Tableau de bord")
st.caption(
    "Synthèse des enseignants et de la paie de la période choisie. Les montants proviennent "
    "du moteur de calcul de paie ; cette page ne les modifie pas."
)

if permission_service.a_permission(utilisateur_courant_role(), permission_service.ALERTE_CONSULTER):
    from services import alert_service
    _compteurs_alertes = alert_service.compter_alertes_actives()
    if any(_compteurs_alertes.values()):
        st.header("Alertes actives")
        _col_a, _col_b, _col_c, _col_d = st.columns(4)
        _col_a.metric("Critiques", _compteurs_alertes.get("critique", 0))
        _col_b.metric("Erreurs", _compteurs_alertes.get("erreur", 0))
        _col_c.metric("Avertissements", _compteurs_alertes.get("avertissement", 0))
        _col_d.metric("Informations", _compteurs_alertes.get("info", 0))
        st.caption("Détail et traitement des alertes : Documents & Opérations › Notifications.")
        st.divider()

# =======================================================================
# Indicateurs enseignants (toujours visibles, indépendants de la période)
# =======================================================================
indicateurs = dashboard_service.obtenir_indicateurs_enseignants()

st.header("Enseignants")
if indicateurs.total == 0:
    st.info("Aucune donnée disponible. Aucun enseignant n'est enregistré.")
else:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total", indicateurs.total)
    col2.metric("Actifs", indicateurs.actifs)
    col3.metric("Inactifs", indicateurs.inactifs)
    col4.metric("Permanents", indicateurs.permanents)
    col5.metric("Vacataires", indicateurs.vacataires)

st.divider()

# =======================================================================
# Sélection de la période
# =======================================================================
st.header("Période consultée")

periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée.")
    peut_preparer = permission_service.a_permission(utilisateur_courant_role(), permission_service.PERIODE_GERER)
    if not peut_preparer:
        st.caption(
            "Les indicateurs apparaîtront lorsqu'un administrateur ou un gestionnaire de paie aura "
            "enregistré les enseignants et créé une période."
        )
    elif indicateurs.total == 0:
        st.markdown(
            "**Pour commencer**\n\n"
            "1. Gestion › Enseignants : enregistrer les enseignants (nom, statut, taux horaire).\n"
            "2. Gestion › Périodes de paie : créer la période du mois, puis l'ouvrir.\n"
            "3. Paie › Données de paie : saisir les heures, primes, indemnités et retenues.\n"
            "4. Paie › Calcul de paie : vérifier les montants calculés.\n\n"
            "Le guide utilisateur détaille chaque étape (Tableau de bord › Guide utilisateur)."
        )
    else:
        st.caption("Créez une période dans Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période de paie", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)

with st.expander("Statut de toutes les périodes"):
    lignes_statuts_periodes = [
        {"Période": p.libelle, "Statut": libelle_statut_periode(p.statut)}
        for p in periodes
    ]
    st.dataframe(lignes_statuts_periodes, use_container_width=True, hide_index=True)

try:
    etat = preparer_etat_comptable(periode_id)
except ComptabiliteError as erreur:
    st.warning(str(erreur))
    etat = None

if etat is not None:
    st.subheader("Indicateurs de paie de la période")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Enseignants concernés", len(etat.resultats))
    col2.metric("Total gains", formater_fcfa(etat.totaux.total_gain_heures + etat.totaux.total_primes))
    col3.metric("Total taxe (5 %)", formater_fcfa(etat.totaux.total_taxe))
    col4.metric("Total retenues", formater_fcfa(etat.totaux.total_retenues))
    col5.metric("Total net à percevoir", formater_fcfa(etat.totaux.total_net_a_percevoir))
    st.caption(f"dont total dettes : {formater_fcfa(etat.totaux.total_dette)}")

st.divider()

# =======================================================================
# Recherche et filtres
# =======================================================================
st.header("Recherche et filtres")

col_recherche, col_statut, col_sexe, col_etat = st.columns(4)
with col_recherche:
    terme_recherche = st.text_input("Rechercher un enseignant (nom, prénom)")
with col_statut:
    choix_statut = st.selectbox("Statut", ["Tous", "Permanent", "Vacataire"])
with col_sexe:
    choix_sexe = st.selectbox("Sexe", ["Tous", "Masculin", "Féminin"])
with col_etat:
    choix_etat = st.selectbox("État", ["Tous", "Actif", "Inactif"])

resultat_recherche = enseignant_service.rechercher_enseignants(terme_recherche, inclure_inactifs=True)
resultat_filtre = dashboard_service.filtrer_enseignants(
    resultat_recherche,
    statut=statut_depuis_libelle(choix_statut) if choix_statut != "Tous" else None,
    sexe=sexe_depuis_libelle(choix_sexe) if choix_sexe != "Tous" else None,
    actif=(choix_etat == "Actif") if choix_etat != "Tous" else None,
)
ids_filtres = {e.id for e in resultat_filtre}

st.caption(f"{len(resultat_filtre)} enseignant(s) correspondant aux critères.")

st.divider()

# =======================================================================
# Tableau récapitulatif (croisé avec les résultats de la période)
# =======================================================================
st.header("Tableau récapitulatif")

if etat is None:
    st.info("Aucune donnée de paie à afficher pour cette période.")
    resultats_filtres = []
else:
    resultats_filtres = [r for r in etat.resultats if r.enseignant_id in ids_filtres]
    if not resultats_filtres:
        st.info("Aucun enseignant ne correspond aux critères pour cette période.")
    else:
        lignes = [
            {
                "N°": i,
                "Nom": r.nom,
                "Prénom": r.prenom,
                "Sexe": libelle_sexe(r.sexe),
                "Statut": libelle_statut(r.statut),
                "Heures": r.total_heures,
                "Taux horaire": formater_fcfa(r.taux_horaire),
                "Gain": formater_fcfa(r.gain_heures),
                "Taxe": formater_fcfa(r.taxe_5),
                "Retenues": formater_fcfa(r.retenue_amicale + r.dette),
                "Dette": formater_fcfa(r.dette),
                "Net": formater_fcfa(r.net_a_percevoir),
            }
            for i, r in enumerate(resultats_filtres, start=1)
        ]
        st.dataframe(lignes, use_container_width=True, hide_index=True)

st.divider()

# =======================================================================
# Fiche détaillée d'un enseignant
# =======================================================================
st.header("Fiche détaillée")

if resultats_filtres:
    options_fiche = {f"{r.nom} {r.prenom}": r for r in resultats_filtres}
    choix_fiche = st.selectbox("Sélectionner un enseignant", list(options_fiche.keys()))
    r = options_fiche[choix_fiche]

    col_identite, col_heures, col_remuneration, col_retenues = st.columns(4)
    with col_identite:
        st.markdown("**IDENTITÉ**")
        st.write(f"Nom : {r.nom}")
        st.write(f"Prénom : {r.prenom}")
        st.write(f"Sexe : {libelle_sexe(r.sexe)}")
        st.write(f"Statut : {libelle_statut(r.statut)}")
        st.write(f"Taux horaire : {formater_fcfa(r.taux_horaire)}")
    with col_heures:
        st.markdown("**HEURES**")
        st.write(f"Semaine 1 : {r.semaine_1:g}")
        st.write(f"Semaine 2 : {r.semaine_2:g}")
        st.write(f"Semaine 3 : {r.semaine_3:g}")
        st.write(f"Semaine 4 : {r.semaine_4:g}")
        st.write(f"Semaine 5 : {r.semaine_5:g}")
        st.write(f"**Total : {r.total_heures:g}**")
    with col_remuneration:
        st.markdown("**RÉMUNÉRATION**")
        st.write(f"Gain par heures : {formater_fcfa(r.gain_heures)}")
        st.write(f"Prime AP/PP : {formater_fcfa(r.prime_ap_pp)}")
        st.write(f"Surveillance/Secrétariat : {formater_fcfa(r.surveillance_secretariat)}")
        st.write(f"Indemnité suggestion/admin : {formater_fcfa(r.indemnite_suggestion_admin)}")
    with col_retenues:
        st.markdown("**RETENUES**")
        st.write(f"Taxe 5 % : {formater_fcfa(r.taxe_5)}")
        st.write(f"Retenue amicale : {formater_fcfa(r.retenue_amicale)}")
        st.write(f"Dette : {formater_fcfa(r.dette)}")

    st.markdown("**RÉSULTAT**")
    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("Total gains", formater_fcfa(r.base_taxable))
    col_r2.metric("Total retenues", formater_fcfa(r.base_taxable - r.net_a_percevoir))
    col_r3.metric("Net à percevoir", formater_fcfa(r.net_a_percevoir))

    deja_genere = bulletin_service.bulletin_deja_genere(r.nom, r.prenom, periode.libelle)
    st.caption(
        f"Bulletin pour cette période : {'Généré' if deja_genere else 'Non généré'} "
        "(généré depuis « Bulletins de paie »)"
    )
else:
    st.info("Aucun enseignant sélectionnable pour cette période avec les filtres actuels.")

st.divider()

# =======================================================================
# Historique des bulletins de la période
# =======================================================================
st.header("Historique des bulletins (période sélectionnée)")

if resultats_filtres:
    etat_bulletins = dashboard_service.etat_bulletins_periode(resultats_filtres, periode.libelle)
    lignes_bulletins = [
        {
            "Enseignant": f"{r.nom} {r.prenom}",
            "Période": periode.libelle,
            "Bulletin": "Généré" if etat_bulletins.get(r.enseignant_id) else "Non généré",
        }
        for r in resultats_filtres
    ]
    st.dataframe(lignes_bulletins, use_container_width=True, hide_index=True)
    st.caption("Pour générer un bulletin manquant, utilisez la page Paie › Bulletins de solde.")
else:
    st.info("Aucune donnée à afficher.")

st.divider()

# =======================================================================
# Statistiques par statut / sexe
# =======================================================================
st.header("Statistiques")

if etat is not None and etat.resultats:
    col_statut, col_sexe_stats = st.columns(2)
    with col_statut:
        st.markdown("**Par statut**")
        lignes_statut = [
            {
                "Statut": s.libelle, "Nombre": s.nombre, "Total heures": s.total_heures,
                "Total gains": formater_fcfa(s.total_gain_heures), "Total net": formater_fcfa(s.total_net),
            }
            for s in dashboard_service.synthese_par_statut(etat.resultats)
        ]
        st.dataframe(lignes_statut, use_container_width=True, hide_index=True)
    with col_sexe_stats:
        st.markdown("**Par sexe** *(descriptif uniquement)*")
        lignes_sexe = [
            {
                "Sexe": s.libelle, "Nombre": s.nombre, "Total heures": s.total_heures,
                "Total gains": formater_fcfa(s.total_gain_heures), "Total net": formater_fcfa(s.total_net),
            }
            for s in dashboard_service.synthese_par_sexe(etat.resultats)
        ]
        st.dataframe(lignes_sexe, use_container_width=True, hide_index=True)

    anomalies = dashboard_service.controler_coherence_resultats(etat.resultats)
    if anomalies:
        st.error("Anomalies détectées :\n" + "\n".join(f"- {a}" for a in anomalies))
    else:
        st.success("Aucune anomalie de cohérence détectée pour cette période.")
else:
    st.info("Aucune statistique disponible pour cette période.")

st.divider()

# =======================================================================
# Évolution de la masse salariale
# =======================================================================
st.header("Évolution de la masse salariale")

evolution = dashboard_service.evolution_masse_salariale()
if len(evolution) < 2:
    st.info("Au moins deux périodes exploitables sont nécessaires pour afficher une évolution.")
else:
    lignes_evolution = [
        {
            "Période": pt.libelle,
            "Total gains": formater_fcfa(pt.total_gains),
            "Total taxe": formater_fcfa(pt.total_taxe),
            "Total retenues": formater_fcfa(pt.total_retenues),
            "Total net": formater_fcfa(pt.total_net),
        }
        for pt in evolution
    ]
    st.dataframe(lignes_evolution, use_container_width=True, hide_index=True)

    df_graphique = pd.DataFrame({"Net total": [pt.total_net for pt in evolution]}, index=[pt.libelle for pt in evolution])
    st.line_chart(df_graphique)

st.divider()

# =======================================================================
# Export de la consultation filtrée (réutilise le module 06)
# =======================================================================
st.header("Export de la consultation")

if etat is not None and resultats_filtres:
    aucun_filtre_actif = (
        not terme_recherche.strip()
        and choix_statut == "Tous"
        and choix_sexe == "Tous"
        and choix_etat == "Tous"
    )
    # None = export complet (aucun filtre) ; sinon, liste EXACTE des
    # enseignants actuellement affichés après filtrage/recherche.
    enseignant_ids_export = None if aucun_filtre_actif else [r.enseignant_id for r in resultats_filtres]

    if not peut_exporter:
        st.info("Vous n'avez pas la permission de générer des exports (consultation seule).")

    if st.button("Générer l'export Excel de cette consultation", disabled=not peut_exporter):
        try:
            chemin_export = dashboard_service.exporter_consultation_excel(
                periode_id, enseignant_ids=enseignant_ids_export
            )
            with open(chemin_export, "rb") as fichier:
                st.download_button(
                    f"Télécharger {chemin_export.name}",
                    data=fichier.read(),
                    file_name=chemin_export.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        except ComptabiliteError as erreur:
            st.error(str(erreur))
else:
    st.info("Aucune donnée exportable avec les filtres actuels.")

st.divider()

# =======================================================================
# Répartition des composantes de paie (indicateur financier, section 25)
# =======================================================================
st.header("Répartition de la masse salariale")
if etat is not None and etat.resultats:
    import pandas as pd

    composantes = pd.DataFrame(
        {"Montant": [
            etat.totaux.total_gain_heures, etat.totaux.total_primes,
            etat.totaux.total_taxe, etat.totaux.total_retenues,
        ]},
        index=["Gains", "Primes/indemnités", "Taxe", "Retenues"],
    )
    st.bar_chart(composantes)
    if permission_service.a_permission(utilisateur_courant_role(), permission_service.STATISTIQUES_CONSULTER):
        from services import statistiques_service
        _stats_kpi = statistiques_service.statistiques_generales(periode_id)
        if _stats_kpi.nombre_enseignants_actifs > 0:
            st.metric("Coût moyen par enseignant", formater_fcfa(_stats_kpi.total_net // _stats_kpi.nombre_enseignants_actifs))
    st.caption(
        "Pour une analyse financière complète (rapprochement, comparaison, export Excel détaillé), "
        "consultez la page **« Rapports comptables »**, ou **« Statistiques »** pour l'analyse décisionnelle."
    )
else:
    st.info("Aucune donnée à représenter pour cette période.")
