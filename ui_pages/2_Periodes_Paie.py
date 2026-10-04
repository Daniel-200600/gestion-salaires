"""
Page Streamlit — Module 03 : Gestion des périodes de paie.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL. Elle appelle exclusivement les fonctions de services.periode_service,
qui portent toute la logique de validation et de transition d'état.
"""

import sys
from datetime import date
from pathlib import Path

# Garantit que la racine du projet est importable, quelle que soit la
# façon dont Streamlit est lancé.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from models.enums import StatutPeriode
from services import permission_service
from services.periode_service import (
    PeriodeValidationError,
    creer_periode,
    lister_periodes,
    modifier_periode,
    obtenir_dependances_periode,
    obtenir_periode,
    ouvrir_periode,
)
from utils.formatters import LIBELLES_STATUT_PERIODE, NOMS_MOIS, formater_taxe_periode, libelle_statut_periode
from utils.ui_helpers import badge_statut_periode
from services.parametres_paie_service import (
    ParametrePaieError,
    formater_taux,
    obtenir_taux_taxe_defaut,
    taux_periode_modifiable,
    taux_vers_pourcentage,
)
from services import administration_service
from services import administration_periode_service as admin_periode
from services.autorisation_service import AutorisationRefuseeError
from utils.session_auth import exiger_permission, utilisateur_courant_id, utilisateur_courant_role

# Idempotent : garantit que les tables existent dès le premier lancement.
init_database()


exiger_permission(permission_service.PERIODE_CONSULTER)
role_courant = utilisateur_courant_role()
peut_gerer_periode = permission_service.a_permission(role_courant, permission_service.PERIODE_GERER)
peut_supprimer_periode = permission_service.a_permission(role_courant, permission_service.PERIODE_SUPPRIMER)
peut_regler_taux = permission_service.a_permission(role_courant, permission_service.PARAMETRES_PAIE_GERER)

st.title("Gestion des périodes de paie")
if (message_action := st.session_state.pop("message_action_periode", None)) is not None:
    st.success(message_action)

ANNEE_COURANTE = date.today().year  # valeur par défaut raisonnable pour le formulaire ; l'utilisateur peut la changer

# =======================================================================
# Zone 1 — Créer une période
# =======================================================================
if not peut_gerer_periode:
    st.info("Vous consultez les périodes en lecture seule (permission de gestion non accordée).")
with st.expander("Créer une période", expanded=False):
    if not peut_gerer_periode:
        st.warning("Vous n'avez pas la permission de créer une période.")
    with st.form("form_creation_periode", clear_on_submit=True):
        col_gauche, col_droite = st.columns(2)
        with col_gauche:
            mois_libelle = st.selectbox("Mois *", NOMS_MOIS, index=7)  # Août par défaut
        with col_droite:
            annee = st.number_input(
                "Année *", min_value=2000, max_value=2100, step=1, value=ANNEE_COURANTE, format="%d"
            )

        mois_numero = NOMS_MOIS.index(mois_libelle) + 1
        st.caption(
            f"Libellé généré automatiquement : **{mois_libelle} {int(annee)}** · "
            f"taux de taxe des vacataires : **{formater_taux(obtenir_taux_taxe_defaut())}** "
            "(taux par défaut, réglable dans Administration › Paramètres ; aucune taxe pour les permanents)"
        )

        soumis = st.form_submit_button("Créer la période", disabled=not peut_gerer_periode)

        if soumis and peut_gerer_periode:
            try:
                nouvelle_periode = creer_periode(mois=mois_numero, annee=int(annee))
                st.success(f"Période « {nouvelle_periode.libelle} » créée avec succès (statut : Brouillon).")
                st.rerun()
            except PeriodeValidationError as erreur:
                st.error(str(erreur))

st.divider()

# =======================================================================
# Zone 2 — Liste des périodes (avec filtres)
# =======================================================================
st.subheader("Liste des périodes")

col_filtre_annee, col_filtre_statut = st.columns(2)
with col_filtre_annee:
    annees_disponibles = sorted({p.annee for p in lister_periodes()}, reverse=True)
    options_annee = ["Toutes"] + [str(a) for a in annees_disponibles]
    filtre_annee_libelle = st.selectbox("Filtrer par année", options_annee)
