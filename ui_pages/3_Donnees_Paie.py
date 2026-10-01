"""
Page Streamlit — Module 04 : Données de paie.

Règle d'architecture stricte : cette page ne contient AUCUNE requête
SQL et AUCUNE formule de salaire. Elle appelle exclusivement
services/heures_service.py, services/remuneration_service.py et
services/retenue_service.py. Le calcul du net à percevoir (gain
heures, base taxable, taxe 5 %, net) sera implémenté au module 05.
"""

import sys
from pathlib import Path

# Garantit que la racine du projet est importable, quelle que soit la
# façon dont Streamlit est lancé.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.initialization import init_database
from models.enums import StatutPeriode
from services import donnees_paie_service, enseignant_service, heures_service, periode_service, remuneration_service, retenue_service
from services.donnees_paie_service import DonneesPaieEnseignant
from services.heures_service import DonneesPaieValidationError
from utils.formatters import libelle_statut_periode

# Idempotent : garantit que les tables existent dès le premier lancement.
init_database()


from services import permission_service
from utils.session_auth import exiger_permission

exiger_permission(permission_service.PAIE_MODIFIER)
st.title("Données de paie")

SEMAINES = range(1, 6)

# =======================================================================
# 1. Sélection de la période
# =======================================================================
periodes = periode_service.lister_periodes()
if not periodes:
    st.info("Aucune donnée disponible. Aucune période de paie n'a été créée : voir Gestion › Périodes de paie.")
    st.stop()

options_periodes = {f"{p.libelle} — {libelle_statut_periode(p.statut)}": p.id for p in periodes}
choix_periode_libelle = st.selectbox("Période de paie", list(options_periodes.keys()))
periode_id = options_periodes[choix_periode_libelle]
periode = periode_service.obtenir_periode(periode_id)

st.divider()

if periode.statut == StatutPeriode.BROUILLON:
    st.warning(
        "Cette période est encore au statut **Brouillon**. Elle doit d'abord être ouverte "
        "(page « Gestion des périodes de paie ») avant toute saisie de données de paie."
    )
    st.stop()

lecture_seule = periode.statut in (StatutPeriode.VALIDEE, StatutPeriode.CLOTUREE)
if periode.statut == StatutPeriode.VALIDEE:
    st.info("Cette période est validée. Les données sont en lecture seule.")
elif periode.statut == StatutPeriode.CLOTUREE:
    st.info("Cette période est clôturée. Les données sont en lecture seule.")

# =======================================================================
# 2. Données déjà enregistrées sur cette période
# =======================================================================
heures_existantes = heures_service.lister_heures_periode(periode_id)
remuneration_existante = remuneration_service.lister_remuneration_periode(periode_id)
retenues_existantes = retenue_service.lister_retenues_periode(periode_id)
ids_avec_donnees = set(heures_existantes) | set(remuneration_existante) | set(retenues_existantes)

# =======================================================================
# 3. Sélection des enseignants
# =======================================================================
if lecture_seule:
    # En lecture seule, on affiche tous les enseignants ayant des
    # données sur la période, y compris ceux depuis désactivés
    # (historique consultable).
    tous_enseignants = enseignant_service.lister_enseignants(inclure_inactifs=True)
    enseignants_disponibles = [e for e in tous_enseignants if e.id in ids_avec_donnees]
else:
    # Une nouvelle saisie n'est jamais proposée pour un enseignant désactivé.
    enseignants_disponibles = enseignant_service.lister_enseignants(inclure_inactifs=False)

if not enseignants_disponibles:
    message = (
        "Aucune donnée enregistrée pour cette période."
        if lecture_seule
        else "Aucun enseignant actif disponible pour la saisie."
    )
    st.info(message)
    st.stop()

options_enseignants = {f"{e.nom} {e.prenom}": e.id for e in enseignants_disponibles}

if lecture_seule:
    enseignants_choisis_libelles = list(options_enseignants.keys())
    st.write(f"**{len(enseignants_choisis_libelles)} enseignant(s)** avec des données sur cette période.")
else:
    enseignants_choisis_libelles = st.multiselect(
        "Sélectionner un ou plusieurs enseignants pour la saisie",
        list(options_enseignants.keys()),
        default=[libelle for libelle, eid in options_enseignants.items() if eid in ids_avec_donnees],
    )

enseignant_ids = [options_enseignants[libelle] for libelle in enseignants_choisis_libelles]

if not enseignant_ids:
    st.info("Sélectionnez au moins un enseignant pour afficher la grille de saisie.")
    st.stop()

st.divider()

# =======================================================================
# 4. Aperçu des heures (le total est dérivé, jamais stocké)
# =======================================================================
st.subheader("Aperçu des heures")

apercu = []
for enseignant_id in enseignant_ids:
    enseignant = enseignant_service.obtenir_enseignant(enseignant_id)
    heures = heures_existantes.get(enseignant_id, {s: 0.0 for s in SEMAINES})
    ligne = {"Enseignant": f"{enseignant.nom} {enseignant.prenom}"}
    ligne.update({f"S{s}": heures.get(s, 0.0) for s in SEMAINES})
    ligne["Total"] = heures_service.total_heures(heures)
    apercu.append(ligne)

