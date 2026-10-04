"""
Page Streamlit — Import du fichier de paie mensuel (classeur Excel).

L'utilisateur dépose le classeur de l'établissement (feuilles Heures, Global,
Comptable) : l'application lit chaque information, la présente dans un
tableau à compléter ou corriger, signale ce qui est à vérifier, puis
enregistre fiches et données de paie de la période après confirmation.
Aucune requête SQL ni formule de paie ici : tout passe par
services/import_fichier_paie_service.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from database.initialization import init_database
from models.enums import StatutPeriode
from services import import_fichier_paie_service as import_paie
from services import periode_service, permission_service
from services.import_service import TAILLE_MAX_OCTETS
from utils.formatters import formater_fcfa
from utils.session_auth import exiger_permission

init_database()
exiger_permission(permission_service.IMPORT_DONNEES)

st.title("Import du fichier de paie")
st.caption(
    "Déposez le classeur Excel de paie du mois (feuilles des heures, des informations des enseignants et état "
    "comptable) : chaque information est placée au bon endroit, vous complétez ou corrigez, puis vous validez. "
    "Rien n'est enregistré avant votre confirmation."
)

ETAT = "import_fichier_paie"
LIBELLES = {
    "importer": "Importer", "sn": "S/N", "nom_complet": "Noms et prénoms", "sexe": "Sexe", "statut": "Statut",
    "taux_horaire": "Taux horaire", "salaire_fixe": "Salaire fixe", "s1": "S1", "s2": "S2", "s3": "S3", "s4": "S4",
    "s5": "S5", "prime_ap_pp": "Prime AP/PP", "surveillance": "Surveillance/Secrétariat",
    "indemnite": "Indemnité", "retenue_amicale": "Retenue amicale", "dette": "Dette", "net_fichier": "Net du fichier",
    "remarques_fichier": "Remarques du fichier",
}
CHAMPS_PAR_LIBELLE = {libelle: champ for champ, libelle in LIBELLES.items()}

# =======================================================================
# 1. Période
# =======================================================================
st.header("1. Période de paie")
periodes_ouvertes = [p for p in periode_service.lister_periodes() if p.statut == StatutPeriode.OUVERTE]
if not periodes_ouvertes:
    st.info("Aucune période ouverte : créez et ouvrez la période du mois dans Gestion › Périodes de paie.")
    st.stop()
options = {p.libelle: p for p in periodes_ouvertes}
periode = options[st.selectbox("Période qui recevra les données", list(options))]

# =======================================================================
# 2. Fichier
# =======================================================================
st.header("2. Fichier Excel")
fichier = st.file_uploader(
    "Classeur de paie (.xlsx ou .xlsm), 10 Mo au maximum", type=["xlsx", "xlsm"],
    max_upload_size=TAILLE_MAX_OCTETS // (1024 * 1024),
)
if fichier is None:
    st.info("Sélectionnez le fichier de paie du mois pour continuer.")
    st.stop()

signature = (fichier.name, fichier.size, periode.id)
if st.session_state.get(f"{ETAT}_signature") != signature:
    try:
        lu = import_paie.lire_fichier_paie(fichier.getvalue(), fichier.name)
    except import_paie.ImportFichierPaieError as erreur:
        st.error(str(erreur))
        st.stop()
    st.session_state[f"{ETAT}_signature"] = signature
    st.session_state[f"{ETAT}_fichier"] = lu
    st.session_state[f"{ETAT}_lignes"] = lu.lignes
    st.session_state[f"{ETAT}_version"] = st.session_state.get(f"{ETAT}_version", 0) + 1
    st.session_state.pop(f"{ETAT}_rapport", None)

lu: import_paie.FichierPaie = st.session_state[f"{ETAT}_fichier"]
roles = {"heures": "heures", "global": "informations des enseignants", "comptable": "état comptable"}
st.success(
    f"Fichier lu : {lu.nom_fichier} — {len(lu.lignes)} enseignant(s). Feuilles reconnues : "
    + ", ".join(f"« {f.nom} » ({roles[f.role]})" for f in lu.feuilles) + "."
)
for remarque in lu.remarques:
    st.warning(remarque)

rapport = st.session_state.get(f"{ETAT}_rapport")
if rapport is not None:
    st.success(
        f"Import enregistré dans {periode.libelle} : {rapport.nb_lignes} enseignant(s), {rapport.nb_crees} fiche(s) "
        f"créée(s), {rapport.nb_mis_a_jour} mise(s) à jour. Continuez avec le calcul puis le contrôle de la paie."
    )
    col_calcul, col_controle = st.columns(2)
    col_calcul.page_link("ui_pages/4_Calcul_Paie.py", label="Calcul de paie", icon=":material/calculate:")
    col_controle.page_link("ui_pages/9_Controle_Paie.py", label="Contrôle de la paie", icon=":material/fact_check:")
    st.stop()

# =======================================================================
# 3. Vérification
# =======================================================================
lignes_verifiees = import_paie.verifier_lignes(st.session_state[f"{ETAT}_lignes"], periode.id)
a_importer = [l for l in lignes_verifiees if l.donnees.get("importer")]
en_erreur = [l for l in a_importer if l.erreurs]
a_verifier = [l for l in a_importer if l.remarques and not l.erreurs]
net_calcule = sum(l.net_calcule or 0 for l in a_importer)

st.header("3. Vérification")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Créations", sum(1 for l in a_importer if l.action == "Création"))
c2.metric("Mises à jour", sum(1 for l in a_importer if l.action == "Mise à jour"))
c3.metric("À vérifier", len(a_verifier))
c4.metric("Erreurs", len(en_erreur))
c5.metric("Salaires fixes", sum(1 for l in a_importer if l.donnees.get("salaire_fixe") is not None))
if lu.total_net_fichier is not None:
    ecart_total = net_calcule - lu.total_net_fichier
    st.write(
        f"Net total du fichier : **{formater_fcfa(lu.total_net_fichier)}** · net total calculé par l'application : "
        f"**{formater_fcfa(net_calcule)}**" + (f" (écart de {ecart_total:+,d} FCFA)".replace(",", " ") if ecart_total else "")
    )
deja = import_paie.nombre_enseignants_avec_donnees(periode.id)
if deja:
    st.info(f"{periode.libelle} contient déjà des données pour {deja} enseignant(s) : celles des enseignants du "
            "fichier seront remplacées par les valeurs du tableau.")

if en_erreur or a_verifier:
    st.subheader("Points à examiner")
    st.dataframe(
        [{"S/N": l.donnees.get("sn"), "Enseignant": l.donnees.get("nom_complet"),
          "Niveau": "Erreur" if l.erreurs else "À vérifier",
          "Détail": " ".join(l.erreurs + l.remarques)} for l in en_erreur + a_verifier],
        hide_index=True, use_container_width=True,
    )
    st.caption(
        "Les heures retenues sont celles de la feuille des heures. Un écart de net vient en général d'heures "
        "différentes entre les feuilles, de l'arrondi de la taxe, ou d'une prime que l'application taxe (la taxe "
        "de 5,5 % porte sur le gain et les primes des vacataires)."
    )
modifications = [l for l in a_importer if l.modifications]
if modifications:
    with st.expander(f"Fiches existantes modifiées par le fichier ({len(modifications)})"):
        st.dataframe([{"Enseignant": l.donnees.get("nom_complet"), "Changements": " ; ".join(l.modifications)}
                      for l in modifications], hide_index=True, use_container_width=True)

# =======================================================================
# 4. Tableau à compléter ou corriger
# =======================================================================
st.header("4. Compléter ou corriger")
st.caption(
    "Modifiez directement les cases (double-clic), décochez « Importer » pour écarter une ligne, puis cliquez sur "
    "« Vérifier à nouveau ». Statut : V (vacataire) ou P (permanent). Le salaire fixe remplace heures × taux "
    "pour un permanent payé au mois."
)
tableau = pd.DataFrame(
    [
        {**{LIBELLES[c]: l.donnees.get(c) for c in import_paie.COLONNES if c != "remarques_fichier"},
         "Action": l.action, "Net calculé": l.net_calcule,
         "À vérifier": " ".join(l.erreurs + l.remarques)}
        for l in lignes_verifiees
    ]
)
lecture_seule = ["S/N", "Net du fichier", "Net calculé", "Action", "À vérifier"]
config = {
    "Importer": st.column_config.CheckboxColumn(width="small"),
    "Sexe": st.column_config.SelectboxColumn(options=["M", "F"], width="small"),
    "Statut": st.column_config.SelectboxColumn(options=["V", "P"], width="small"),
    "Taux horaire": st.column_config.NumberColumn(min_value=0, step=50, format="%d"),
    "Salaire fixe": st.column_config.NumberColumn(min_value=0, step=1000, format="%d"),
    **{f"S{n}": st.column_config.NumberColumn(min_value=0, step=0.5, width="small") for n in range(1, 6)},
    **{libelle: st.column_config.NumberColumn(min_value=0, step=500, format="%d")
       for libelle in ("Prime AP/PP", "Surveillance/Secrétariat", "Indemnité", "Retenue amicale", "Dette")},
    "Net du fichier": st.column_config.NumberColumn(format="%d"),
    "Net calculé": st.column_config.NumberColumn(format="%d"),
    "À vérifier": st.column_config.TextColumn(width="large"),
}
modifie = st.data_editor(
    tableau, column_config=config, disabled=lecture_seule, hide_index=True, use_container_width=True,
    num_rows="fixed", key=f"{ETAT}_editeur_{st.session_state[f'{ETAT}_version']}",
)


def _lignes_depuis_tableau(df: pd.DataFrame) -> list:
    remarques = [l.get("remarques_fichier") for l in st.session_state[f"{ETAT}_lignes"]]
    lignes = []
    for position, enregistrement in enumerate(df.to_dict(orient="records")):
        ligne = {champ: enregistrement.get(libelle) for libelle, champ in CHAMPS_PAR_LIBELLE.items()
                 if libelle in enregistrement}
        ligne["remarques_fichier"] = remarques[position] if position < len(remarques) else None
        lignes.append(ligne)
    return lignes


if st.button("Vérifier à nouveau", icon=":material/refresh:"):
    st.session_state[f"{ETAT}_lignes"] = _lignes_depuis_tableau(modifie)
    st.session_state[f"{ETAT}_version"] += 1
    st.rerun()

# =======================================================================
# 5. Validation
# =======================================================================
st.header("5. Valider")
lignes_finales = import_paie.verifier_lignes(_lignes_depuis_tableau(modifie), periode.id)
nb_finales = sum(1 for l in lignes_finales if l.donnees.get("importer"))
erreurs_finales = [l for l in lignes_finales if l.donnees.get("importer") and l.erreurs]
if erreurs_finales:
    st.error(f"{len(erreurs_finales)} ligne(s) comportent une erreur (colonne « À vérifier ») : corrigez-les ou "
             "décochez-les, puis cliquez sur « Vérifier à nouveau ».")
confirmation = st.checkbox(
    f"Je confirme l'enregistrement de {nb_finales} enseignant(s) dans la période {periode.libelle}."
)
if st.button("Enregistrer dans la période", type="primary", disabled=not confirmation or bool(erreurs_finales)):
    try:
        rapport = import_paie.enregistrer_lignes(
            lignes_finales, periode.id, lu.nom_fichier, utilisateur=st.session_state.get("username"),
        )
    except import_paie.ImportFichierPaieError as erreur:
        st.error(str(erreur))
    else:
        st.session_state[f"{ETAT}_rapport"] = rapport
        st.rerun()
