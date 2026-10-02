"""
Page Streamlit — Module 02 : Gestion des enseignants.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL. Elle appelle exclusivement les fonctions de services.enseignant_service,
qui portent toute la logique de validation et d'orchestration.
"""

import sys
from pathlib import Path

# Garantit que la racine du projet est importable, quelle que soit la
# façon dont Streamlit est lancé (streamlit run pages/1_Enseignants.py
# ou via un futur app.py multipage).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from io import BytesIO

import streamlit as st

from database.initialization import init_database
from exports.import_template_export import generer_classeur_fiches_a_completer
from services.enseignant_service import (
    MESSAGE_BULLETIN_EXISTANT,
    ComplementFiche,
    EnseignantValidationError,
    changer_statut_enseignant,
    completer_fiches_en_lot,
    creer_enseignant,
    desactiver_enseignant,
    lister_enseignants,
    lister_enseignants_a_completer,
    modifier_enseignant,
    obtenir_dependances_enseignant,
    obtenir_enseignant,
    reactiver_enseignant,
    rechercher_enseignants,
)
from utils.formatters import (
    OPTIONS_SEXE,
    OPTIONS_STATUT,
    formater_fcfa,
    libelle_actif,
    libelle_sexe,
    libelle_statut,
    sexe_depuis_libelle,
    statut_depuis_libelle,
)

# Idempotent : garantit que les tables existent dès le premier lancement.
init_database()


from services import licence_service, permission_service
from services import administration_service
from services.autorisation_service import AutorisationRefuseeError
from utils.session_auth import exiger_permission, utilisateur_courant_id, utilisateur_courant_role

exiger_permission(permission_service.ENSEIGNANT_CONSULTER)

st.title("Gestion des enseignants")

_places_demo = licence_service.places_restantes_demo()
if _places_demo is not None:
    st.info(
        f"Mode démonstration : {licence_service.LIMITE_DEMO_ENSEIGNANTS} enseignants au maximum "
        f"({_places_demo} place(s) restante(s)). Un administrateur active la licence dans Administration › Licence."
    )

# =======================================================================
# Zone 1 — Ajouter un enseignant
# =======================================================================
with st.expander("Ajouter un enseignant", expanded=False):
    with st.form("form_ajout_enseignant", clear_on_submit=True):
        col_gauche, col_droite = st.columns(2)

        with col_gauche:
            nom = st.text_input("Nom *")
            sexe_libelle = st.selectbox("Sexe *", OPTIONS_SEXE)
            taux_horaire = st.number_input(
                "Taux horaire (FCFA) *", min_value=0, step=100, format="%d"
            )
            email = st.text_input("Email")

        with col_droite:
            prenom = st.text_input("Prénom(s) *")
            statut_libelle = st.selectbox("Statut *", OPTIONS_STATUT)
            telephone = st.text_input("Téléphone")
            adresse = st.text_input("Adresse")

        soumis = st.form_submit_button("Enregistrer l'enseignant")

        if soumis:
            try:
                nouvel_enseignant = creer_enseignant(
                    nom=nom,
                    prenom=prenom,
                    sexe=sexe_depuis_libelle(sexe_libelle),
                    statut=statut_depuis_libelle(statut_libelle),
                    taux_horaire=taux_horaire,
                    email=email,
                    telephone=telephone,
                    adresse=adresse,
                )
                st.success(
                    f"Enseignant « {nouvel_enseignant.prenom} {nouvel_enseignant.nom} » ajouté avec succès."
                )
                st.rerun()
            except EnseignantValidationError as erreur:
                st.error(str(erreur))

st.divider()

# =======================================================================
# Zone 2 — Liste des enseignants (recherche + filtre)
# =======================================================================
st.subheader("Liste des enseignants")

