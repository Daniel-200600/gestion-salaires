"""
Service de vérification d'intégrité documentaire (module 14).

Deux niveaux de vérification, volontairement séparés pour des raisons
de performance (section 38) :

- `etat_leger(document)` : vérifie uniquement la PRÉSENCE du fichier
  sur disque (`Path.exists()`), sans recalculer de hash. C'est cette
  fonction que le diagnostic courant (module 10) doit utiliser — un
  hash n'est jamais recalculé pour des centaines de documents à chaque
  ouverture de page.
- `verifier_integrite(document)` : vérification COMPLÈTE (présence +
  comparaison du hash SHA-256 stocké avec le hash réel du fichier).
  Coûteuse, réservée à une action explicite (« Vérifier l'intégrité
  maintenant »).

Détecte également les documents ORPHELINS : des fichiers présents sur
disque (dans les dossiers de génération déjà existants) sans aucune
ligne correspondante dans le registre `documents`.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from database.repositories import document_repository
from models.document import Document
from models.enums import StatutDocument
from services.document_service import calculer_hash_fichier

DbPath = Optional[Union[str, Path]]


def etat_leger(document: Document) -> StatutDocument:
    """Vérification rapide : présence du fichier uniquement (aucun hash recalculé)."""
    return StatutDocument.VALIDE if Path(document.chemin).exists() else StatutDocument.MANQUANT


def verifier_integrite(document: Document) -> StatutDocument:
    """
    Vérification complète (section 14) :
    - MANQUANT : le fichier référencé n'existe plus sur disque.
    - MODIFIE : le fichier existe mais son hash actuel diffère de celui
      enregistré lors de la génération (ou aucun hash n'a été
      enregistré à l'époque, auquel cas la comparaison est ignorée et
      le document reste VALIDE — ne jamais signaler une anomalie sur
      une donnée qui n'a simplement jamais été mesurée).
    - VALIDE : présent, hash identique (ou non mesuré à l'origine).
    """
    chemin = Path(document.chemin)
    if not chemin.exists():
        return StatutDocument.MANQUANT

    if document.hash_fichier is None:
        return StatutDocument.VALIDE

    hash_actuel = calculer_hash_fichier(chemin)
    if hash_actuel != document.hash_fichier:
        return StatutDocument.MODIFIE
    return StatutDocument.VALIDE


@dataclass
class RapportIntegriteDocumentaire:
    """Résultat d'une vérification complète, prêt à afficher (section 15/32)."""

    nombre_documents: int = 0
    nombre_valides: int = 0
    nombre_manquants: int = 0
    nombre_modifies: int = 0
    documents_manquants: List[Document] = field(default_factory=list)
    documents_modifies: List[Document] = field(default_factory=list)
    documents_orphelins: List[Path] = field(default_factory=list)
    taille_totale_octets: int = 0


def verifier_integrite_complete(
    dossiers_a_scanner: Optional[List[Path]] = None, db_path: DbPath = None
) -> RapportIntegriteDocumentaire:
    """
    Vérification complète (bouton dédié, section 38) : hash de chaque
    document enregistré + détection des orphelins dans les dossiers de
    génération fournis (fichiers présents sur disque sans ligne dans
    le registre).
    """
    documents = document_repository.rechercher(db_path=db_path)
    rapport = RapportIntegriteDocumentaire(nombre_documents=len(documents))

    chemins_enregistres = set()
    for document in documents:
        statut = verifier_integrite(document)
        chemins_enregistres.add(str(Path(document.chemin).resolve()))
        if statut == StatutDocument.MANQUANT:
            rapport.nombre_manquants += 1
            rapport.documents_manquants.append(document)
        elif statut == StatutDocument.MODIFIE:
            rapport.nombre_modifies += 1
            rapport.documents_modifies.append(document)
        else:
            rapport.nombre_valides += 1
            if document.taille:
                rapport.taille_totale_octets += document.taille

    if dossiers_a_scanner:
        for dossier in dossiers_a_scanner:
            if not dossier.exists():
                continue
            for chemin_fichier in dossier.rglob("*"):
                if chemin_fichier.is_file() and str(chemin_fichier.resolve()) not in chemins_enregistres:
                    rapport.documents_orphelins.append(chemin_fichier)

    return rapport
