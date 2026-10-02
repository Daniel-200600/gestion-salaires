"""
Page Streamlit — Module 18 : Automatisation & génération massive.

Règle d'architecture stricte : cette page orchestre uniquement
l'interface. Toute la logique vit dans
services/automatisation_service.py, lui-même une pure couche
d'orchestration des services existants — aucun calcul ni règle
métier propre.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from exports.excel_export import EXPORT_DIR
from exports.word_export import EXPORT_DIR_BULLETINS
from models.enums import StatutPeriode
from services import (
    automatisation_service, enseignant_service, modele_bulletin_service, periode_service, permission_service,
)
from services.automatisation_service import AutomatisationError
from utils.formatters import libelle_statut_periode
from utils.session_auth import exiger_permission

init_database()


exiger_permission(permission_service.AUTOMATISATION_EXECUTER)

st.title("Automatisation & génération massive")
st.caption(
    "Orchestre les opérations déjà existantes (bulletins, exports, archivage) sur un ensemble d'enseignants — "
    "aucun calcul ni règle métier n'est reproduit ici."
)
probleme_modele = modele_bulletin_service.probleme_modele_actif()
if probleme_modele:
    st.warning(probleme_modele, icon=":material/warning:")

periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode = st.selectbox("Période concernée", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode]

cle_operation = f"automatisation_derniere_operation_{periode_id}"

# =======================================================================
# 1. Préconditions
# =======================================================================
st.header("1. Préconditions")
precondition = automatisation_service.verifier_preconditions(periode_id)
if precondition.ok:
    st.success("Préconditions remplies : aucun problème bloquant détecté.")
else:
    st.error("Préconditions non remplies. Problèmes bloquants :")
    for probleme in precondition.problemes_bloquants:
        st.write(f"- {probleme}")
for avertissement in precondition.avertissements:
    st.warning(avertissement)

st.divider()

# =======================================================================
# 2. Génération massive des bulletins
# =======================================================================
st.header("2. Génération massive des bulletins")

enseignants = enseignant_service.lister_enseignants_payables()
_fiches_a_completer = enseignant_service.lister_enseignants_a_completer()
if _fiches_a_completer:
    st.info(
        f"{len(_fiches_a_completer)} enseignant(s) non proposé(s) ici : fiche à compléter (sexe, statut ou "
        "taux horaire manquant). Complétez-la dans Gestion › Enseignants pour l'inclure dans la paie."
    )
options_enseignants = {f"{e.nom} {e.prenom}": e.id for e in enseignants}
choix_enseignants = st.multiselect(
    "Limiter à certains enseignants (optionnel — tous par défaut)", list(options_enseignants.keys())
)
ids_choisis = [options_enseignants[c] for c in choix_enseignants] if choix_enseignants else None

if st.button("Simuler (aperçu, aucune écriture)"):
    analyse = automatisation_service.analyser_generation_bulletins(periode_id, enseignant_ids=ids_choisis)
    col1, col2, col3 = st.columns(3)
    col1.metric("Prêts", analyse.nombre_prets)
    col2.metric("Déjà existants", analyse.nombre_deja_existants)
    col3.metric("Erreurs potentielles", analyse.nombre_erreurs_potentielles)
    st.dataframe(
        [{"Enseignant": f"{l.nom} {l.prenom}", "État": l.etat, "Détail": l.detail} for l in analyse.lignes],
        use_container_width=True, hide_index=True,
    )

forcer = st.checkbox("Forcer la régénération des bulletins déjà existants")
if st.button("Générer les bulletins", type="primary", disabled=not precondition.ok):
    with st.spinner("Génération en cours..."):
        operation = automatisation_service.generer_bulletins_massif(
            periode_id, enseignant_ids=ids_choisis, forcer_regeneration=forcer,
            utilisateur=st.session_state.get("username"),
        )
    st.session_state[cle_operation] = operation
    st.success(
        f"Opération {operation.id} terminée : {operation.succes} succès, "
        f"{operation.ignores} ignoré(s), {operation.erreurs} erreur(s)."
    )
    st.rerun()

operation_courante = st.session_state.get(cle_operation)
if operation_courante is not None:
    st.markdown(f"**Dernière opération : `{operation_courante.id}`** ({operation_courante.statut.value})")
    st.dataframe(
        [{"Enseignant": f"{l.nom} {l.prenom}", "Statut": l.statut, "Détail": l.message} for l in operation_courante.lignes],
        use_container_width=True, hide_index=True,
    )
    if operation_courante.erreurs > 0:
        if st.button("Reprendre uniquement les erreurs"):
            try:
                nouvelle_operation = automatisation_service.reprendre_erreurs(
                    operation_courante, utilisateur=st.session_state.get("username")
                )
                st.session_state[cle_operation] = nouvelle_operation
                st.success(
                    f"Reprise terminée : {nouvelle_operation.succes} succès, "
                    f"{nouvelle_operation.erreurs} erreur(s) restante(s)."
                )
                st.rerun()
            except AutomatisationError as erreur:
                st.error(str(erreur))

st.divider()

# =======================================================================
# 3. Vérification d'intégrité
# =======================================================================
st.header("3. Vérification d'intégrité")
if st.button("Vérifier l'intégrité des documents de cette période"):
    rapport_integrite = automatisation_service.verifier_integrite_periode(
        periode_id, dossiers_a_scanner=[EXPORT_DIR_BULLETINS, EXPORT_DIR]
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Valides", rapport_integrite.nombre_valides)
    col2.metric("Manquants", rapport_integrite.nombre_manquants)
    col3.metric("Modifiés", rapport_integrite.nombre_modifies)

st.divider()

# =======================================================================
# 4. Archive massive
# =======================================================================
st.header("4. Archive de la période")
periode_actuelle = periode_service.obtenir_periode(periode_id)
if periode_actuelle.statut != StatutPeriode.CLOTUREE:
    st.info("L'archivage n'est possible que pour une période clôturée.")
else:
    if st.button("Créer l'archive de cette période"):
        rapport_archive = automatisation_service.archiver_periode_massif(
            periode_id, utilisateur=st.session_state.get("username"),
            dossier_destination=EXPORT_DIR / "archives",
        )
        st.success(f"Archive créée : {rapport_archive.chemin_archive.name} ({rapport_archive.nombre_documents} document(s)).")
        with open(rapport_archive.chemin_archive, "rb") as fichier:
            st.download_button(
                f"Télécharger {rapport_archive.chemin_archive.name}", data=fichier.read(),
                file_name=rapport_archive.chemin_archive.name, mime="application/zip",
            )

st.divider()

# =======================================================================
# 5. Pack de paie complet
# =======================================================================
st.header("5. Pack de paie complet")
st.caption("Assemble tous les documents déjà générés pour cette période (bulletins, exports, rapports) dans une archive unique.")
if st.button("Créer le pack de paie"):
    chemin_pack = automatisation_service.creer_pack_paie(
        periode_id, utilisateur=st.session_state.get("username"), dossier_destination=EXPORT_DIR / "packs",
    )
    st.success(f"Pack créé : {chemin_pack.name}")
    with open(chemin_pack, "rb") as fichier:
        st.download_button(
            f"Télécharger {chemin_pack.name}", data=fichier.read(), file_name=chemin_pack.name, mime="application/zip"
        )
