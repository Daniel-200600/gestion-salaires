"""
Page Streamlit — Module 15 : Importation de données.

Règle d'architecture stricte : cette page orchestre uniquement
l'interface. Toute la logique (lecture, normalisation, validation,
doublons, dry-run, transaction) vit dans services/import_service.py,
totalement indépendant de Streamlit.

Sécurité fichiers : le fichier téléversé par l'utilisateur est
toujours écrit sous un nom généré par l'application (jamais le nom
fourni par l'utilisateur) dans un dossier temporaire contrôlé — son
nom d'origine n'est conservé que pour l'affichage et la traçabilité.
"""

import sys
import tempfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from database.repositories import import_repository
from exports.import_template_export import generer_classeur_modele, generer_modele_csv
from models.enums import StrategieDoublon, TypeImport
from services import enseignant_service, import_service, periode_service, permission_service
from services.import_service import ImportServiceError
from utils.formatters import libelle_statut_periode
from utils.session_auth import exiger_permission

init_database()


exiger_permission(permission_service.IMPORT_DONNEES)

st.title("Importation de données")
st.caption(
    "Fichier → Analyse → Validation → Simulation → Confirmation → Import → Rapport. "
    "Aucune donnée n'est écrite en base avant confirmation explicite."
)

LIBELLES_TYPE = {
    TypeImport.ENSEIGNANTS: "Enseignants",
    TypeImport.HEURES: "Heures",
    TypeImport.REMUNERATIONS: "Rémunérations",
    TypeImport.RETENUES: "Retenues",
}

# =======================================================================
# Section 1 — Choisir le type d'import
# =======================================================================
st.header("1. Type d'import")
choix_type_libelle = st.radio("Que souhaitez-vous importer ?", list(LIBELLES_TYPE.values()), horizontal=True)
type_import = next(t for t, libelle in LIBELLES_TYPE.items() if libelle == choix_type_libelle)

periode_id_choisie = None
if type_import != TypeImport.ENSEIGNANTS:
    periodes = periode_service.lister_periodes()
    if not periodes:
        st.warning("Aucune période n'existe encore. Créez-en une avant d'importer ce type de données.")
        st.stop()
    options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
    choix_periode = st.selectbox("Période concernée", list(options_periodes.keys()))
    periode_id_choisie = options_periodes[choix_periode]

st.divider()