fiches_a_completer = lister_enseignants_a_completer()
if fiches_a_completer:
    st.warning(
        f"{len(fiches_a_completer)} fiche(s) à compléter (sexe, statut ou taux horaire manquant, souvent après "
        "l'import d'une liste existante). Ces enseignants n'entrent pas dans la paie tant que leur fiche est "
        "incomplète : complétez-les toutes ensemble ci-dessous, ou une par une (onglet « Modifier »)."
    )
    if (message_lot := st.session_state.pop("message_complement_lot", None)) is not None:
        st.success(message_lot)
    with st.expander(f"Compléter les fiches en une fois ({len(fiches_a_completer)})", expanded=False):
        peut_completer = permission_service.a_permission(
            utilisateur_courant_role(), permission_service.ENSEIGNANT_MODIFIER
        )
        st.caption(
            "Choisissez le sexe et le statut, saisissez le taux horaire, puis enregistrez. Une case encore "
            "inconnue peut rester vide : la fiche restera à compléter. Aucune information déjà enregistrée "
            "n'est effacée."
        )
        # Clé renouvelée après chaque enregistrement : le tableau change de lignes.
        version_editeur = st.session_state.get("version_editeur_fiches", 0)
        tableau_modifie = st.data_editor(
            [
                {
                    "ID": e.id, "Nom": e.nom, "Prénom": e.prenom,
                    "Sexe": libelle_sexe(e.sexe) if e.sexe is not None else None,
                    "Statut": libelle_statut(e.statut) if e.statut is not None else None,
                    "Taux horaire (FCFA)": e.taux_horaire,
                }
                for e in fiches_a_completer
            ],
            column_config={
                "ID": st.column_config.NumberColumn(disabled=True, width="small"),
                "Nom": st.column_config.TextColumn(disabled=True),
                "Prénom": st.column_config.TextColumn(disabled=True),
                "Sexe": st.column_config.SelectboxColumn(options=OPTIONS_SEXE),
                "Statut": st.column_config.SelectboxColumn(options=OPTIONS_STATUT),
                "Taux horaire (FCFA)": st.column_config.NumberColumn(min_value=0, step=100, format="%d"),
            },
            hide_index=True, use_container_width=True, disabled=not peut_completer, placeholder="À renseigner",
            key=f"editeur_fiches_{version_editeur}",
        )
        col_enregistrer, col_exporter = st.columns(2)
        with col_enregistrer:
            if st.button("Enregistrer les compléments", type="primary", disabled=not peut_completer):
                try:
                    resultat = completer_fiches_en_lot(
                        [
                            ComplementFiche(
                                enseignant_id=int(ligne["ID"]),
                                sexe=sexe_depuis_libelle(ligne["Sexe"]) if ligne["Sexe"] else None,
                                statut=statut_depuis_libelle(ligne["Statut"]) if ligne["Statut"] else None,
                                taux_horaire=ligne["Taux horaire (FCFA)"],
                            )
                            for ligne in tableau_modifie
                        ],
                        utilisateur=st.session_state.get("username"),
                    )
                except EnseignantValidationError as erreur:
                    st.error(str(erreur))
                else:
                    st.session_state["message_complement_lot"] = (
                        f"{resultat.nb_fiches_modifiees} fiche(s) mise(s) à jour, dont "
                        f"{resultat.nb_fiches_completees} désormais complète(s) et incluse(s) dans la paie."
                        if resultat.nb_fiches_modifiees else "Aucune information nouvelle à enregistrer."
                    )
                    st.session_state["version_editeur_fiches"] = version_editeur + 1
                    st.rerun()
        with col_exporter:
            tampon_fiches = BytesIO()
            generer_classeur_fiches_a_completer(fiches_a_completer).save(tampon_fiches)
            st.download_button(
                "Télécharger la liste à compléter (Excel)", data=tampon_fiches.getvalue(),
                file_name="Fiches_enseignants_a_completer.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="À faire remplir (cases jaunes), puis à réimporter dans Importation, type « Enseignants », "
                     "stratégie « Mettre à jour les doublons ».",
            )
elif (message_lot := st.session_state.pop("message_complement_lot", None)) is not None:
    st.success(message_lot)

col_recherche, col_filtre, col_incomplets = st.columns([3, 1, 1])
with col_recherche:
    terme_recherche = st.text_input(
        "Rechercher (nom, prénom ou nom complet)", key="champ_recherche_enseignant"
    )
with col_filtre:
    inclure_inactifs = st.checkbox("Inclure les enseignants désactivés", value=False)
with col_incomplets:
    seulement_a_completer = st.checkbox("Seulement les fiches à compléter", value=False)

