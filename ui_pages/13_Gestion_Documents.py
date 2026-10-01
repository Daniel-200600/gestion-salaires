"""
Page Streamlit — Module 14 : Gestion des documents.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUN calcul de paie. Toutes les données proviennent de
services/document_service.py, services/document_integrity_service.py
et services/archive_service.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from database.repositories import audit_log_repository, enseignant_repository
from exports.excel_export import EXPORT_DIR
from exports.word_export import EXPORT_DIR_BULLETINS
from models.audit_log import AuditLog
from models.enums import StatutDocument, StatutPeriode, TypeActionAudit, TypeDocument
from services import archive_service, document_integrity_service, document_service, periode_service, permission_service
from services.archive_service import ArchiveServiceError
from utils.session_auth import exiger_permission, utilisateur_courant_role
from utils.ui_helpers import badge_statut_document

init_database()


exiger_permission(permission_service.DOCUMENT_CONSULTER)

role_courant = utilisateur_courant_role()
peut_archiver = permission_service.a_permission(role_courant, permission_service.DOCUMENT_ARCHIVER)

st.title("Gestion des documents")
st.caption("Registre, recherche et archivage des documents de paie (bulletins, états, exports).")

LIBELLES_TYPE = {
    TypeDocument.BULLETIN: "Bulletin",
    TypeDocument.RAPPORT_PAIE: "Rapport de paie",
    TypeDocument.ETAT_PAIE: "État de paie",
    TypeDocument.EXPORT_EXCEL: "Export Excel",
}
LIBELLES_STATUT_DOC = {
    StatutDocument.VALIDE: "Valide",
    StatutDocument.MANQUANT: "Manquant",
    StatutDocument.MODIFIE: "Modifié",
    StatutDocument.ORPHELIN: "Orphelin",
}

# =======================================================================
# 1. Recherche (section 16/19/20)
# =======================================================================
st.header("Recherche")

periodes = periode_service.lister_periodes()
enseignants = enseignant_repository.lister(inclure_inactifs=True)

col1, col2, col3 = st.columns(3)
with col1:
    options_periodes = {"Toutes": None}
    options_periodes.update({p.libelle: p.id for p in periodes})
    choix_periode = st.selectbox("Période", list(options_periodes.keys()))
with col2:
    options_enseignants = {"Tous": None}
    options_enseignants.update({f"{e.nom} {e.prenom}": e.id for e in enseignants})
    choix_enseignant = st.selectbox("Enseignant", list(options_enseignants.keys()))
with col3:
    options_types = {"Tous": None}
    options_types.update({v: k for k, v in LIBELLES_TYPE.items()})
    choix_type = st.selectbox("Type de document", list(options_types.keys()))

terme_recherche = st.text_input("Recherche rapide (nom de fichier — insensible à la casse)")

documents = document_service.rechercher_documents(
    periode_id=options_periodes[choix_periode],
    enseignant_id=options_enseignants[choix_enseignant],
    type_document=options_types[choix_type],
    terme_recherche=terme_recherche if terme_recherche.strip() else None,
)

st.divider()

# =======================================================================
# 2. Tableau des documents (section 17)
# =======================================================================
st.header("Documents")

if not documents:
    st.info("Aucune donnée disponible. Aucun document ne correspond à la recherche.")
else:
    enseignants_par_id = {e.id: e for e in enseignants}
    periodes_par_id = {p.id: p for p in periodes}

    lignes = []
    for d in documents:
        enseignant_libelle = "—"
        if d.enseignant_id and d.enseignant_id in enseignants_par_id:
            e = enseignants_par_id[d.enseignant_id]
            enseignant_libelle = f"{e.nom} {e.prenom}"
        periode_libelle = periodes_par_id[d.periode_id].libelle if d.periode_id in periodes_par_id else "—"
        statut = document_integrity_service.etat_leger(d)
        lignes.append({
            "Document": d.nom_fichier, "Type": LIBELLES_TYPE.get(d.type_document, d.type_document.value),
            "Enseignant": enseignant_libelle, "Période": periode_libelle, "Date": d.date_creation or "—",
            "Utilisateur": d.utilisateur or "—", "Statut": LIBELLES_STATUT_DOC[statut],
        })
    st.dataframe(lignes, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Consulter un document**")
    options_docs = {f"{d.nom_fichier} ({d.date_creation})": d for d in documents}
    choix_doc_libelle = st.selectbox("Sélectionner un document", list(options_docs.keys()))
    document_choisi = options_docs[choix_doc_libelle]

    col_a, col_b = st.columns(2)
    with col_a:
        st.write(f"**Type :** {LIBELLES_TYPE.get(document_choisi.type_document, document_choisi.type_document.value)}")
        st.write(f"**Date de génération :** {document_choisi.date_creation or '—'}")
        st.write(f"**Utilisateur :** {document_choisi.utilisateur or '—'}")
    with col_b:
        taille_affichee = f"{document_choisi.taille} octets" if document_choisi.taille else "—"
        st.write(f"**Taille :** {taille_affichee}")
        statut_document_choisi = document_integrity_service.etat_leger(document_choisi)
        st.markdown(
            f"**Statut :** {badge_statut_document(statut_document_choisi, LIBELLES_STATUT_DOC[statut_document_choisi])}",
            unsafe_allow_html=True,
        )

    chemin_document = Path(document_choisi.chemin)
    if chemin_document.exists():
        with open(chemin_document, "rb") as fichier:
            contenu_fichier = fichier.read()
        if st.download_button(f"Télécharger {document_choisi.nom_fichier}", data=contenu_fichier, file_name=document_choisi.nom_fichier):
            audit_log_repository.enregistrer(AuditLog(
                type_action=TypeActionAudit.DOCUMENT_TELECHARGE, entite="document", entite_id=document_choisi.id,
                utilisateur=st.session_state.get("username"), details=document_choisi.nom_fichier,
            ))
    else:
        st.error("Le fichier n'est plus présent sur le disque (document manquant).")

st.divider()

# =======================================================================
# 3. Vérification d'intégrité (section 14/15/38)
# =======================================================================
st.header("Vérification d'intégrité")
st.caption(
    "Le tableau ci-dessus affiche un état léger (présence du fichier uniquement). "
    "Cette vérification complète recalcule le hash de chaque document et détecte les orphelins."
)
if st.button("Vérifier l'intégrité maintenant"):
    rapport = document_integrity_service.verifier_integrite_complete(
        dossiers_a_scanner=[EXPORT_DIR_BULLETINS, EXPORT_DIR]
    )
    col_v, col_ma, col_mo, col_or = st.columns(4)
    col_v.metric("Valides", rapport.nombre_valides)
    col_ma.metric("Manquants", rapport.nombre_manquants)
    col_mo.metric("Modifiés", rapport.nombre_modifies)
    col_or.metric("Orphelins", len(rapport.documents_orphelins))

    if rapport.documents_manquants:
        st.warning("Manquants : " + ", ".join(d.nom_fichier for d in rapport.documents_manquants))
    if rapport.documents_modifies:
        st.error("Modifiés après génération : " + ", ".join(d.nom_fichier for d in rapport.documents_modifies))
    if rapport.documents_orphelins:
        st.info("Orphelins (présents sur disque, non référencés) : " + ", ".join(f.name for f in rapport.documents_orphelins))

    audit_log_repository.enregistrer(AuditLog(
        type_action=TypeActionAudit.DOCUMENT_INTEGRITE_VERIFIEE, entite="documents", entite_id=None,
        utilisateur=st.session_state.get("username"),
        details=f"{rapport.nombre_valides} valides, {rapport.nombre_manquants} manquants, "
                f"{rapport.nombre_modifies} modifiés, {len(rapport.documents_orphelins)} orphelins",
    ))

st.divider()

# =======================================================================
# 4. Archivage d'une période clôturée (section 21-25)
# =======================================================================
st.header("Archivage d'une période")

periodes_cloturees = [p for p in periodes if p.statut == StatutPeriode.CLOTUREE]
if not periodes_cloturees:
    st.info("Aucune période clôturée à archiver.")
elif not peut_archiver:
    st.info("Vous n'avez pas la permission d'archiver des documents.")
else:
    options_cloturees = {p.libelle: p.id for p in periodes_cloturees}
    choix_periode_archive = st.selectbox("Période à archiver", list(options_cloturees.keys()), key="periode_archive")
    periode_id_archive = options_cloturees[choix_periode_archive]

    if st.button("Archiver cette période", type="primary"):
        try:
            rapport_archive = archive_service.archiver_periode(
                periode_id_archive, utilisateur=st.session_state.get("username"),
                dossier_destination=EXPORT_DIR / "archives",
            )
            audit_log_repository.enregistrer(AuditLog(
                type_action=TypeActionAudit.ARCHIVE_CREEE, entite="periode_paie", entite_id=periode_id_archive,
                utilisateur=st.session_state.get("username"),
                details=f"{rapport_archive.chemin_archive.name} — {rapport_archive.nombre_documents} document(s)",
            ))
            st.success(f"Archive créée : {rapport_archive.chemin_archive.name} ({rapport_archive.nombre_documents} document(s)).")
            if rapport_archive.documents_manquants:
                st.warning("Documents manquants (non inclus) : " + ", ".join(rapport_archive.documents_manquants))

            with open(rapport_archive.chemin_archive, "rb") as fichier:
                contenu_archive = fichier.read()
            st.download_button(
                f"Télécharger {rapport_archive.chemin_archive.name}",
                data=contenu_archive, file_name=rapport_archive.chemin_archive.name, mime="application/zip",
            )
        except ArchiveServiceError as erreur:
            st.error(str(erreur))