st.dataframe(apercu, use_container_width=True, hide_index=True)
st.caption("Le total est recalculé à partir des 5 semaines à chaque affichage : il n'est jamais stocké séparément.")

st.divider()

# =======================================================================
# 5. Saisie détaillée + enregistrement groupé (un seul formulaire)
# =======================================================================
st.subheader("Détail par enseignant" if not lecture_seule else "Détail par enseignant (lecture seule)")

with st.form("form_donnees_paie"):
    valeurs_saisies = {}

    for enseignant_id in enseignant_ids:
        enseignant = enseignant_service.obtenir_enseignant(enseignant_id)
        heures = heures_existantes.get(enseignant_id, {s: 0.0 for s in SEMAINES})
        remuneration = remuneration_existante.get(
            enseignant_id,
            {"prime_ap_pp": 0, "surveillance_secretariat": 0, "indemnite_suggestion_admin": 0},
        )
        retenues = retenues_existantes.get(enseignant_id, {"retenue_amicale": 0, "dette": 0})

        st.markdown(f"#### {enseignant.nom} {enseignant.prenom}")

        cols_heures = st.columns(5)
        heures_widget = {}
        for i, semaine in enumerate(SEMAINES):
            with cols_heures[i]:
                heures_widget[semaine] = st.number_input(
                    f"Semaine {semaine}",
                    min_value=0.0,
                    step=0.5,
                    value=float(heures.get(semaine, 0.0)),
                    disabled=lecture_seule,
                    key=f"heures_{periode_id}_{enseignant_id}_{semaine}",
                )
        st.caption(f"Total calculé : **{heures_service.total_heures(heures_widget):g} h**")

        col_r1, col_r2, col_r3, col_d1, col_d2 = st.columns(5)
        with col_r1:
            prime_ap_pp = st.number_input(
                "Prime AP/PP (FCFA)",
                min_value=0, step=100, format="%d",
                value=int(remuneration.get("prime_ap_pp", 0)),
                disabled=lecture_seule,
                key=f"prime_{periode_id}_{enseignant_id}",
            )
        with col_r2:
            surveillance_secretariat = st.number_input(
                "Surveillance/Secrétariat (FCFA)",
                min_value=0, step=100, format="%d",
                value=int(remuneration.get("surveillance_secretariat", 0)),
                disabled=lecture_seule,
                key=f"surveillance_{periode_id}_{enseignant_id}",
            )
        with col_r3:
            indemnite_suggestion_admin = st.number_input(
                "Indemnité suggestion/admin (FCFA)",
                min_value=0, step=100, format="%d",
                value=int(remuneration.get("indemnite_suggestion_admin", 0)),
                disabled=lecture_seule,
                key=f"indemnite_{periode_id}_{enseignant_id}",
            )
        with col_d1:
            retenue_amicale = st.number_input(
                "Retenue amicale (FCFA)",
                min_value=0, step=100, format="%d",
                value=int(retenues.get("retenue_amicale", 0)),
                disabled=lecture_seule,
                key=f"retenueamicale_{periode_id}_{enseignant_id}",
            )
        with col_d2:
            dette = st.number_input(
                "Dette (FCFA)",
                min_value=0, step=100, format="%d",
                value=int(retenues.get("dette", 0)),
                disabled=lecture_seule,
                key=f"dette_{periode_id}_{enseignant_id}",
            )

        valeurs_saisies[enseignant_id] = {
            "heures": heures_widget,
            "prime_ap_pp": prime_ap_pp,
            "surveillance_secretariat": surveillance_secretariat,
            "indemnite_suggestion_admin": indemnite_suggestion_admin,
            "retenue_amicale": retenue_amicale,
            "dette": dette,
        }
        st.divider()

    if not lecture_seule:
        soumis = st.form_submit_button("Enregistrer les données de paie")
        if soumis:
            groupe = [
                DonneesPaieEnseignant(
                    enseignant_id=enseignant_id,
                    heures_par_semaine=valeurs["heures"],
                    prime_ap_pp=valeurs["prime_ap_pp"],
                    surveillance_secretariat=valeurs["surveillance_secretariat"],
                    indemnite_suggestion_admin=valeurs["indemnite_suggestion_admin"],
                    retenue_amicale=valeurs["retenue_amicale"],
                    dette=valeurs["dette"],
                )
                for enseignant_id, valeurs in valeurs_saisies.items()
            ]
            try:
                # Une seule transaction pour tout le groupe : soit tous
                # les enseignants sont enregistrés, soit aucun ne l'est
                # (rollback complet en cas d'erreur, même en milieu de groupe).
                donnees_paie_service.enregistrer_donnees_paie_groupe(periode_id, groupe)
                st.success(f"Données de paie enregistrées pour {len(groupe)} enseignant(s).")
                st.rerun()
            except DonneesPaieValidationError as erreur:
                st.error(
                    f"Aucune donnée n'a été enregistrée (transaction annulée) : {erreur}"
                )