if terme_recherche:
    enseignants = rechercher_enseignants(terme_recherche, inclure_inactifs=inclure_inactifs)
else:
    enseignants = lister_enseignants(inclure_inactifs=inclure_inactifs)
if seulement_a_completer:
    enseignants = [e for e in enseignants if not e.est_complet]

if not enseignants:
    st.info("Aucune donnée disponible. Aucun enseignant ne correspond aux critères affichés.")
else:
    lignes_tableau = [
        {
            "ID": enseignant.id,
            "Nom": enseignant.nom,
            "Prénom": enseignant.prenom,
            "Sexe": libelle_sexe(enseignant.sexe),
            "Statut": libelle_statut(enseignant.statut),
            "Taux horaire": formater_fcfa(enseignant.taux_horaire),
            "Fiche": "Complète" if enseignant.est_complet else "À compléter : " + ", ".join(enseignant.champs_manquants),
            "État": libelle_actif(enseignant.actif),
        }
        for enseignant in enseignants
    ]
    st.dataframe(lignes_tableau, use_container_width=True, hide_index=True)
    st.caption(f"{len(enseignants)} enseignant(s) affiché(s).")

st.divider()

# =======================================================================
# Zone 3 — Actions : consulter / modifier / désactiver / réactiver
# =======================================================================
st.subheader("Actions sur un enseignant")

if not enseignants:
    st.info("Aucun enseignant disponible pour les actions.")