with col_filtre_statut:
    options_statut = ["Tous"] + list(LIBELLES_STATUT_PERIODE.values())
    filtre_statut_libelle = st.selectbox("Filtrer par statut", options_statut)

filtre_annee = None if filtre_annee_libelle == "Toutes" else int(filtre_annee_libelle)
filtre_statut = None
if filtre_statut_libelle != "Tous":
    filtre_statut = next(
        statut for statut, libelle in LIBELLES_STATUT_PERIODE.items() if libelle == filtre_statut_libelle
    )

periodes = lister_periodes(annee=filtre_annee, statut=filtre_statut)

if not periodes:
    st.info("Aucune donnée disponible. Aucune période ne correspond aux filtres sélectionnés.")
else:
    lignes_tableau = [
        {
            "Période": p.libelle,
            "Mois": p.mois,
            "Année": p.annee,
            "Statut": libelle_statut_periode(p.statut),
            "Taxe": formater_taxe_periode(p),
            "Date de création": p.date_creation,
            "Date de clôture": p.date_cloture or "—",
        }
        for p in periodes
    ]
    st.dataframe(lignes_tableau, use_container_width=True, hide_index=True)
    st.caption(f"{len(periodes)} période(s) affichée(s).")

st.divider()

# =======================================================================
# Zone 3 — Actions sur une période (selon son statut)
# =======================================================================
st.subheader("Actions sur une période")

if not periodes:
    st.info("Aucune période disponible pour les actions.")
