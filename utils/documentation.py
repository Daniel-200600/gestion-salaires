"""
Accès à la documentation intégrée (guide utilisateur, guide
administrateur, politique de confidentialité, conditions d'utilisation).

Les textes sont des fichiers Markdown du dossier `docs/`, source unique
affichée à la fois dans l'application et lisible hors application.
Ce module ne dépend pas de Streamlit : il est testable directement.
"""

from typing import Dict, List

from config.settings import DOCS_DIR

DOCUMENTS: Dict[str, str] = {
    "guide_utilisateur": "guide_utilisateur.md",
    "guide_administrateur": "guide_administrateur.md",
    "politique_confidentialite": "politique_confidentialite.md",
    "conditions_utilisation": "conditions_utilisation.md",
    "a_propos": "a_propos.md",
}


class DocumentationIntrouvableError(FileNotFoundError):
    """Le fichier de documentation demandé est absent de l'installation."""


def lire_document(cle: str) -> str:
    """Retourne le texte Markdown d'un document intégré."""
    if cle not in DOCUMENTS:
        raise KeyError(f"Document inconnu : {cle}")
    chemin = DOCS_DIR / DOCUMENTS[cle]
    if not chemin.exists():
        raise DocumentationIntrouvableError(
            f"Le document « {DOCUMENTS[cle]} » est introuvable dans l'installation ({DOCS_DIR})."
        )
    return chemin.read_text(encoding="utf-8")


def sommaire(texte: str) -> List[str]:
    """Titres de niveau 2 (« ## ») d'un document, dans l'ordre : sert de table des matières."""
    return [ligne[3:].strip() for ligne in texte.splitlines() if ligne.startswith("## ")]


def separer_titre(texte: str):
    """Sépare le titre principal (« # ») du reste du document."""
    lignes = texte.splitlines()
    if lignes and lignes[0].startswith("# "):
        return lignes[0][2:].strip(), "\n".join(lignes[1:]).lstrip("\n")
    return "", texte