else:
    options_enseignants = {
        f"{enseignant.prenom} {enseignant.nom}".strip()
        + f" (id {enseignant.id})" + ("" if enseignant.est_complet else " — à compléter"): enseignant.id
        for enseignant in enseignants
    }
    choix_libelle = st.selectbox("Sélectionner un enseignant", list(options_enseignants.keys()))
    enseignant_id = options_enseignants[choix_libelle]
    enseignant_selectionne = obtenir_enseignant(enseignant_id)

    onglet_fiche, onglet_modifier, onglet_statut, onglet_etat, onglet_suppression = st.tabs(
        ["Fiche détaillée", "Modifier", "Changer le statut", "Activer / Désactiver", "Supprimer définitivement"]
    )

    # --- Fiche détaillée -----------------------------------------------
    with onglet_fiche:
        if not enseignant_selectionne.est_complet:
            st.warning(
                "Fiche à compléter : " + ", ".join(enseignant_selectionne.champs_manquants)
                + ". Cet enseignant n'entre pas dans la paie tant qu'elle est incomplète (onglet « Modifier »)."
            )
        col_a, col_b = st.columns(2)
        with col_a:
            st.write(f"**Nom :** {enseignant_selectionne.nom}")
            st.write(f"**Prénom :** {enseignant_selectionne.prenom}")
            st.write(f"**Sexe :** {libelle_sexe(enseignant_selectionne.sexe)}")
            st.write(f"**Statut :** {libelle_statut(enseignant_selectionne.statut)}")
            st.write(f"**Taux horaire :** {formater_fcfa(enseignant_selectionne.taux_horaire)}")
        with col_b:
            st.write(f"**Email :** {enseignant_selectionne.email or '—'}")
            st.write(f"**Téléphone :** {enseignant_selectionne.telephone or '—'}")
            st.write(f"**Adresse :** {enseignant_selectionne.adresse or '—'}")
            st.write(f"**État :** {libelle_actif(enseignant_selectionne.actif)}")
        st.caption(
            f"Créé le {enseignant_selectionne.date_creation} · "
            f"Dernière modification le {enseignant_selectionne.date_modification}"
        )

    # --- Modifier ---------------------------------------------------
    with onglet_modifier:
        peut_modifier_enseignant = permission_service.a_permission(
            utilisateur_courant_role(), permission_service.ENSEIGNANT_MODIFIER
        )
        if not peut_modifier_enseignant:
            st.info("Vous n'avez pas la permission de modifier les enseignants (consultation seule).")
        with st.form(f"form_modifier_{enseignant_id}"):
            col_gauche, col_droite = st.columns(2)

            with col_gauche:
                nom_modifie = st.text_input("Nom *", value=enseignant_selectionne.nom)
                sexe_modifie_libelle = st.selectbox(
                    "Sexe *",
                    OPTIONS_SEXE,
                    index=(OPTIONS_SEXE.index(libelle_sexe(enseignant_selectionne.sexe))
                           if enseignant_selectionne.sexe is not None else None),
                    placeholder="À renseigner",
                )
                taux_modifie = st.number_input(
                    "Taux horaire (FCFA) *",
                    min_value=0,
                    step=100,
                    format="%d",
                    value=(int(enseignant_selectionne.taux_horaire)
                           if enseignant_selectionne.taux_horaire is not None else None),
                    placeholder="À renseigner",
                )
                email_modifie = st.text_input("Email", value=enseignant_selectionne.email or "")

            with col_droite:
                prenom_modifie = st.text_input("Prénom(s) *", value=enseignant_selectionne.prenom)
                statut_modifie_libelle = st.selectbox(
                    "Statut *",
                    OPTIONS_STATUT,
                    index=(OPTIONS_STATUT.index(libelle_statut(enseignant_selectionne.statut))
                           if enseignant_selectionne.statut is not None else None),
                    placeholder="À renseigner",
                )
                telephone_modifie = st.text_input("Téléphone", value=enseignant_selectionne.telephone or "")
                adresse_modifiee = st.text_input("Adresse", value=enseignant_selectionne.adresse or "")

            if not enseignant_selectionne.est_complet:
                st.caption(
                    "Renseignez les informations manquantes. Une information encore inconnue peut rester "
                    "vide : la fiche restera « à compléter »."
                )
            soumis_modification = st.form_submit_button(
                "Enregistrer les modifications", disabled=not peut_modifier_enseignant
            )

            if soumis_modification and peut_modifier_enseignant:
                try:
                    modifier_enseignant(
                        enseignant_id=enseignant_id,
                        nom=nom_modifie,
                        prenom=prenom_modifie,
                        sexe=sexe_depuis_libelle(sexe_modifie_libelle) if sexe_modifie_libelle else None,
                        statut=statut_depuis_libelle(statut_modifie_libelle) if statut_modifie_libelle else None,
                        taux_horaire=taux_modifie,
                        email=email_modifie,
                        telephone=telephone_modifie,
                        adresse=adresse_modifiee,
                        utilisateur=st.session_state.get("username"),
                    )
                    st.success("Enseignant modifié avec succès.")
                    st.rerun()
                except EnseignantValidationError as erreur:
                    st.error(str(erreur))

    # --- Changer le statut (Vacataire <-> Permanent) ----------------
    with onglet_statut:
        peut_changer_statut = permission_service.a_permission(
            utilisateur_courant_role(), permission_service.ENSEIGNANT_MODIFIER
        )
        st.write(f"**Statut actuel :** {libelle_statut(enseignant_selectionne.statut)}")
        st.caption(
            "Le nouveau statut s'applique aux calculs et aux bulletins produits à partir de maintenant. "
            "Les bulletins déjà émis pour une période validée ou clôturée conservent le statut qu'ils "
            "portaient. Chaque changement est inscrit au journal d'audit."
        )
        if not peut_changer_statut:
            st.info("Vous n'avez pas la permission de modifier les enseignants (consultation seule).")
        else:
            autres_statuts = [o for o in OPTIONS_STATUT if o != libelle_statut(enseignant_selectionne.statut)]
            with st.form(f"form_statut_{enseignant_id}"):
                nouveau_statut_libelle = st.selectbox("Nouveau statut", autres_statuts)
                confirme_statut = st.checkbox(
                    f"Je confirme le passage de {enseignant_selectionne.prenom} {enseignant_selectionne.nom} "
                    f"au statut « {nouveau_statut_libelle} »."
                )
                if st.form_submit_button("Changer le statut", type="primary"):
                    if not confirme_statut:
                        st.error("Cochez la case de confirmation pour changer le statut.")
                    else:
                        try:
                            changer_statut_enseignant(
                                enseignant_id, statut_depuis_libelle(nouveau_statut_libelle),
                                utilisateur=st.session_state.get("username"),
                            )
                            st.success(f"Statut modifié : {nouveau_statut_libelle}.")
                            st.rerun()
                        except EnseignantValidationError as erreur:
                            st.error(str(erreur))

    # --- Activer / Désactiver ---------------------------------------
    with onglet_etat:
        peut_changer_etat = permission_service.a_permission(
            utilisateur_courant_role(), permission_service.ENSEIGNANT_MODIFIER
        )
        if enseignant_selectionne.actif:
            st.warning("Cet enseignant est actuellement **actif**.")
        else:
            st.warning("Cet enseignant est actuellement **inactif**.")
        if not peut_changer_etat:
            st.info("Vous n'avez pas la permission de modifier les enseignants (consultation seule).")
        elif enseignant_selectionne.actif:
            if st.button("Désactiver cet enseignant"):
                desactiver_enseignant(enseignant_id)
                st.success("Enseignant désactivé. Il reste consultable dans l'historique.")
                st.rerun()
        else:
            if st.button("Réactiver cet enseignant"):
                reactiver_enseignant(enseignant_id)
                st.success("Enseignant réactivé.")
                st.rerun()

    # --- Supprimer définitivement (irréversible) ---------------------
    with onglet_suppression:
        if not permission_service.a_permission(utilisateur_courant_role(), permission_service.ENSEIGNANT_SUPPRIMER):
            st.info("La suppression définitive est réservée aux administrateurs.")
            st.stop()
        nom_complet = f"{enseignant_selectionne.nom} {enseignant_selectionne.prenom}"
        st.write(f"**Nom :** {enseignant_selectionne.nom}")
        st.write(f"**Prénom :** {enseignant_selectionne.prenom}")
        st.write(f"**Statut :** {libelle_statut(enseignant_selectionne.statut)}")

        dependances = obtenir_dependances_enseignant(enseignant_id)
        st.markdown(
            f"- {dependances.nombre_heures} semaine(s) d'heures enregistrée(s)\n"
            f"- {dependances.nombre_elements_remuneration} élément(s) de rémunération\n"
            f"- {dependances.nombre_retenues} retenue(s)\n"
            f"- {'Oui' if dependances.a_des_bulletins else 'Aucun'} bulletin généré"
        )

        cle_confirmation = f"confirmation_suppression_{enseignant_id}"

        if dependances.a_des_bulletins:
            # CAS 3 : la règle ne peut jamais être contournée depuis
            # l'interface — aucun bouton de suppression n'est même affiché.
            st.error(MESSAGE_BULLETIN_EXISTANT)
        else:
            if dependances.a_des_donnees_de_paie:
                st.warning(
                    "Cet enseignant possède des données de paie sans bulletin généré. "
                    "Elles seront supprimées avec lui."
                )

            if not st.session_state.get(cle_confirmation, False):
                if st.button("Supprimer définitivement", type="primary"):
                    st.session_state[cle_confirmation] = True
                    st.rerun()
            else:
                st.error(
                    "ATTENTION — Cette opération est **définitive et irréversible**.\n\n"
                    f"Enseignant : **{nom_complet}**"
                )
                saisie_confirmation = st.text_input(
                    f"Tapez **{nom_complet}** pour confirmer la suppression définitive",
                    key=f"saisie_confirmation_{enseignant_id}",
                )
                col_confirmer, col_annuler = st.columns(2)
                with col_confirmer:
                    confirmation_valide = saisie_confirmation.strip() == nom_complet
                    if st.button("Confirmer la suppression", type="primary", disabled=not confirmation_valide):
                        try:
                            # Droits revérifiés en base par le service (ADMIN uniquement).
                            administration_service.supprimer_enseignant(
                                utilisateur_courant_id(), enseignant_id, confirmation=True
                            )
                            st.session_state.pop(cle_confirmation, None)
                            st.success(f"{nom_complet} a été supprimé définitivement.")
                            st.rerun()
                        except (EnseignantValidationError, AutorisationRefuseeError) as erreur:
                            st.session_state.pop(cle_confirmation, None)
                            st.error(str(erreur))
                    if saisie_confirmation and not confirmation_valide:
                        st.caption("Le texte saisi ne correspond pas exactement au nom demandé.")
                with col_annuler:
                    if st.button("Annuler"):
                        st.session_state.pop(cle_confirmation, None)
                        st.rerun()