else:
    options_periodes = {p.libelle: p.id for p in periodes}
    choix_libelle = st.selectbox("Sélectionner une période", list(options_periodes.keys()))
    periode_id = options_periodes[choix_libelle]
    periode_selectionnee = obtenir_periode(periode_id)

    st.markdown(f"Statut actuel : {badge_statut_periode(periode_selectionnee.statut)}", unsafe_allow_html=True)

    # --- Taux de taxe de la période -------------------------------------
    if taux_periode_modifiable(periode_selectionnee):
        st.write(f"Taux de taxe de la période : **{formater_taux(periode_selectionnee.taux_taxe)}**, appliqué "
                 "aux vacataires uniquement (modifiable jusqu'à la validation, puis figé).")
        if peut_regler_taux:
            with st.form(f"form_taux_{periode_id}"):
                pourcentage = st.number_input(
                    "Taux de taxe de cette période (%)", min_value=0.0, max_value=50.0, step=0.5, format="%.2f",
                    value=float(taux_vers_pourcentage(periode_selectionnee.taux_taxe)),
                )
                if st.form_submit_button("Appliquer ce taux à la période"):
                    try:
                        administration_service.definir_taux_taxe_periode(
                            utilisateur_courant_id(), periode_id, f"{pourcentage:.2f}"
                        )
                        st.success("Taux de taxe de la période mis à jour.")
                        st.rerun()
                    except (ParametrePaieError, AutorisationRefuseeError) as erreur:
                        st.error(str(erreur))
    else:
        st.write(f"Taxe de la période : **{formater_taxe_periode(periode_selectionnee)}** "
                 "(figée : période validée ou clôturée).")

    if periode_selectionnee.statut == StatutPeriode.BROUILLON:
        col_ouvrir, col_modifier = st.columns(2)
        with col_ouvrir:
            if st.button("Ouvrir cette période"):
                try:
                    ouvrir_periode(periode_id)
                    st.success("Période ouverte. Elle est prête à recevoir les données de paie.")
                    st.rerun()
                except PeriodeValidationError as erreur:
                    st.error(str(erreur))
        with col_modifier:
            with st.popover("Corriger mois/année"):
                with st.form(f"form_modifier_{periode_id}"):
                    nouveau_mois_libelle = st.selectbox(
                        "Mois", NOMS_MOIS, index=periode_selectionnee.mois - 1
                    )
                    nouvelle_annee = st.number_input(
                        "Année", min_value=2000, max_value=2100, step=1,
                        value=periode_selectionnee.annee, format="%d",
                    )
                    valider_modif = st.form_submit_button("Enregistrer")
                    if valider_modif:
                        try:
                            modifier_periode(
                                periode_id=periode_id,
                                mois=NOMS_MOIS.index(nouveau_mois_libelle) + 1,
                                annee=int(nouvelle_annee),
                            )
                            st.success("Période modifiée avec succès.")
                            st.rerun()
                        except PeriodeValidationError as erreur:
                            st.error(str(erreur))

    elif periode_selectionnee.statut == StatutPeriode.OUVERTE:
        st.info(
            "La validation d'une période passe désormais par un contrôle complet des données. "
            "Rendez-vous sur la page **« Contrôle de la paie »** pour valider cette période."
        )
        st.page_link("ui_pages/9_Controle_Paie.py", label="Aller au contrôle de la paie", icon=":material/arrow_forward:")

    elif periode_selectionnee.statut == StatutPeriode.VALIDEE:
        st.info(
            "La clôture d'une période passe désormais par un contrôle complet des données. "
            "Rendez-vous sur la page **« Contrôle de la paie »** pour clôturer cette période."
        )
        st.page_link("ui_pages/9_Controle_Paie.py", label="Aller au contrôle de la paie", icon=":material/arrow_forward:")

    else:  # CLOTUREE
        st.info("Cette période est clôturée. Aucune action de modification n'est disponible.")

    st.divider()

    # ===================================================================
    # Zone 4 — Actions d'administrateur : rouvrir (invalider) ou supprimer
    # ===================================================================
    st.subheader("Rouvrir ou supprimer la période")
    if not peut_supprimer_periode:
        st.caption("Réservé aux administrateurs.")
    else:
        dependances_periode = obtenir_dependances_periode(periode_id)
        st.caption(
            f"Données de la période : {dependances_periode.nombre_heures} saisie(s) d'heures, "
            f"{dependances_periode.nombre_elements_remuneration} élément(s) de rémunération, "
            f"{dependances_periode.nombre_retenues} retenue(s), "
            f"{'des' if dependances_periode.a_des_bulletins else 'aucun'} bulletin(s) enregistré(s). "
            "Une sauvegarde de la base est créée automatiquement avant chaque action ; chaque action est "
            "inscrite au journal d'audit."
        )
        col_rouvrir, col_supprimer = st.columns(2)

        with col_rouvrir:
            st.markdown("**Rouvrir (invalider) la période**")
            if periode_selectionnee.statut in (StatutPeriode.VALIDEE, StatutPeriode.CLOTUREE):
                st.caption(
                    "La période redevient ouverte : ses données redeviennent modifiables. Après correction, "
                    "validez-la de nouveau et produisez les bulletins."
                )
                with st.form(f"form_rouvrir_{periode_id}"):
                    motif = st.text_input("Motif (facultatif)")
                    confirmation_r = st.text_input(f"Tapez « {periode_selectionnee.libelle} » pour confirmer")
                    if st.form_submit_button("Rouvrir la période"):
                        try:
                            rapport = admin_periode.rouvrir_periode(
                                utilisateur_courant_id(), periode_id, confirmation_r, motif=motif
                            )
                            st.session_state["message_action_periode"] = (
                                f"{rapport.libelle} est de nouveau ouverte. Sauvegarde préalable : {rapport.sauvegarde.name}."
                            )
                            st.rerun()
                        except (admin_periode.AdministrationPeriodeError, AutorisationRefuseeError) as erreur:
                            st.error(str(erreur))
            else:
                st.caption("Disponible pour une période validée ou clôturée.")

        with col_supprimer:
            st.markdown("**Supprimer la période**")
            st.caption(
                "Supprime la période, quel que soit son statut, avec ses heures, primes, retenues et bulletins "
                "enregistrés. Les fiches des enseignants sont conservées."
            )
            with st.form(f"form_supprimer_{periode_id}"):
                confirmation_s = st.text_input(f"Tapez « {periode_selectionnee.libelle} » pour confirmer")
                if st.form_submit_button("Supprimer la période", type="primary"):
                    try:
                        rapport = admin_periode.supprimer_periode(utilisateur_courant_id(), periode_id, confirmation_s)
                        st.session_state["message_action_periode"] = (
                            f"La période {rapport.libelle} a été supprimée ({rapport.nb_saisies_heures} saisie(s) "
                            f"d'heures). Sauvegarde préalable : {rapport.sauvegarde.name} (Administration › Restauration)."
                        )
                        st.rerun()
                    except (admin_periode.AdministrationPeriodeError, AutorisationRefuseeError) as erreur:
                        st.error(str(erreur))
