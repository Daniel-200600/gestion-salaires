"""
Composants visuels partagés (amélioration UX/interface).

Ce module ne contient AUCUNE logique métier : il traduit des valeurs
déjà calculées ailleurs (statut de période, niveau d'alerte, statut
de document...) en badges colorés cohérents, réutilisables sur
n'importe quelle page. Les libellés textuels restent ceux déjà
définis dans utils/formatters.py — ce module ajoute uniquement la
couleur et la présentation.
"""

import streamlit as st

from models.enums import NiveauAlerte, StatutDocument, StatutPeriode
from utils.formatters import libelle_statut_periode

# Couples (texte, fond) : contraste supérieur à 6:1 pour chacun (lisibilité
# renforcée, vérifiée par tests/test_interface_professionnelle.py). La
# couleur n'est jamais le seul porteur d'information : chaque badge
# affiche aussi son libellé en toutes lettres et une bordure.
_COULEURS_STATUT_PERIODE = {
    StatutPeriode.BROUILLON: ("#4B5563", "#F3F4F6"),
    StatutPeriode.OUVERTE: ("#1F3A6E", "#E8EEF7"),
    StatutPeriode.VALIDEE: ("#92400E", "#FEF3C7"),
    StatutPeriode.CLOTUREE: ("#166534", "#DCFCE7"),
}

_COULEURS_NIVEAU_ALERTE = {
    NiveauAlerte.INFO: ("#1F3A6E", "#E8EEF7"),
    NiveauAlerte.AVERTISSEMENT: ("#92400E", "#FEF3C7"),
    NiveauAlerte.ERREUR: ("#9A3412", "#FFEDD5"),
    NiveauAlerte.CRITIQUE: ("#991B1B", "#FEE2E2"),
}

_COULEURS_STATUT_DOCUMENT = {
    StatutDocument.VALIDE: ("#166534", "#DCFCE7"),
    StatutDocument.MANQUANT: ("#991B1B", "#FEE2E2"),
    StatutDocument.MODIFIE: ("#92400E", "#FEF3C7"),
    StatutDocument.ORPHELIN: ("#4B5563", "#F3F4F6"),
}


def _badge_html(texte: str, couleur_texte: str, couleur_fond: str) -> str:
    return (
        f'<span style="display:inline-block; padding:0.15rem 0.5rem; border-radius:3px; '
        f"border:1px solid {couleur_texte}; font-size:0.85rem; font-weight:600; "
        f'color:{couleur_texte}; background-color:{couleur_fond};">'
        f"{texte}</span>"
    )


def badge_statut_periode(statut: StatutPeriode) -> str:
    couleur_texte, couleur_fond = _COULEURS_STATUT_PERIODE[statut]
    return _badge_html(libelle_statut_periode(statut), couleur_texte, couleur_fond)


def badge_niveau_alerte(niveau: NiveauAlerte, texte: str = None) -> str:
    couleur_texte, couleur_fond = _COULEURS_NIVEAU_ALERTE[niveau]
    return _badge_html(texte or niveau.value.upper(), couleur_texte, couleur_fond)


def badge_statut_document(statut: StatutDocument, texte: str) -> str:
    couleur_texte, couleur_fond = _COULEURS_STATUT_DOCUMENT[statut]
    return _badge_html(texte, couleur_texte, couleur_fond)


def afficher_badge_statut_periode(statut: StatutPeriode) -> None:
    st.markdown(badge_statut_periode(statut), unsafe_allow_html=True)


def config_colonnes_montants(noms_colonnes) -> dict:
    """
    Retourne la configuration `column_config` alignant à droite les
    colonnes monétaires d'un `st.dataframe` (amélioration de
    lisibilité) — sans jamais modifier le format d'affichage déjà
    produit par `utils.formatters.formater_fcfa` (toujours des
    chaînes de texte, jamais des valeurs numériques recalculées ici).

    Exemple :
        st.dataframe(lignes, column_config=config_colonnes_montants(["Net", "Taxe"]))
    """
    return {nom: st.column_config.TextColumn(nom, alignment="right") for nom in noms_colonnes}


def afficher_document(cle: str, avec_sommaire: bool = True) -> str:
    """
    Affiche un document de la documentation intégrée (dossier docs/) :
    titre de page, sommaire des sections, texte complet, puis bouton de
    téléchargement du texte source. Le document entier reste visible
    sur la page (aucun contenu masqué derrière un onglet), ce qui le
    rend lisible par une aide technique ou un outil automatisé.
    Retourne le texte affiché.
    """
    from utils.documentation import DOCUMENTS, DocumentationIntrouvableError, lire_document, separer_titre, sommaire

    try:
        texte = lire_document(cle)
    except DocumentationIntrouvableError as erreur:
        st.error(str(erreur))
        st.stop()

    titre, corps = separer_titre(texte)
    st.title(titre or cle)
    sections = sommaire(corps)
    if avec_sommaire and sections:
        with st.container(border=True):
            st.markdown("**Sommaire**")
            st.markdown("\n".join(f"- {section}" for section in sections))
    st.markdown(corps)
    st.divider()
    st.download_button(
        "Télécharger ce document (texte au format Markdown)",
        data=texte.encode("utf-8"),
        file_name=DOCUMENTS[cle],
        mime="text/markdown",
    )
    return texte
