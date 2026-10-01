"""
Service documentaire (module 14).

Enregistre les documents générés par l'application (bulletins, exports
Excel, états de paie) dans le registre `documents`, et fournit la
recherche filtrée (période, enseignant, type, terme de recherche).

Ce service NE GÉNÈRE AUCUN DOCUMENT lui-même : il vient toujours APRÈS
qu'un fichier a été produit par les modules existants
(services/bulletin_service.py, exports/excel_export.py,
exports/reporting_export.py). L'enregistrement dans le registre est
volontairement best-effort (jamais bloquant pour la génération elle-même) :
une erreur d'écriture dans le registre ne doit jamais faire échouer une
génération de bulletin ou d'export déjà fonctionnelle.
"""

import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Union

from database.repositories import document_repository
from models.document import Document
from models.enums import TypeDocument

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.document_service")

_TAILLE_BLOC_HASH = 65536  # lecture par blocs de 64 Ko : jamais tout le fichier en mémoire d'un coup


def calculer_hash_fichier(chemin: Path) -> Optional[str]:
    """
    Calcule le hash SHA-256 du contenu réel d'un fichier (section 13).
    Retourne None si le fichier est introuvable ou illisible — ne lève
    jamais d'exception (un document manquant est un état normal à
    détecter, pas une erreur technique).
    """
    if not chemin.exists() or not chemin.is_file():
        return None
    try:
        hacheur = hashlib.sha256()
        with open(chemin, "rb") as fichier:
            for bloc in iter(lambda: fichier.read(_TAILLE_BLOC_HASH), b""):
                hacheur.update(bloc)
        return hacheur.hexdigest()
    except OSError:
        return None


def enregistrer_document(
    type_document: TypeDocument,
    chemin: Path,
    periode_id: Optional[int] = None,
    enseignant_id: Optional[int] = None,
    utilisateur: Optional[str] = None,
    db_path: DbPath = None,
) -> Optional[Document]:
    """
    Enregistre un document déjà généré dans le registre : calcule sa
    taille et son hash à partir du fichier réel sur disque. Best-effort :
    toute erreur est journalisée et retourne None plutôt que de
    propager une exception — un problème de registre ne doit jamais
    faire échouer la génération du document lui-même, déjà réussie à
    ce stade.
    """
    try:
        taille = chemin.stat().st_size if chemin.exists() else None
        hash_fichier = calculer_hash_fichier(chemin)

        document = Document(
            type_document=type_document,
            nom_fichier=chemin.name,
            chemin=str(chemin),
            enseignant_id=enseignant_id,
            periode_id=periode_id,
            utilisateur=utilisateur,
            taille=taille,
            hash_fichier=hash_fichier,
        )
        document.id = document_repository.enregistrer(document, db_path=db_path)
        logger.info("Document enregistré au registre : %s (%s)", chemin.name, type_document.value)
        return document
    except Exception as erreur:  # noqa: BLE001 — jamais bloquant pour la génération déjà réussie
        logger.warning("Échec de l'enregistrement au registre documentaire pour %s : %s", chemin, erreur)
        return None


def rechercher_documents(
    periode_id: Optional[int] = None,
    enseignant_id: Optional[int] = None,
    type_document: Optional[TypeDocument] = None,
    terme_recherche: Optional[str] = None,
    db_path: DbPath = None,
) -> List[Document]:
    """Recherche filtrée dans le registre (section 16/19/20) — lecture seule."""
    return document_repository.rechercher(
        periode_id=periode_id, enseignant_id=enseignant_id, type_document=type_document,
        terme_recherche=terme_recherche, db_path=db_path,
    )


def obtenir_document(document_id: int, db_path: DbPath = None) -> Optional[Document]:
    return document_repository.obtenir_par_id(document_id, db_path=db_path)
