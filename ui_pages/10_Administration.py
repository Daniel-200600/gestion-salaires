"""
Page Streamlit — Administration (réservée au rôle ADMIN).

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL directe et AUCUNE formule de calcul de salaire.

Toutes les opérations sensibles (comptes, sauvegarde, restauration,
paramètres, diagnostic, réinitialisation des données) passent par
services/administration_service.py ou services/reinitialisation_service.py,
qui revérifient les droits de l'utilisateur en base : masquer un bouton
n'est jamais la seule protection.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hashlib
import platform
import sqlite3

import streamlit as st

from config.logging_config import lire_dernieres_lignes, obtenir_logger
from config.settings import BACKUP_DIR, DB_PATH, MODELES_BULLETIN_DIR, NOM_APPLICATION, VERSION
from database.initialization import init_database
from models.enums import RoleUtilisateur
from services import (
    administration_service,
    backup_service,
    diagnostic_service,
    modele_bulletin_service,
    parametres_paie_service,
    parametres_service,
    periode_service,
    permission_service,
    reinitialisation_service,
    utilisateur_service,
)
from services.autorisation_service import AutorisationRefuseeError
from services.backup_service import BackupServiceError
from services.diagnostic_service import EtatSysteme
from services.parametres_service import ParametresEtablissement
from services.reinitialisation_service import (
    ELEMENTS_CONSERVES,
    LIBELLE_FICHIERS,
    PHRASE_CONFIRMATION,
    ReinitialisationError,
)
from services.modele_bulletin_service import LIBELLES_FORMAT, ModeleBulletinError
from services.utilisateur_service import UtilisateurValidationError
from exports import pdf_export
from utils.balises_bulletin import BALISES
from utils.detection_bulletin import meme_ligne
from utils.session_auth import exiger_permission, utilisateur_courant_id, utilisateur_courant_role

init_database()
logger = obtenir_logger("page_administration")

exiger_permission(permission_service.ADMINISTRATION_CONSULTER)
acteur_id = utilisateur_courant_id()

st.title("Administration")
st.caption(
    "Paramètres de l'établissement et de paie, modèles de bulletin, comptes utilisateurs, sauvegardes, restauration, diagnostic, "
    "maintenance, journaux techniques et réinitialisation des données. Page réservée aux administrateurs."
)

LIBELLES_ROLES = administration_service.LIBELLES_ROLES
ROLES_PAR_LIBELLE = {libelle: role for role, libelle in LIBELLES_ROLES.items()}

(
    onglet_parametres, onglet_modeles, onglet_utilisateurs, onglet_sauvegarde, onglet_restauration,
    onglet_diagnostic, onglet_maintenance, onglet_logs, onglet_reinitialisation, onglet_apropos,
) = st.tabs([
    "Paramètres", "Modèles de bulletin", "Utilisateurs", "Sauvegarde", "Restauration", "Diagnostic",
    "Maintenance", "Journaux", "Réinitialisation des données", "À propos",
])

# =======================================================================
# Onglet Paramètres
# =======================================================================
with onglet_parametres:
    st.subheader("Informations de l'établissement")
    st.caption("Ces informations sont enregistrées sur disque et conservées après un redémarrage de l'application.")

    parametres_actuels = parametres_service.charger_parametres()

    with st.form("formulaire_parametres_etablissement"):
        nom_etablissement = st.text_input("Nom de l'établissement", value=parametres_actuels.nom_etablissement)
        adresse = st.text_input("Adresse", value=parametres_actuels.adresse)
        col_tel, col_email = st.columns(2)
        with col_tel:
            telephone = st.text_input("Téléphone", value=parametres_actuels.telephone)
        with col_email:
            email = st.text_input("Adresse électronique", value=parametres_actuels.email)
        col_annee, col_devise = st.columns(2)
        with col_annee:
            annee_scolaire = st.text_input("Année scolaire", value=parametres_actuels.annee_scolaire)
        with col_devise:
            devise = st.text_input("Devise (affichage uniquement)", value=parametres_actuels.devise)
        col_nom_resp, col_fonction_resp = st.columns(2)
        with col_nom_resp:
            nom_responsable = st.text_input("Nom du responsable", value=parametres_actuels.nom_responsable)
        with col_fonction_resp:
            fonction_responsable = st.text_input(
                "Fonction du responsable", value=parametres_actuels.fonction_responsable
            )

        if st.form_submit_button("Enregistrer les paramètres", type="primary"):
            nouveaux_parametres = ParametresEtablissement(
                nom_etablissement=nom_etablissement.strip(),
                adresse=adresse.strip(),
                telephone=telephone.strip(),
                email=email.strip(),
                annee_scolaire=annee_scolaire.strip(),
                devise=devise.strip() or "FCFA",
                nom_responsable=nom_responsable.strip(),
                fonction_responsable=fonction_responsable.strip(),
            )
            try:
                administration_service.enregistrer_parametres(acteur_id, nouveaux_parametres)
                logger.info("Paramètres de l'établissement modifiés depuis l'interface.")
                st.success("Paramètres enregistrés.")
                st.rerun()
            except AutorisationRefuseeError as erreur:
                st.error(str(erreur))

    st.divider()
    st.subheader("Paramètres de paie")
    taux_defaut = parametres_paie_service.obtenir_taux_taxe_defaut()
    col_taux, col_devise_calc, col_semaines = st.columns(3)
    col_taux.metric("Taux de taxe par défaut", parametres_paie_service.formater_taux(taux_defaut))
    col_devise_calc.metric("Devise de calcul", "FCFA")
    from config.settings import NB_SEMAINES_PAR_PERIODE
    col_semaines.metric("Semaines par période", NB_SEMAINES_PAR_PERIODE)

    st.markdown("**Taux de taxe**")
    st.caption(
        "Le taux par défaut est recopié sur chaque nouvelle période. Le taux d'une période reste "
        "ajustable (Gestion › Périodes de paie) tant qu'elle n'est pas validée, puis il est figé : "
        "les bulletins validés ou clôturés sont toujours recalculés à l'identique. Modifier le taux "
        "par défaut ne change aucune période existante."
    )
    with st.form("formulaire_taux_taxe"):
        nouveau_pourcentage = st.number_input(
            "Taux de taxe par défaut (%)", min_value=0.0, max_value=50.0, step=0.5, format="%.2f",
            value=float(parametres_paie_service.taux_vers_pourcentage(taux_defaut)),
            help="Exemple : 5,5 % = 5 % d'impôt + 10 % de centimes additionnels communaux.",
        )
        appliquer_periodes_ouvertes = st.checkbox(
            "Appliquer aussi ce taux aux périodes en brouillon ou ouvertes", value=False,
        )
        if st.form_submit_button("Enregistrer le taux", type="primary"):
            try:
                administration_service.definir_taux_taxe_defaut(acteur_id, f"{nouveau_pourcentage:.2f}")
                modifiees = []
                if appliquer_periodes_ouvertes:
                    for periode_modifiable in periode_service.lister_periodes():
                        if parametres_paie_service.taux_periode_modifiable(periode_modifiable):
                            administration_service.definir_taux_taxe_periode(
                                acteur_id, periode_modifiable.id, f"{nouveau_pourcentage:.2f}"
                            )
                            modifiees.append(periode_modifiable.libelle)
                message = "Taux de taxe par défaut enregistré."
                if modifiees:
                    message += " Périodes mises à jour : " + ", ".join(modifiees) + "."
                st.success(message)
                st.rerun()
            except (parametres_paie_service.ParametrePaieError, AutorisationRefuseeError) as erreur:
                st.error(str(erreur))

    with st.expander("Emplacements de stockage"):
        from config.settings import BACKUP_DIR as _BACKUP_DIR, DATA_DIR, LOGS_DIR
        from exports.excel_export import EXPORT_DIR
        from exports.word_export import EXPORT_DIR_BULLETINS, TEMPLATE_PATH
        st.code(
            f"Base de données     : {DB_PATH}\n"
            f"Dossier de données  : {DATA_DIR}\n"
            f"Exports Excel       : {EXPORT_DIR}\n"
            f"Bulletins           : {EXPORT_DIR_BULLETINS}\n"
            f"Sauvegardes         : {_BACKUP_DIR}\n"
            f"Journaux techniques : {LOGS_DIR}\n"
            f"Modèle Word standard: {TEMPLATE_PATH}\n"
            f"Modèles importés    : {MODELES_BULLETIN_DIR}",
            language=None,
        )

# =======================================================================
# Onglet Modèles de bulletin
# =======================================================================
MIME_PAR_FORMAT = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
CHAMP_TEXTE_FIXE = "— texte fixe (ne pas remplacer) —"
LIBELLES_CHAMPS = {f"{b.libelle} [{b.nom}]": b.nom for b in BALISES}
CHAMPS_PAR_BALISE = {nom: libelle for libelle, nom in LIBELLES_CHAMPS.items()}


def _afficher_apercu(format_, contenu_bulletin: bytes, nom_fichier: str, cle: str) -> None:
    """Aperçu d'un bulletin d'essai : image pour un PDF, téléchargement dans tous les cas."""
    if format_ == "pdf":
        st.image(pdf_export.apercu_png(contenu_bulletin), caption="Bulletin d'essai (valeurs d'exemple)")
    else:
        st.caption("Aperçu Word : téléchargez le bulletin d'essai pour l'ouvrir dans Word.")
    st.download_button(
        "Télécharger le bulletin d'essai", data=contenu_bulletin, file_name=nom_fichier,
        mime=MIME_PAR_FORMAT[format_], key=f"essai_{cle}",
    )


with onglet_modeles:
    st.subheader("Modèle de bulletin actif")
    modele_actif = modele_bulletin_service.obtenir_modele_actif()
    probleme_modele = modele_bulletin_service.probleme_modele_actif()
    if probleme_modele:
        st.warning(probleme_modele, icon=":material/warning:")
    st.write(
        f"Les bulletins sont produits avec le modèle **{modele_actif.libelle}**. "
        "Un seul modèle est actif à la fois ; le changement s'applique aux bulletins générés ensuite, "
        "les fichiers déjà produits ne sont pas modifiés."
    )

    st.subheader("Modèles disponibles")
    modeles = modele_bulletin_service.lister_modeles()
    st.dataframe(
        [
            {
                "Modèle": m.nom,
                "Format": LIBELLES_FORMAT[m.format],
                "Origine": "Standard (bulletin officiel)" if m.standard
                else f"Importé le {m.date_import} par {m.utilisateur or '—'} ({m.nom_fichier_origine})",
                "Actif": "Oui" if m.cle == modele_actif.cle else "Non",
            }
            for m in modeles
        ],
        use_container_width=True, hide_index=True,
    )
    libelles_modeles = {f"{m.libelle}{' — importé' if not m.standard else ''} [{m.cle}]": m for m in modeles}
    choix_modele = libelles_modeles[st.selectbox("Choisir un modèle", list(libelles_modeles))]
    col_activer, col_essai, col_supprimer = st.columns(3)
    with col_activer:
        if st.button("Activer ce modèle", disabled=choix_modele.cle == modele_actif.cle):
            try:
                administration_service.activer_modele_bulletin(acteur_id, choix_modele.cle)
                st.success(f"Modèle activé : {choix_modele.libelle}.")
                st.rerun()
            except (ModeleBulletinError, AutorisationRefuseeError) as erreur:
                st.error(str(erreur))
    with col_essai:
        if st.button("Produire un bulletin d'essai"):
            try:
                st.session_state["essai_modele"] = (
                    choix_modele.cle, modele_bulletin_service.apercu_modele(choix_modele)
                )
            except ModeleBulletinError as erreur:
                st.error(str(erreur))
    with col_supprimer:
        if not choix_modele.standard:
            confirme_suppression_modele = st.checkbox("Confirmer la suppression", key="confirme_suppr_modele")
            if st.button("Supprimer ce modèle", disabled=not confirme_suppression_modele):
                try:
                    administration_service.supprimer_modele_bulletin(acteur_id, choix_modele.cle)
                    st.success("Modèle supprimé.")
                    st.rerun()
                except (ModeleBulletinError, AutorisationRefuseeError) as erreur:
                    st.error(str(erreur))
    essai = st.session_state.get("essai_modele")
    if essai and essai[0] == choix_modele.cle:
        _afficher_apercu(choix_modele.format, essai[1], f"Bulletin_essai{choix_modele.extension}", "existant")

    st.divider()
    st.subheader("Ajouter un modèle (Word ou PDF)")
    st.markdown(
        "Deux possibilités :\n\n"
        "1. **Envoyer un bulletin déjà rempli** (par exemple un bulletin d'un mois précédent, en PDF exporté "
        "depuis Excel ou en Word). L'application repère le nom, la période, le statut, les heures, les "
        "montants et le net, puis vous propose les correspondances à vérifier.\n"
        "2. **Envoyer un modèle à balises** : un document où chaque valeur variable est remplacée par une "
        "balise, par exemple `{{NOM_COMPLET}}` ou `{{NET_A_PAYER}}` (liste ci-dessous). Dans un PDF, "
        "`{{NET_A_PAYER|centre}}` centre la valeur sur l'emplacement de la balise.\n\n"
        "Dans les deux cas, la mise en page, le logo, les couleurs et les textes fixes du document sont "
        "reproduits à l'identique. Un bulletin d'essai est produit avant l'enregistrement."
    )
    with st.expander("Liste des balises reconnues"):
        st.dataframe(
            [{"Balise": "{{" + b.nom + "}}", "Contenu": b.libelle, "Exemple": b.exemple, "Catégorie": b.categorie}
             for b in BALISES],
            use_container_width=True, hide_index=True,
        )
    st.download_button(
        "Télécharger le modèle Word standard (à balises, pour le personnaliser)",
        data=modele_bulletin_service.modele_standard_word().contenu(),
        file_name="Modele_bulletin_standard.docx", mime=MIME_PAR_FORMAT["docx"],
    )

    fichier_modele = st.file_uploader("Fichier du modèle (.docx ou .pdf, 10 Mo maximum)", type=["docx", "pdf"])
    if fichier_modele is not None:
        contenu_modele = fichier_modele.getvalue()
        empreinte_modele = hashlib.sha256(contenu_modele).hexdigest()
        analyse_en_cache = st.session_state.get("analyse_modele")
        if not analyse_en_cache or analyse_en_cache[0] != empreinte_modele:
            try:
                analyse_en_cache = (
                    empreinte_modele,
                    administration_service.analyser_modele_bulletin(acteur_id, contenu_modele, fichier_modele.name),
                )
                st.session_state["analyse_modele"] = analyse_en_cache
            except (ModeleBulletinError, AutorisationRefuseeError) as erreur:
                st.error(str(erreur))
                analyse_en_cache = None
        if analyse_en_cache:
            analyse = analyse_en_cache[1]
            correspondances, alignements = None, None
            if analyse.mode == "balises":
                st.write(f"Modèle à balises ({LIBELLES_FORMAT[analyse.format]}) : "
                         f"{len(analyse.balises)} balise(s) trouvée(s) — " + ", ".join(analyse.balises))
                for erreur in analyse.erreurs:
                    st.error(erreur)
                if analyse.recommandees_manquantes:
                    st.warning("Balises absentes (le modèle reste utilisable) : "
                               + ", ".join(analyse.recommandees_manquantes) + ".")
            else:
                st.info(
                    "Aucune balise dans ce document : il est traité comme un bulletin rempli. "
                    f"{len(analyse.propositions)} champ(s) reconnu(s) automatiquement. Vérifiez la colonne "
                    "« Champ » ligne par ligne, corrigez si besoin, puis produisez un bulletin d'essai."
                )
                # Champs reconnus en tête (dans l'ordre du document), puis les textes fixes.
                segments_tries = sorted(
                    analyse.segments,
                    key=lambda seg: (seg.id not in analyse.propositions, seg.page, round(seg.y0), seg.x0),
                )
                seulement_reconnus = st.checkbox("Afficher uniquement les champs reconnus", value=False)
                lignes_editeur = []
                for segment in segments_tries:
                    balise = analyse.propositions.get(segment.id, "")
                    if seulement_reconnus and not balise:
                        continue
                    voisins = " · ".join(
                        autre.texte for autre in segments_tries
                        if autre.id != segment.id and meme_ligne(autre, segment)
                    )
                    ligne = {
                        "Identifiant": segment.id,
                        "Texte du document": segment.texte,
                        "Même ligne": voisins[:80],
                        "Champ": CHAMPS_PAR_BALISE.get(balise, CHAMP_TEXTE_FIXE),
                    }
                    if analyse.format == "pdf":
                        ligne["Alignement"] = "centre"
                    lignes_editeur.append(ligne)
                configuration = {
                    "Identifiant": None,
                    "Texte du document": st.column_config.TextColumn("Texte du document", disabled=True),
                    "Même ligne": st.column_config.TextColumn("Textes sur la même ligne", disabled=True),
                    "Champ": st.column_config.SelectboxColumn(
                        "Champ", options=[CHAMP_TEXTE_FIXE] + list(LIBELLES_CHAMPS), required=True,
                    ),
                    "Alignement": st.column_config.SelectboxColumn(
                        "Alignement", options=["gauche", "centre", "droite"], required=True,
                    ),
                }
                edition = st.data_editor(
                    lignes_editeur, column_config=configuration, hide_index=True, use_container_width=True,
                    num_rows="fixed", key=f"editeur_{empreinte_modele}_{seulement_reconnus}", height=460,
                )
                correspondances = dict(analyse.propositions) if seulement_reconnus else {}
                alignements = {}
                for ligne in edition:
                    balise = LIBELLES_CHAMPS.get(ligne["Champ"])
                    if balise:
                        correspondances[ligne["Identifiant"]] = balise
                    else:
                        correspondances.pop(ligne["Identifiant"], None)
                    alignements[ligne["Identifiant"]] = ligne.get("Alignement") or "centre"
                for erreur in modele_bulletin_service.controler_correspondances(correspondances):
                    st.warning(erreur)

            nom_nouveau_modele = st.text_input(
                "Nom du modèle", value=Path(fichier_modele.name).stem[:80], max_chars=80,
            )
            activer_nouveau = st.checkbox("Activer ce modèle dès son enregistrement", value=True)
            col_apercu, col_enregistrer = st.columns(2)
            with col_apercu:
                if st.button("Produire un bulletin d'essai", key="essai_nouveau_modele"):
                    try:
                        contenu_construit, zones_construites = modele_bulletin_service.construire_modele(
                            contenu_modele, analyse, correspondances, alignements
                        )
                        st.session_state["essai_nouveau"] = (
                            empreinte_modele,
                            modele_bulletin_service.apercu(analyse.format, contenu_construit, zones_construites),
                        )
                    except ModeleBulletinError as erreur:
                        st.error(str(erreur))
            with col_enregistrer:
                if st.button("Enregistrer le modèle", type="primary"):
                    try:
                        nouveau = administration_service.importer_modele_bulletin(
                            acteur_id, nom_nouveau_modele, contenu_modele, fichier_modele.name,
                            correspondances=correspondances, alignements=alignements, activer=activer_nouveau,
                        )
                        st.session_state.pop("analyse_modele", None)
                        st.session_state.pop("essai_nouveau", None)
                        st.success(
                            f"Modèle « {nouveau.nom} » enregistré"
                            + (" et activé." if activer_nouveau else ".")
                        )
                    except (ModeleBulletinError, AutorisationRefuseeError) as erreur:
                        st.error(str(erreur))
            essai_nouveau = st.session_state.get("essai_nouveau")
            if essai_nouveau and essai_nouveau[0] == empreinte_modele:
                _afficher_apercu(analyse.format, essai_nouveau[1], f"Bulletin_essai.{analyse.format}", "nouveau")

# =======================================================================
# Onglet Utilisateurs
# =======================================================================
with onglet_utilisateurs:
    st.subheader("Gestion des comptes utilisateurs")
    st.caption(
        "Un compte désactivé ne peut plus se connecter mais reste conservé, ainsi que son historique. "
        "Chaque opération est enregistrée dans le journal d'audit (jamais les mots de passe)."
    )

    with st.expander("Créer un compte utilisateur"):
        with st.form("formulaire_creation_utilisateur"):
            col_nom, col_prenom = st.columns(2)
            with col_nom:
                nouveau_nom = st.text_input("Nom")
            with col_prenom:
                nouveau_prenom = st.text_input("Prénom")
            nouveau_username = st.text_input("Nom d'utilisateur")
            nouveau_role_libelle = st.selectbox("Rôle", list(ROLES_PAR_LIBELLE.keys()), key="role_creation")
            col_mdp, col_mdp_confirm = st.columns(2)
            with col_mdp:
                nouveau_mdp = st.text_input(
                    "Mot de passe (8 caractères minimum)", type="password", key="mdp_creation",
                    autocomplete="new-password",
                )
            with col_mdp_confirm:
                nouveau_mdp_confirm = st.text_input(
                    "Confirmer le mot de passe", type="password", key="mdp_creation_confirm",
                    autocomplete="new-password",
                )
            nouveau_actif = st.checkbox("Compte actif", value=True, key="actif_creation")

            if st.form_submit_button("Créer le compte", type="primary"):
                try:
                    administration_service.creer_compte(
                        acteur_id,
                        nom=nouveau_nom,
                        prenom=nouveau_prenom,
                        username=nouveau_username,
                        mot_de_passe=nouveau_mdp,
                        confirmation_mot_de_passe=nouveau_mdp_confirm,
                        role=ROLES_PAR_LIBELLE[nouveau_role_libelle],
                        actif=nouveau_actif,
                    )
                    logger.info("Utilisateur créé depuis l'interface : %s", nouveau_username)
                    st.success(f"Compte « {nouveau_username.strip()} » créé.")
                    st.rerun()
                except (UtilisateurValidationError, AutorisationRefuseeError) as erreur:
                    st.error(str(erreur))

    st.divider()
    st.markdown("**Liste des comptes**")

    tous_les_utilisateurs = utilisateur_service.lister_utilisateurs()
    if not tous_les_utilisateurs:
        st.info("Aucune donnée disponible.")
    else:
        lignes_utilisateurs = [
            {
                "Nom complet": u.nom_complet,
                "Nom d'utilisateur": u.username,
                "Rôle": LIBELLES_ROLES[u.role],
                "Compte actif": "Oui" if u.actif else "Non",
                "Dernière connexion": u.derniere_connexion or "Jamais",
            }
            for u in tous_les_utilisateurs
        ]
        st.dataframe(lignes_utilisateurs, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("**Modifier un compte**")

        options_utilisateurs = {f"{u.username} — {u.nom_complet}": u.id for u in tous_les_utilisateurs}
        choix_utilisateur = st.selectbox("Compte à modifier", list(options_utilisateurs.keys()))
        id_utilisateur_choisi = options_utilisateurs[choix_utilisateur]
        utilisateur_choisi = utilisateur_service.obtenir_utilisateur(id_utilisateur_choisi)
        est_mon_compte = id_utilisateur_choisi == acteur_id

        onglet_infos, onglet_statut_util, onglet_reinit_mdp = st.tabs(
            ["Informations et rôle", "Activer ou désactiver", "Réinitialiser le mot de passe"]
        )

        with onglet_infos:
            if est_mon_compte:
                st.caption("Il s'agit de votre compte : votre propre rôle ne peut être modifié que par un autre administrateur.")
            with st.form(f"form_modifier_utilisateur_{id_utilisateur_choisi}"):
                col_nom_mod, col_prenom_mod = st.columns(2)
                with col_nom_mod:
                    nom_modifie_util = st.text_input("Nom", value=utilisateur_choisi.nom)
                with col_prenom_mod:
                    prenom_modifie_util = st.text_input("Prénom", value=utilisateur_choisi.prenom)
                libelles = list(ROLES_PAR_LIBELLE.keys())
                role_modifie_libelle = st.selectbox(
                    "Rôle",
                    libelles,
                    index=libelles.index(LIBELLES_ROLES[utilisateur_choisi.role]),
                    key="role_modif",
                    disabled=est_mon_compte,
                )
                if st.form_submit_button("Enregistrer les modifications", type="primary"):
                    try:
                        administration_service.modifier_compte(
                            acteur_id,
                            id_utilisateur_choisi,
                            nom=nom_modifie_util,
                            prenom=prenom_modifie_util,
                            role=ROLES_PAR_LIBELLE[role_modifie_libelle],
                        )
                        logger.info("Utilisateur modifié depuis l'interface : id=%s", id_utilisateur_choisi)
                        st.success("Compte modifié.")
                        st.rerun()
                    except (UtilisateurValidationError, AutorisationRefuseeError) as erreur:
                        st.error(str(erreur))

        with onglet_statut_util:
            if utilisateur_choisi.actif:
                st.write("État actuel du compte : **actif**.")
                if est_mon_compte:
                    st.caption("Vous ne pouvez pas désactiver votre propre compte.")
                elif st.button("Désactiver ce compte"):
                    try:
                        administration_service.desactiver_compte(acteur_id, id_utilisateur_choisi)
                        logger.info("Utilisateur désactivé depuis l'interface : id=%s", id_utilisateur_choisi)
                        st.success("Compte désactivé.")
                        st.rerun()
                    except (UtilisateurValidationError, AutorisationRefuseeError) as erreur:
                        st.error(str(erreur))
            else:
                st.write("État actuel du compte : **désactivé**.")
                if st.button("Réactiver ce compte"):
                    try:
                        administration_service.activer_compte(acteur_id, id_utilisateur_choisi)
                        logger.info("Utilisateur réactivé depuis l'interface : id=%s", id_utilisateur_choisi)
                        st.success("Compte réactivé.")
                        st.rerun()
                    except (UtilisateurValidationError, AutorisationRefuseeError) as erreur:
                        st.error(str(erreur))

        with onglet_reinit_mdp:
            st.caption("Réinitialisation par un administrateur : l'ancien mot de passe n'est pas demandé.")
            with st.form(f"form_reinit_mdp_{id_utilisateur_choisi}"):
                nouveau_mdp_reinit = st.text_input(
                    "Nouveau mot de passe", type="password", autocomplete="new-password"
                )
                confirmation_mdp_reinit = st.text_input(
                    "Confirmer le nouveau mot de passe", type="password", autocomplete="new-password"
                )
                if st.form_submit_button("Réinitialiser le mot de passe", type="primary"):
                    if nouveau_mdp_reinit != confirmation_mdp_reinit:
                        st.error("Le mot de passe et sa confirmation ne correspondent pas.")
                    else:
                        try:
                            administration_service.reinitialiser_mot_de_passe_compte(
                                acteur_id, id_utilisateur_choisi, nouveau_mdp_reinit
                            )
                            logger.info(
                                "Mot de passe réinitialisé depuis l'interface : id=%s", id_utilisateur_choisi
                            )
                            st.success("Mot de passe réinitialisé.")
                        except (UtilisateurValidationError, AutorisationRefuseeError) as erreur:
                            st.error(str(erreur))

    st.divider()
    st.markdown("**Changer mon mot de passe**")
    with st.form("form_changer_mon_mot_de_passe"):
        mdp_actuel = st.text_input("Mot de passe actuel", type="password", autocomplete="current-password")
        nouveau_mdp_perso = st.text_input("Nouveau mot de passe", type="password", autocomplete="new-password")
        confirmation_mdp_perso = st.text_input(
            "Confirmer le nouveau mot de passe", type="password", autocomplete="new-password"
        )
        if st.form_submit_button("Changer mon mot de passe"):
            if nouveau_mdp_perso != confirmation_mdp_perso:
                st.error("Le nouveau mot de passe et sa confirmation ne correspondent pas.")
            else:
                try:
                    administration_service.changer_mon_mot_de_passe(acteur_id, mdp_actuel, nouveau_mdp_perso)
                    st.success("Mot de passe modifié.")
                except (UtilisateurValidationError, AutorisationRefuseeError) as erreur:
                    st.error(str(erreur))

# =======================================================================
# Onglet Sauvegarde
# =======================================================================
def _type_sauvegarde(nom: str) -> str:
    if nom.startswith(backup_service.PREFIXE_SAUVEGARDE_AUTO):
        return "Automatique"
    if nom.startswith(backup_service.PREFIXE_SAUVEGARDE):
        return "Manuelle"
    return "Sécurité (avant restauration ou réinitialisation)"


with onglet_sauvegarde:
    st.subheader("Créer une sauvegarde")
    st.caption(
        "Crée une copie cohérente et horodatée de la base de données dans le dossier des sauvegardes : "
        f"{BACKUP_DIR}"
    )

    if st.button("Créer une sauvegarde maintenant", type="primary"):
        try:
            chemin = administration_service.creer_sauvegarde(acteur_id)
            logger.info("Sauvegarde créée depuis l'interface : %s", chemin.name)
            st.success(f"Sauvegarde créée : {chemin.name}")
            st.rerun()
        except (BackupServiceError, AutorisationRefuseeError) as erreur:
            logger.error("Échec de sauvegarde depuis l'interface : %s", erreur)
            st.error(str(erreur))

    st.divider()
    st.subheader("Sauvegarde automatique")
    derniere_auto = next(iter(backup_service.lister_sauvegardes_automatiques()), None)
    st.caption(
        "Une sauvegarde est créée automatiquement chaque jour, à la première utilisation de "
        f"l'application ; les {backup_service.NOMBRE_SAUVEGARDES_AUTO_CONSERVEES} plus récentes sont "
        "conservées. Les sauvegardes manuelles ne sont jamais supprimées."
    )
    if derniere_auto is None:
        st.info("Aucune sauvegarde automatique pour l'instant.")
    else:
        st.success(f"Dernière sauvegarde automatique : {derniere_auto.date_creation.strftime('%d/%m/%Y à %H:%M')}.")

    st.divider()
    st.subheader("Sauvegardes disponibles")

    sauvegardes = backup_service.lister_sauvegardes()
    if not sauvegardes:
        st.info("Aucune donnée disponible. Aucune sauvegarde n'a encore été créée.")
    else:
        lignes_sauvegardes = [
            {
                "Nom": s.nom,
                "Type": _type_sauvegarde(s.nom),
                "Date": s.date_creation.strftime("%d/%m/%Y %H:%M:%S"),
                "Taille": s.taille_lisible,
                "Emplacement": str(s.chemin.parent),
            }
            for s in sauvegardes
        ]
        st.dataframe(lignes_sauvegardes, use_container_width=True, hide_index=True)

# =======================================================================
# Onglet Restauration
# =======================================================================
with onglet_restauration:
    st.subheader("Restaurer une sauvegarde")
    st.error(
        "Opération critique : la base de données active est remplacée par la sauvegarde choisie. "
        "Une sauvegarde de sécurité de la base actuelle est créée automatiquement avant le remplacement."
    )

    sauvegardes_disponibles = backup_service.lister_sauvegardes()
    if not sauvegardes_disponibles:
        st.info("Aucune donnée disponible. Aucune sauvegarde à restaurer.")
    else:
        options_sauvegardes = {
            f"{s.nom} — {s.date_creation.strftime('%d/%m/%Y %H:%M:%S')} ({s.taille_lisible})": s.chemin
            for s in sauvegardes_disponibles
        }
        choix_sauvegarde = st.selectbox("Sauvegarde à restaurer", list(options_sauvegardes.keys()))
        chemin_choisi = options_sauvegardes[choix_sauvegarde]

        resultat_verif = backup_service.verifier_integrite(chemin_choisi)
        if resultat_verif.valide:
            st.success(f"Vérification du fichier : conforme. {resultat_verif.message}")
        else:
            st.error(f"Vérification du fichier : échec. {resultat_verif.message}")

        cle_confirmation_restauration = "confirmation_restauration"
        if resultat_verif.valide:
            if not st.session_state.get(cle_confirmation_restauration, False):
                if st.button("Restaurer cette sauvegarde", type="primary"):
                    st.session_state[cle_confirmation_restauration] = True
                    st.rerun()
            else:
                st.warning(
                    f"Vous êtes sur le point de remplacer la base active par **{choix_sauvegarde}**. "
                    "Une sauvegarde de sécurité de l'état actuel sera créée auparavant."
                )
                saisie_confirmation = st.text_input("Pour confirmer, saisissez : JE CONFIRME CETTE OPÉRATION")
                col_confirmer, col_annuler = st.columns(2)
                with col_confirmer:
                    confirmation_valide = saisie_confirmation.strip() == "JE CONFIRME CETTE OPÉRATION"
                    if st.button("Confirmer la restauration", type="primary", disabled=not confirmation_valide):
                        st.session_state.pop(cle_confirmation_restauration, None)
                        try:
                            rapport = administration_service.restaurer_sauvegarde(
                                acteur_id, chemin_choisi, confirmation=True
                            )
                        except (BackupServiceError, AutorisationRefuseeError) as erreur:
                            st.error(str(erreur))
                        else:
                            if rapport.reussie:
                                logger.info("Restauration réussie depuis l'interface : %s", chemin_choisi.name)
                                st.success(rapport.message)
                            else:
                                logger.error("Échec de restauration depuis l'interface : %s", rapport.message)
                                st.error(rapport.message)
                            st.rerun()
                    if saisie_confirmation and not confirmation_valide:
                        st.caption("Le texte saisi ne correspond pas exactement au texte demandé.")
                with col_annuler:
                    if st.button("Annuler"):
                        st.session_state.pop(cle_confirmation_restauration, None)
                        st.rerun()

# =======================================================================
# Onglet Diagnostic
# =======================================================================
with onglet_diagnostic:
    st.subheader("Diagnostic du système")

    diagnostic = administration_service.diagnostiquer_systeme(acteur_id)

    libelles_etat = {
        EtatSysteme.VERT: "État global : système opérationnel.",
        EtatSysteme.ORANGE: "État global : points d'attention à examiner.",
        EtatSysteme.ROUGE: "État global : problème détecté.",
    }
    if diagnostic.etat_global == EtatSysteme.VERT:
        st.success(libelles_etat[diagnostic.etat_global])
    elif diagnostic.etat_global == EtatSysteme.ORANGE:
        st.warning(libelles_etat[diagnostic.etat_global])
    else:
        st.error(libelles_etat[diagnostic.etat_global])

    col1, col2, col3 = st.columns(3)
    col1.metric("Base accessible", "Oui" if diagnostic.base_accessible else "Non")
    col2.metric("Intégrité SQLite", "Conforme" if diagnostic.integrite.valide else "Échec")
    col3.metric("Taille de la base", diagnostic_service.formater_taille(diagnostic.taille_base_octets))
    if not diagnostic.integrite.valide:
        st.caption(f"Détail : {diagnostic.integrite.message}")

    st.markdown("**Tables essentielles**")
    lignes_tables = [{"Table": t.nom, "État": "Présente" if t.presente else "Manquante"} for t in diagnostic.tables]
    st.dataframe(lignes_tables, use_container_width=True, hide_index=True)
    if not diagnostic.toutes_tables_presentes:
        st.error("Erreur : table manquante. Vérifiez l'intégrité de la base ou restaurez une sauvegarde valide.")

    st.markdown("**Dénombrements**")
    col4, col5, col6, col7 = st.columns(4)
    col4.metric("Enseignants", diagnostic.nombre_enseignants)
    col5.metric("Périodes", diagnostic.nombre_periodes)
    col6.metric("Bulletins générés", diagnostic.nombre_bulletins)
    col7.metric("Lignes d'audit", diagnostic.nombre_lignes_audit)

    col8, col9, col10 = st.columns(3)
    col8.metric("Taille des exports", diagnostic_service.formater_taille(diagnostic.taille_exports_octets))
    col9.metric("Sauvegardes disponibles", diagnostic.nombre_sauvegardes)
    col10.metric("Modèle de bulletin", "Présent" if diagnostic.template_bulletin_present else "Absent")

    st.markdown("**Authentification**")
    col11, col12, col13 = st.columns(3)
    col11.metric("Comptes", diagnostic.nombre_utilisateurs)
    col12.metric("Comptes actifs", diagnostic.nombre_utilisateurs_actifs)
    col13.metric("Administrateurs actifs", diagnostic.nombre_admins_actifs)
    if diagnostic.nombre_utilisateurs > 0 and diagnostic.nombre_admins_actifs == 0:
        st.error("Aucun administrateur actif : l'application ne peut plus être administrée.")

    st.markdown("**Registre documentaire**")
    col14, col15, col16 = st.columns(3)
    col14.metric("Documents enregistrés", diagnostic.nombre_documents)
    col15.metric("Documents manquants", diagnostic.documents_manquants)
    col16.metric("Taille des documents", diagnostic_service.formater_taille(diagnostic.taille_documents_octets))
    if diagnostic.documents_manquants > 0:
        st.warning(
            f"{diagnostic.documents_manquants} document(s) référencé(s) en base introuvable(s) sur disque. "
            "Il s'agit d'une erreur documentaire, distincte d'un problème SQLite : voir la page "
            "Gestion des documents."
        )

    if diagnostic.dossiers_manquants:
        st.error(f"Dossiers manquants : {', '.join(diagnostic.dossiers_manquants)}")

# =======================================================================
# Onglet Maintenance
# =======================================================================
with onglet_maintenance:
    st.subheader("Vérifications de maintenance")
    st.caption(
        "Vérifications en lecture seule : aucune suppression de bulletin, d'historique, de sauvegarde "
        "ou de donnée de paie n'est effectuée ici."
    )

    if st.button("Lancer les vérifications"):
        diagnostic_maintenance = administration_service.diagnostiquer_systeme(acteur_id)
        logger.info("Vérification de maintenance lancée depuis l'interface.")

        verifications = [
            ("Base de données présente et accessible", diagnostic_maintenance.base_accessible),
            ("Intégrité SQLite", diagnostic_maintenance.integrite.valide),
            ("Toutes les tables essentielles présentes", diagnostic_maintenance.toutes_tables_presentes),
            ("Modèle de bulletin présent", diagnostic_maintenance.template_bulletin_present),
            ("Répertoires essentiels accessibles", diagnostic_maintenance.dossiers_essentiels_ok),
        ]
        lignes_verifications = [
            {"Vérification": libelle, "Résultat": "Conforme" if ok else "Échec"} for libelle, ok in verifications
        ]
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            lignes_verifications.append(
                {"Vérification": "Dossier de sauvegardes accessible en écriture", "Résultat": "Conforme"}
            )
        except OSError as erreur:
            lignes_verifications.append(
                {"Vérification": f"Dossier de sauvegardes accessible en écriture ({erreur})", "Résultat": "Échec"}
            )
        st.dataframe(lignes_verifications, use_container_width=True, hide_index=True)
        nombre_echecs = sum(1 for ligne in lignes_verifications if ligne["Résultat"] == "Échec")
        if nombre_echecs:
            st.error(f"{nombre_echecs} vérification(s) en échec.")
        else:
            st.success("Toutes les vérifications sont conformes.")

# =======================================================================
# Onglet Journaux
# =======================================================================
with onglet_logs:
    st.subheader("Journaux techniques")
    st.caption(
        "Événements techniques (erreurs, sauvegardes, restaurations, maintenance). Ils sont distincts du "
        "journal d'audit, qui trace les actions de gestion et reste consultable par période et par enseignant."
    )

    col_nb, col_recherche = st.columns([1, 2])
    with col_nb:
        nombre_lignes = st.number_input("Nombre de lignes récentes", min_value=10, max_value=1000, value=100, step=10)
    with col_recherche:
        terme_recherche_logs = st.text_input("Rechercher dans les journaux (facultatif)")

    lignes_log = lire_dernieres_lignes(nombre_lignes=int(nombre_lignes))
    if terme_recherche_logs.strip():
        lignes_log = [l for l in lignes_log if terme_recherche_logs.lower() in l.lower()]

    if not lignes_log:
        st.info("Aucune donnée disponible.")
    else:
        st.text_area("Dernières entrées", value="".join(lignes_log), height=400)

# =======================================================================
# Onglet Réinitialisation des données (distincte de la gestion des comptes)
# =======================================================================
with onglet_reinitialisation:
    st.subheader("Réinitialisation des données métier")

    if not permission_service.a_permission(utilisateur_courant_role(), permission_service.DONNEES_REINITIALISER):
        st.error("Accès refusé : cette opération est réservée aux administrateurs.")
    else:
        rapport_precedent = st.session_state.get("rapport_reinitialisation")
        if rapport_precedent is not None:
            if rapport_precedent.reussie:
                st.success(rapport_precedent.message)
            else:
                st.error(rapport_precedent.message)
            if rapport_precedent.sauvegarde_archive is not None:
                st.write(
                    f"Sauvegarde réalisée avant l'opération : **{rapport_precedent.sauvegarde_archive.name}**  \n"
                    f"Emplacement : `{rapport_precedent.sauvegarde_archive.parent}`"
                )
            if rapport_precedent.reussie:
                lignes = [{"Catégorie": k, "Éléments supprimés": v} for k, v in rapport_precedent.elements_supprimes.items()]
                lignes.append({"Catégorie": LIBELLE_FICHIERS, "Éléments supprimés": rapport_precedent.fichiers_supprimes})
                # Hauteur ajustée au nombre de lignes : tableau affiché en entier, sans défilement.
                st.dataframe(lignes, use_container_width=True, hide_index=True, height=(len(lignes) + 1) * 35 + 3)
                st.caption(f"Comptes utilisateurs conservés : {rapport_precedent.comptes_conserves}.")
            if st.button("Masquer ce compte rendu"):
                st.session_state.pop("rapport_reinitialisation", None)
                st.rerun()
            st.divider()

        st.error(
            "Opération destructive et définitive depuis l'interface : toutes les données métier de "
            "l'application sont supprimées. Les comptes utilisateurs ne sont pas concernés."
        )

        apercu = reinitialisation_service.apercu_reinitialisation()
        col_supprime, col_conserve = st.columns(2)
        with col_supprime:
            st.markdown("**Sera supprimé**")
            lignes_apercu = [{"Catégorie": k, "Nombre": v} for k, v in apercu.elements_a_supprimer.items()]
            lignes_apercu.append({"Catégorie": LIBELLE_FICHIERS, "Nombre": apercu.fichiers_a_supprimer})
            st.dataframe(
                lignes_apercu, use_container_width=True, hide_index=True, height=(len(lignes_apercu) + 1) * 35 + 3
            )
        with col_conserve:
            st.markdown("**Sera conservé**")
            st.markdown("\n".join(f"- {element}" for element in ELEMENTS_CONSERVES))
            st.caption(
                f"Comptes utilisateurs actuellement enregistrés : {apercu.comptes_conserves}. "
                f"Entrées du journal d'audit conservées : {apercu.entrees_audit_conservees}."
            )
        if apercu.tables_non_classees:
            st.warning(
                "Tables non reconnues, conservées sans modification : " + ", ".join(apercu.tables_non_classees)
            )

        st.markdown("**Déroulement**")
        st.markdown(
            f"1. Sauvegarde complète automatique (base de données et fichiers générés) dans `{BACKUP_DIR}`.\n"
            "2. Suppression des données dans une transaction unique.\n"
            "3. Vérification de l'intégrité de la base et de l'intégrité des comptes.\n"
            "4. En cas d'échec : annulation ou restauration automatique de la sauvegarde ; aucune donnée n'est perdue.\n"
            "5. Enregistrement de l'opération dans le journal d'audit (auteur, date, résultat, volumes)."
        )

        compteur = st.session_state.get("reinitialisation_compteur", 0)
        case_confirmee = st.checkbox(
            "Je confirme vouloir supprimer définitivement toutes les données métier listées ci-dessus. "
            "Les comptes utilisateurs seront conservés.",
            key=f"reinitialisation_case_{compteur}",
        )
        phrase_saisie = st.text_input(
            f"Pour confirmer, saisissez {PHRASE_CONFIRMATION} en majuscules "
            "(la saisie sans accent, REINITIALISER, est également acceptée)",
            key=f"reinitialisation_phrase_{compteur}",
        )
        phrase_valide = reinitialisation_service.phrase_confirmation_valide(phrase_saisie)
        if phrase_saisie and not phrase_valide:
            st.caption("Le texte saisi ne correspond pas au texte demandé.")

        if st.button(
            "Réinitialiser toutes les données métier",
            type="primary",
            disabled=not (case_confirmee and phrase_valide),
        ):
            try:
                with st.spinner("Sauvegarde puis réinitialisation en cours. Ne fermez pas cette page."):
                    rapport = reinitialisation_service.reinitialiser_donnees_metier(
                        acteur_id, phrase_saisie, confirmation=case_confirmee
                    )
            except (AutorisationRefuseeError, ReinitialisationError) as erreur:
                st.error(str(erreur))
            else:
                st.session_state["rapport_reinitialisation"] = rapport
                st.session_state["reinitialisation_compteur"] = compteur + 1
                st.rerun()

# =======================================================================
# Onglet À propos
# =======================================================================
with onglet_apropos:
    st.subheader("À propos")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Application**")
        st.write(f"Nom : {NOM_APPLICATION}")
        st.write(f"Version : {VERSION}")
        st.write("Base de données : SQLite (fichier local)")
    with col_b:
        st.markdown("**Environnement technique**")
        st.write(f"Python : {platform.python_version()}")
        st.write(f"Streamlit : {st.__version__}")
        st.write(f"SQLite : {sqlite3.sqlite_version}")

    periode_active = next(
        (p for p in periode_service.lister_periodes() if p.statut.value in ("ouverte", "validee")), None
    )
    st.divider()
    st.caption(
        f"Période active : {periode_active.libelle} ({periode_active.statut.value})"
        if periode_active else "Aucune période active."
    )