# =======================================================================
# Section 2 — Télécharger le modèle
# =======================================================================
st.header("2. Télécharger le modèle")
col_xlsx, col_csv = st.columns(2)
with col_xlsx:
    classeur_modele = generer_classeur_modele(type_import)
    tampon = BytesIO()
    classeur_modele.save(tampon)
    st.download_button(
        "Télécharger modèle Excel", data=tampon.getvalue(),
        file_name=f"template_import_{type_import.value}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with col_csv:
    st.download_button(
        "Télécharger modèle CSV", data=generer_modele_csv(type_import),
        file_name=f"template_import_{type_import.value}.csv", mime="text/csv",
    )

st.divider()

# =======================================================================
# Section 3 — Importer un fichier
# =======================================================================
st.header("3. Choisir un fichier")
if type_import == TypeImport.ENSEIGNANTS:
    st.info(
        "Vous pouvez importer votre liste d'enseignants existante telle quelle, en Excel, Word ou PDF : "
        "l'application lit le tableau qu'elle contient et reconnaît les intitulés usuels (Nom, Prénoms, "
        "« Nom et prénoms » dans une seule colonne, Sexe ou Genre, Statut, Taux horaire, Téléphone…). "
        "Seul le nom est obligatoire : une information absente (sexe, statut, taux horaire) se complète "
        "plus tard dans Gestion › Enseignants. Une fiche incomplète n'entre pas dans la paie."
    )
fichier_televerse = st.file_uploader(
    "Fichier Excel (.xlsx), CSV (.csv), Word (.docx) ou PDF (.pdf)", type=["xlsx", "csv", "docx", "pdf"]
)

cle_etat = f"import_pipeline_{type_import.value}"
if fichier_televerse is None:
    st.info("Sélectionnez un fichier pour continuer.")
    st.stop()

if st.session_state.get(f"{cle_etat}_nom_fichier") != fichier_televerse.name:
    st.session_state.pop(f"{cle_etat}_rapport_prep", None)
    st.session_state[f"{cle_etat}_nom_fichier"] = fichier_televerse.name

# Écrit le fichier téléversé sous un nom généré par l'application
# (jamais le nom fourni par l'utilisateur) dans un dossier temporaire.
suffixe = Path(fichier_televerse.name).suffix.lower()
chemin_temp = Path(tempfile.mkstemp(suffix=suffixe)[1])
chemin_temp.write_bytes(fichier_televerse.getvalue())

try:
    contenu = import_service.lire_fichier(chemin_temp, nom_fichier=fichier_televerse.name)
except ImportServiceError as erreur:
    st.error(str(erreur))
    st.stop()

unite = "tableau(x)" if suffixe in (".docx", ".pdf") else "feuille(s)"
st.success(f"Fichier lu : {contenu.nom_fichier} — {len(contenu.noms_feuilles)} {unite}.")

feuille_choisie = contenu.noms_feuilles[0]
if len(contenu.noms_feuilles) > 1:
    feuille_choisie = st.selectbox(
        "Tableau à importer" if suffixe in (".docx", ".pdf") else "Feuille à importer", contenu.noms_feuilles
    )

st.divider()

# =======================================================================
# Section 4 — Analyse
# =======================================================================
st.header("4. Analyse du fichier")
try:
    analyse = import_service.analyser_fichier(contenu, type_import, feuille=feuille_choisie)
except ImportServiceError as erreur:
    st.error(str(erreur))
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Lignes détectées", analyse.nombre_lignes)
col2.metric("Colonnes reconnues", len(analyse.colonnes_reconnues))
col3.metric("Colonnes non reconnues", len(analyse.colonnes_inconnues))

CHAMPS_ENSEIGNANT = {
    "nom": "Nom", "prenom": "Prénom(s)", "nom_complet": "Nom et prénoms (une seule colonne)",
    "sexe": "Sexe", "statut": "Statut (vacataire / permanent)", "taux_horaire": "Taux horaire",
    "telephone": "Téléphone", "email": "Adresse électronique", "adresse": "Adresse",
}
if type_import == TypeImport.ENSEIGNANTS:
    # L'administrateur vérifie, et corrige si besoin, la colonne associée à
    # chaque information (intitulés propres à chaque établissement).
    with st.expander("Vérifier l'association des colonnes", expanded=bool(analyse.colonnes_inconnues)):
        aucune = "— aucune —"
        colonne_de = {champ: colonne for colonne, champ in analyse.colonnes_reconnues.items()}
        correspondance = {}
        colonnes_cote = st.columns(3)
        for position, (champ, libelle) in enumerate(CHAMPS_ENSEIGNANT.items()):
            options = [aucune] + analyse.colonnes_detectees
            choix = colonnes_cote[position % 3].selectbox(
                libelle, options, index=options.index(colonne_de[champ]) if champ in colonne_de else 0,
                key=f"{cle_etat}_colonne_{champ}",
            )
            if choix != aucune:
                correspondance[choix] = champ
        analyse.colonnes_reconnues = correspondance
        analyse.colonnes_inconnues = [c for c in analyse.colonnes_detectees if c not in correspondance]
    if not set(analyse.colonnes_reconnues.values()) & {"nom", "nom_complet"}:
        st.error("Associez une colonne au nom (ou au « Nom et prénoms ») pour continuer.")
        st.stop()
    signature = tuple(sorted(analyse.colonnes_reconnues.items()))
    if st.session_state.get(f"{cle_etat}_signature_colonnes") != signature:
        st.session_state.pop(f"{cle_etat}_rapport_prep", None)
        st.session_state[f"{cle_etat}_signature_colonnes"] = signature

if analyse.colonnes_inconnues:
    st.warning("Colonnes non reconnues (ignorées) : " + ", ".join(analyse.colonnes_inconnues))
if not analyse.colonnes_reconnues:
    st.error("Aucune colonne du fichier n'a été reconnue. Vérifiez le modèle téléchargé.")
    st.stop()

st.divider()

# =======================================================================
# Section 5 — Prévisualisation
# =======================================================================
st.header("5. Prévisualisation")
st.dataframe(analyse.apercu, use_container_width=True, hide_index=True)
st.caption(f"Aperçu limité aux 10 premières lignes sur {analyse.nombre_lignes}.")

strategie = StrategieDoublon.REFUSER
if type_import == TypeImport.ENSEIGNANTS:
    libelles_strategie = {
        "Refuser les doublons": StrategieDoublon.REFUSER,
        "Ignorer les doublons": StrategieDoublon.IGNORER,
        "Mettre à jour les doublons": StrategieDoublon.METTRE_A_JOUR,
    }
    choix_strategie = st.selectbox("Stratégie face aux doublons", list(libelles_strategie.keys()))
    strategie = libelles_strategie[choix_strategie]

st.divider()

# =======================================================================
# Section 6 — Simulation (Dry Run)
# =======================================================================
st.header("6. Simulation")
df_a_traiter = contenu.feuilles[feuille_choisie]


def _preparer():
    if type_import == TypeImport.ENSEIGNANTS:
        return import_service.preparer_import_enseignants(analyse, df_a_traiter, strategie_doublon=strategie)
    elif type_import == TypeImport.HEURES:
        return import_service.preparer_import_heures(analyse, df_a_traiter, periode_id_choisie)
    elif type_import == TypeImport.REMUNERATIONS:
        return import_service.preparer_import_remunerations(analyse, df_a_traiter, periode_id_choisie)
    else:
        return import_service.preparer_import_retenues(analyse, df_a_traiter, periode_id_choisie)


if st.button("Lancer la simulation", type="primary"):
    try:
        with st.spinner("Analyse du fichier en cours..."):
            rapport_prep = _preparer()
        st.session_state[f"{cle_etat}_rapport_prep"] = rapport_prep
    except ImportServiceError as erreur:
        st.error(str(erreur))
        st.stop()

rapport_prep = st.session_state.get(f"{cle_etat}_rapport_prep")
if rapport_prep is not None:
    colA, colB, colC, colD, colE, colF = st.columns(6)
    colA.metric("Créations", rapport_prep.nb_creations)
    colB.metric("Mises à jour", rapport_prep.nb_mises_a_jour)
    colC.metric("Ignorées", rapport_prep.nb_ignorees)
    colD.metric("Rejetées", rapport_prep.nb_rejetees)
    colE.metric("Erreurs", rapport_prep.nb_erreurs)
    colF.metric("Fiches à compléter", rapport_prep.nb_fiches_incompletes)
    if rapport_prep.nb_fiches_incompletes:
        st.info(
            f"{rapport_prep.nb_fiches_incompletes} enseignant(s) seront enregistrés avec une fiche à compléter "
            "(sexe, statut ou taux horaire absent). Ils n'entreront dans la paie qu'une fois leur fiche "
            "complétée dans Gestion › Enseignants."
        )

    if rapport_prep.toutes_anomalies:
        lignes_anomalies = [
            {
                "Ligne": a.ligne, "Champ": a.champ or "—", "Valeur": a.valeur or "—",
                "Niveau": a.niveau.value.upper(), "Message": a.message,
            }
            for a in rapport_prep.toutes_anomalies
        ]
        st.dataframe(lignes_anomalies, use_container_width=True, hide_index=True)

    st.divider()

    # ===================================================================
    # Section 7 — Import réel (avec confirmation explicite, section 40)
    # ===================================================================
    st.header("7. Confirmer et importer")
    if rapport_prep.nb_creations + rapport_prep.nb_mises_a_jour == 0:
        st.info("Aucune ligne à importer (aucune création ni mise à jour après validation).")
    else:
        st.warning(
            f"Vous êtes sur le point d'importer :\n\n"
            f"- Fichier : **{contenu.nom_fichier}**\n"
            f"- Lignes analysées : **{rapport_prep.nb_lignes}**\n"
            f"- Créations : **{rapport_prep.nb_creations}**\n"
            f"- Mises à jour : **{rapport_prep.nb_mises_a_jour}**\n"
            f"- Ignorées : **{rapport_prep.nb_ignorees}**\n"
            f"- Rejetées : **{rapport_prep.nb_rejetees}**\n"
            f"- Fiches à compléter ensuite : **{rapport_prep.nb_fiches_incompletes}**\n\n"
            f"**Cette opération modifiera la base de données.**"
        )
        confirmation = st.checkbox("Je confirme cette importation.")
        if st.button("Confirmer et importer", type="primary", disabled=not confirmation):
            utilisateur = st.session_state.get("username")
            if type_import == TypeImport.ENSEIGNANTS:
                journal = import_service.executer_import_enseignants(
                    rapport_prep, contenu.nom_fichier, utilisateur=utilisateur
                )
            elif type_import == TypeImport.HEURES:
                journal = import_service.executer_import_heures(
                    rapport_prep, contenu.nom_fichier, periode_id_choisie, utilisateur=utilisateur
                )
            elif type_import == TypeImport.REMUNERATIONS:
                journal = import_service.executer_import_remunerations(
                    rapport_prep, contenu.nom_fichier, periode_id_choisie, utilisateur=utilisateur
                )
            else:
                journal = import_service.executer_import_retenues(
                    rapport_prep, contenu.nom_fichier, periode_id_choisie, utilisateur=utilisateur
                )

            from services import alert_detection_service
            alert_detection_service.detecter_alerte_import(journal)

            st.session_state[f"{cle_etat}_dernier_journal_id"] = journal.id
            st.session_state.pop(f"{cle_etat}_rapport_prep", None)
            st.rerun()

st.divider()

# =======================================================================
# Section 8 — Rapport
# =======================================================================
st.header("8. Rapport d'importation")
dernier_journal_id = st.session_state.get(f"{cle_etat}_dernier_journal_id")
if dernier_journal_id:
    journal = import_repository.obtenir_import(dernier_journal_id)
    if journal:
        libelle_statut_import = {
            "termine": "TERMINÉ", "echec": "ÉCHEC (annulé intégralement)",
        }.get(journal.statut.value, journal.statut.value)
        st.markdown(f"""
        **RAPPORT D'IMPORTATION**
        - Fichier : {journal.nom_fichier}
        - Date : {journal.date_import}
        - Utilisateur : {journal.utilisateur or '—'}
        - Lignes analysées : {journal.nb_lignes}
        - Créées/mises à jour : {journal.nb_creations + journal.nb_mises_a_jour}
        - Ignorées : {journal.nb_ignorees}
        - Rejetées : {journal.nb_rejetees}
        - Erreurs : {journal.nb_erreurs}
        - Avertissements : {journal.nb_avertissements}
        - Statut : {libelle_statut_import}
        """)
else:
    st.info("Aucun import récent à afficher pour cette session.")

if type_import == TypeImport.ENSEIGNANTS:
    a_completer = enseignant_service.lister_enseignants_a_completer()
    if a_completer:
        st.warning(
            f"{len(a_completer)} fiche(s) d'enseignant à compléter (sexe, statut ou taux horaire manquant). "
            "Ces enseignants n'entrent pas dans la paie tant que leur fiche est incomplète."
        )
        st.page_link("ui_pages/1_Enseignants.py", label="Compléter les fiches dans Gestion › Enseignants",
                     icon=":material/edit_note:")

with st.expander("Historique des imports"):
    imports_recents = import_repository.lister_imports(type_import=type_import)[:20]
    if imports_recents:
        lignes_historique = [
            {
                "Date": j.date_import, "Fichier": j.nom_fichier, "Utilisateur": j.utilisateur or "—",
                "Statut": j.statut.value, "Créations": j.nb_creations, "MAJ": j.nb_mises_a_jour,
                "Rejetées": j.nb_rejetees, "Erreurs": j.nb_erreurs,
            }
            for j in imports_recents
        ]
        st.dataframe(lignes_historique, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun import enregistré pour ce type de données.")
