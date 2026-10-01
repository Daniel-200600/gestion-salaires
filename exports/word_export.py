"""
Génération du fichier Word individuel (module 07).

Charge templates/bulletin_template.docx (créé UNE SEULE FOIS par
templates/build_template.py) et y injecte des valeurs déjà préparées
par services/bulletin_service.py (lui-même dérivé de
services/paie_service.py). Ce module ne contient et ne doit JAMAIS
contenir de formule de paie (gain heures, taxe 5 %, net à percevoir) :
il se limite au remplacement de texte et à l'enregistrement du
document — pure présentation d'une donnée déjà calculée.

Ce module ne dépend pas de Streamlit.
"""

from pathlib import Path
from typing import Dict, Optional

from docx import Document

from config.paths import resource_root
from config.settings import DATA_DIR
from exports.excel_export import chemin_sortie_disponible
from utils.formatters import nettoyer_nom_fichier

TEMPLATE_PATH = resource_root() / "templates" / "bulletin_template.docx"
EXPORT_DIR_BULLETINS = DATA_DIR / "exports" / "bulletins"


class WordExportError(Exception):
    """Levée pour toute impossibilité de générer un bulletin Word (template introuvable, etc.)."""


def _remplacer_dans_paragraphe(paragraphe, valeurs: Dict[str, str]) -> None:
    """
    Remplace tous les placeholders {{...}} présents dans un paragraphe.

    Le template est généré par templates/build_template.py, qui place
    chaque placeholder dans un run isolé : dans le cas normal, un
    simple remplacement run par run suffit. Par robustesse (au cas où
    un placeholder serait scindé entre plusieurs runs), le texte
    complet du paragraphe est reconstruit si un remplacement s'avère
    nécessaire, puis réinjecté dans le premier run.
    """
    texte_complet = "".join(run.text for run in paragraphe.runs)
    if "{{" not in texte_complet:
        return

    # Remplacement direct run par run (cas normal, template auto-généré)
    remplacement_effectue_par_run = True
    for run in paragraphe.runs:
        if "{{" in run.text:
            texte_original = run.text
            for cle, valeur in valeurs.items():
                run.text = run.text.replace(cle, str(valeur))
            if "{{" in run.text and run.text == texte_original:
                remplacement_effectue_par_run = False

    if remplacement_effectue_par_run:
        return

    # Filet de sécurité : placeholder scindé entre plusieurs runs
    for cle, valeur in valeurs.items():
        texte_complet = texte_complet.replace(cle, str(valeur))
    if paragraphe.runs:
        paragraphe.runs[0].text = texte_complet
        for run in paragraphe.runs[1:]:
            run.text = ""


def _remplacer_dans_document(document: Document, valeurs: Dict[str, str]) -> None:
    """Applique le remplacement de placeholders à tous les paragraphes du corps et de tous les tableaux."""
    for paragraphe in document.paragraphs:
        _remplacer_dans_paragraphe(paragraphe, valeurs)

    for table in document.tables:
        for ligne in table.rows:
            for cellule in ligne.cells:
                for paragraphe in cellule.paragraphs:
                    _remplacer_dans_paragraphe(paragraphe, valeurs)


def verifier_aucun_placeholder_restant(document: Document) -> None:
    """
    Vérifie qu'aucun {{...}} ne subsiste dans le document (corps +
    tableaux). Lève WordExportError si un placeholder a été oublié —
    un bulletin ne doit jamais être livré avec un champ non rempli.
    """
    textes = [p.text for p in document.paragraphs]
    for table in document.tables:
        for ligne in table.rows:
            for cellule in ligne.cells:
                textes.extend(p.text for p in cellule.paragraphs)

    for texte in textes:
        if "{{" in texte and "}}" in texte:
            raise WordExportError(f"Placeholder non remplacé détecté dans le bulletin : {texte!r}")


def generer_document_bulletin(valeurs: Dict[str, str], template_path: Optional[Path] = None) -> Document:
    """
    Charge le template officiel et retourne un objet Document avec
    tous les placeholders remplacés par `valeurs`. Ne sauvegarde rien
    sur disque (cf. `sauvegarder_document`).
    """
    chemin_template = template_path if template_path is not None else TEMPLATE_PATH
    if not chemin_template.exists():
        raise WordExportError(
            f"Le template officiel est introuvable : {chemin_template}. "
            "Il doit être généré une fois via templates/build_template.py."
        )

    document = Document(chemin_template)
    _remplacer_dans_document(document, valeurs)
    verifier_aucun_placeholder_restant(document)
    return document


def generer_nom_fichier_bulletin(nom: str, prenom: str, libelle_periode: str) -> str:
    """
    Construit le nom de fichier dynamique et sûr sous Windows d'un
    bulletin individuel, ex : Bulletin_KAMGANG_JEAN_PAUL_AOUT_2026.docx
    """
    nom_nettoye = nettoyer_nom_fichier(nom.upper())
    prenom_nettoye = nettoyer_nom_fichier(prenom.upper())
    periode_nettoyee = nettoyer_nom_fichier(libelle_periode.upper())
    return f"Bulletin_{nom_nettoye}_{prenom_nettoye}_{periode_nettoyee}.docx"


def sauvegarder_document(document: Document, chemin: Path) -> Path:
    """Enregistre le document Word au chemin donné (le dossier parent est créé si besoin)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    document.save(chemin)
    return chemin
