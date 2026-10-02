"""
Page Streamlit — Module 07 : Bulletins de solde (Word ou PDF selon le modèle actif).

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de calcul de salaire, et ne génère AUCUN document
Word directement. Elle appelle exclusivement services/bulletin_service.py
(lui-même basé sur services/paie_service.py) et exports/word_export.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from models.enums import StatutPeriode
from services import enseignant_service, modele_bulletin_service, periode_service
from services.bulletin_service import BulletinServiceError, creer_archive_zip, generer_bulletins_groupe
from services.controle_paie_service import controler_periode
from services.paie_service import CalculPaieError, calculer_paie_groupe
from utils.formatters import formater_fcfa, libelle_statut_periode

init_database()


def _mime(chemin: Path) -> str:
    if chemin.suffix.lower() == ".pdf":
        return "application/pdf"
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


from services import permission_service
from utils.session_auth import exiger_permission, utilisateur_courant_role

exiger_permission(permission_service.BULLETIN_CONSULTER)
peut_generer_bulletin = permission_service.a_permission(utilisateur_courant_role(), permission_service.BULLETIN_GENERER)
st.title("Génération des bulletins de solde")
modele_actif = modele_bulletin_service.obtenir_modele_actif()
st.caption(
    "Génère un bulletin individuel par enseignant, à partir des résultats déjà calculés par le moteur de paie. "
    f"Modèle utilisé : {modele_actif.libelle} (choix du modèle : Administration › Modèles de bulletin)."
)
probleme_modele = modele_bulletin_service.probleme_modele_actif()
if probleme_modele:
    st.warning(probleme_modele, icon=":material/warning:")

# =======================================================================
# 1. Sélection de la période
# =======================================================================
st.header("1. Sélection de la période")

periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période de paie", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)

st.metric("Statut de la période", libelle_statut_periode(periode.statut))
st.divider()

if periode.statut == StatutPeriode.BROUILLON:
    st.warning(
        "Cette période est encore au statut **Brouillon** : elle n'est pas prête pour la génération "
        "de bulletins. Ouvrez-la d'abord dans « Gestion des périodes de paie »."
    )
    st.stop()

if periode.statut == StatutPeriode.OUVERTE:
    st.info("Période **ouverte** : les bulletins générés sont **provisoires**, les données peuvent encore changer.")
elif periode.statut == StatutPeriode.VALIDEE:
    st.info("Période **validée** : les bulletins générés sont définitifs.")
elif periode.statut == StatutPeriode.CLOTUREE:
    st.warning(
        "Période **clôturée** : si un bulletin existe déjà pour un enseignant, sa régénération sera "
        "refusée afin de préserver l'historique."
    )

# =======================================================================
# 2. Sélection des enseignants
# =======================================================================
st.header("2. Sélection des enseignants")

# Une fiche incomplète n'a pas de paie : elle n'est pas proposée ici.
tous_enseignants = [e for e in enseignant_service.lister_enseignants(inclure_inactifs=True) if e.est_complet]
_fiches_a_completer = enseignant_service.lister_enseignants_a_completer()
if _fiches_a_completer:
    st.info(
        f"{len(_fiches_a_completer)} enseignant(s) non proposé(s) ici : fiche à compléter (sexe, statut ou "
        "taux horaire manquant). Complétez-la dans Gestion › Enseignants pour l'inclure dans la paie."
    )
if not tous_enseignants:
    st.info("Aucune donnée disponible. Aucun enseignant n'est enregistré.")
    st.stop()

options_enseignants = {f"{e.nom} {e.prenom}": e.id for e in tous_enseignants}
mode_selection = st.radio(
    "Portée de la génération",
    ["Sélection individuelle", "Tous les enseignants"],
    horizontal=True,
)

if mode_selection == "Tous les enseignants":
    enseignant_ids = list(options_enseignants.values())
    st.caption(f"{len(enseignant_ids)} enseignant(s) seront traités.")
else:
    choix_libelles = st.multiselect("Enseignant(s)", list(options_enseignants.keys()))
    enseignant_ids = [options_enseignants[libelle] for libelle in choix_libelles]

if not enseignant_ids:
    st.info("Sélectionnez au moins un enseignant.")
    st.stop()

# --- Contrôle informatif (n'empêche jamais la génération, signale seulement) ---
rapport_controle = controler_periode(periode_id, enseignant_ids=enseignant_ids)
if rapport_controle.erreurs:
    enseignants_en_erreur = {a.enseignant_nom for a in rapport_controle.erreurs if a.enseignant_nom}
    st.warning(
        f"{len(rapport_controle.erreurs)} anomalie(s) bloquante(s) détectée(s) sur cette sélection "
        f"(enseignants concernés : {', '.join(enseignants_en_erreur) or '—'}). "
        "Les bulletins seront tout de même générés à partir des données disponibles ; "
        "consultez la page « Contrôle de la paie » pour le détail."
    )
if rapport_controle.avertissements:
    st.caption(f"{len(rapport_controle.avertissements)} avertissement(s) — voir « Contrôle de la paie » pour le détail.")
st.caption(f"{len(enseignant_ids)} bulletin(s) seront générés.")

st.divider()

# =======================================================================
# 3. Prévisualisation des résultats (avant génération)
# =======================================================================
st.header("3. Prévisualisation")

try:
    groupe_calcule = calculer_paie_groupe(periode_id, enseignant_ids)
except CalculPaieError as erreur:
    st.error(str(erreur))
    st.stop()

if groupe_calcule.erreurs:
    details = "\n".join(f"- Enseignant id {eid} : {message}" for eid, message in groupe_calcule.erreurs.items())
    st.warning(f"{len(groupe_calcule.erreurs)} enseignant(s) n'ont pas pu être calculés :\n{details}")

if not groupe_calcule.resultats:
    st.info("Aucun résultat à afficher.")
    st.stop()

lignes_apercu = [
    {
        "Nom": r.nom,
        "Prénom": r.prenom,
        "Statut": r.statut.value,
        "Total heures": r.total_heures,
        "Gain": formater_fcfa(r.gain_heures),
        "Taxe": formater_fcfa(r.taxe_5),
        "Retenues": formater_fcfa(r.retenue_amicale + r.dette),
        "Net": formater_fcfa(r.net_a_percevoir),
    }
    for r in groupe_calcule.resultats
]
st.dataframe(lignes_apercu, use_container_width=True, hide_index=True)

st.divider()

# =======================================================================
# 4 & 5 & 6 & 7. Génération et téléchargement
# =======================================================================
st.header("4. Génération des bulletins")

if not peut_generer_bulletin:
    st.info("Vous n'avez pas la permission de générer des bulletins (consultation seule).")

enseignant_ids_a_generer = [r.enseignant_id for r in groupe_calcule.resultats]

if st.button("Générer les bulletins", type="primary", disabled=not peut_generer_bulletin):
    resultat_generation = generer_bulletins_groupe(
        periode_id, enseignant_ids_a_generer, utilisateur=st.session_state.get("username")
    )

    if resultat_generation.erreurs:
        details = "\n".join(
            f"- Enseignant id {eid} : {message}" for eid, message in resultat_generation.erreurs.items()
        )
        st.error(f"Certains bulletins n'ont pas pu être générés :\n{details}")

    if resultat_generation.bulletins:
        st.success(f"{len(resultat_generation.bulletins)} bulletin(s) généré(s) avec succès.")
        st.session_state["derniers_bulletins"] = resultat_generation.bulletins
        st.session_state["derniere_periode_libelle"] = periode.libelle
    else:
        st.session_state.pop("derniers_bulletins", None)

# =======================================================================
# Téléchargement (individuel ou ZIP)
# =======================================================================
bulletins_generes = st.session_state.get("derniers_bulletins")
if bulletins_generes:
    st.header("5. Téléchargement")

    if len(bulletins_generes) == 1:
        bulletin = bulletins_generes[0]
        with open(bulletin.chemin, "rb") as fichier:
            st.download_button(
                f"Télécharger le bulletin ({bulletin.chemin.name})",
                data=fichier.read(),
                file_name=bulletin.chemin.name,
                mime=_mime(bulletin.chemin),
            )
    else:
        libelle_periode = st.session_state.get("derniere_periode_libelle", periode.libelle)
        try:
            chemin_zip = creer_archive_zip(bulletins_generes, libelle_periode)
            with open(chemin_zip, "rb") as fichier_zip:
                st.download_button(
                    f"Télécharger l'archive ZIP ({chemin_zip.name}) — {len(bulletins_generes)} bulletins",
                    data=fichier_zip.read(),
                    file_name=chemin_zip.name,
                    mime="application/zip",
                )
        except BulletinServiceError as erreur:
            st.error(str(erreur))

        with st.expander("Télécharger un bulletin individuellement"):
            for bulletin in bulletins_generes:
                with open(bulletin.chemin, "rb") as fichier:
                    st.download_button(
                        f"{bulletin.chemin.name}",
                        data=fichier.read(),
                        file_name=bulletin.chemin.name,
                        mime=_mime(bulletin.chemin),
                        key=f"telechargement_{bulletin.enseignant_id}",
                    )
