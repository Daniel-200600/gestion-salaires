"""
Service d'archivage documentaire (module 14).

Produit une archive ZIP cohérente des documents d'une période
CLOTURÉE (bulletins + états de paie déjà générés), accompagnée d'un
manifest.json décrivant son contenu. Ne modifie JAMAIS la base de
données ni les données de paie — l'archivage est une opération de
lecture des documents déjà existants et d'écriture d'un fichier ZIP.

Sécurité : `extraire_archive_securise` protège explicitement contre le
path traversal (membres ZIP contenant `../`, chemins absolus, etc.) —
aucun fichier n'est jamais extrait en dehors du dossier de destination
prévu, quel que soit le contenu du ZIP.
"""

import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from database.repositories import document_repository
from models.enums import StatutPeriode, TypeDocument
from services import periode_service
from services.document_service import calculer_hash_fichier

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.archive_service")

NOM_MANIFEST = "manifest.json"


class ArchiveServiceError(Exception):
    """Erreur d'archivage ou de vérification — message toujours compréhensible."""


@dataclass
class RapportArchivage:
    chemin_archive: Path
    nombre_documents: int
    documents_manquants: List[str] = field(default_factory=list)


def archiver_periode(
    periode_id: int,
    etablissement: str = "Établissement scolaire",
    utilisateur: Optional[str] = None,
    dossier_destination: Optional[Path] = None,
    db_path: DbPath = None,
) -> RapportArchivage:
    """
    Archive tous les documents enregistrés d'une période CLOTURÉE
    (section 21). Refuse toute période dont le statut n'est pas
    CLOTUREE — l'archivage est réservé aux périodes définitivement
    figées (module 12), jamais à une période encore OUVERTE ou
    seulement VALIDEE.

    Signale (sans bloquer l'archivage) les documents référencés en
    base mais introuvables sur disque : ils sont listés dans le
    rapport plutôt que silencieusement absents de l'archive.
    """
    periode = periode_service.obtenir_periode(periode_id, db_path=db_path)
    if periode.statut != StatutPeriode.CLOTUREE:
        raise ArchiveServiceError(
            f"Seule une période CLOTUREE peut être archivée (statut actuel : '{periode.statut.value}')."
        )

    documents = document_repository.lister_par_periode(periode_id, db_path=db_path)
    dossier = dossier_destination if dossier_destination is not None else Path.cwd()
    dossier.mkdir(parents=True, exist_ok=True)

    nom_archive = f"Archive_Paie_{periode.libelle.replace(' ', '_')}.zip"
    chemin_archive = dossier / nom_archive
    compteur = 1
    while chemin_archive.exists():
        chemin_archive = dossier / f"Archive_Paie_{periode.libelle.replace(' ', '_')}_{compteur}.zip"
        compteur += 1

    documents_manquants: List[str] = []
    entrees_manifest = []

    with zipfile.ZipFile(chemin_archive, "w", zipfile.ZIP_DEFLATED) as archive:
        for document in documents:
            chemin_source = Path(document.chemin)
            if not chemin_source.exists():
                documents_manquants.append(document.nom_fichier)
                continue

            sous_dossier = {
                TypeDocument.BULLETIN: "Bulletins",
                TypeDocument.ETAT_PAIE: "Etats",
                TypeDocument.EXPORT_EXCEL: "Rapports",
                TypeDocument.RAPPORT_PAIE: "Rapports",
            }.get(document.type_document, "Documents")
            nom_dans_zip = f"{sous_dossier}/{document.nom_fichier}"
            archive.write(chemin_source, arcname=nom_dans_zip)

            entrees_manifest.append({
                "nom_fichier": document.nom_fichier,
                "type": document.type_document.value,
                "chemin_archive": nom_dans_zip,
                "taille": document.taille,
                "hash_sha256": document.hash_fichier,
                "utilisateur_generation": document.utilisateur,
                "date_generation": document.date_creation,
            })

        manifest = {
            "etablissement": etablissement,
            "periode": periode.libelle,
            "statut_periode": periode.statut.value,
            "date_archivage": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "utilisateur": utilisateur,
            "nombre_documents": len(entrees_manifest),
            "documents_manquants": documents_manquants,
            "documents": entrees_manifest,
        }
        archive.writestr(NOM_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

    logger.info("Archive créée : %s (%d document(s))", chemin_archive.name, len(entrees_manifest))
    return RapportArchivage(
        chemin_archive=chemin_archive, nombre_documents=len(entrees_manifest), documents_manquants=documents_manquants
    )


@dataclass
class ResultatVerificationArchive:
    valide: bool
    message: str
    manifest: Optional[dict] = None
    fichiers_avec_hash_invalide: List[str] = field(default_factory=list)


def verifier_archive(chemin_archive: Path) -> ResultatVerificationArchive:
    """
    Vérifie qu'une archive est lisible, que son manifest est présent
    et valide, que les fichiers annoncés sont bien présents, et que
    leur hash correspond lorsqu'il est disponible (section 25). Ne
    lève jamais d'exception : toute anomalie est reflétée dans le
    résultat.
    """
    if not chemin_archive.exists():
        return ResultatVerificationArchive(False, "Le fichier d'archive n'existe pas.")

    try:
        with zipfile.ZipFile(chemin_archive, "r") as archive:
            if archive.testzip() is not None:
                return ResultatVerificationArchive(False, "L'archive ZIP est corrompue.")

            if NOM_MANIFEST not in archive.namelist():
                return ResultatVerificationArchive(False, "Manifest absent de l'archive.")

            try:
                manifest = json.loads(archive.read(NOM_MANIFEST).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return ResultatVerificationArchive(False, "Manifest illisible (JSON invalide).")

            fichiers_avec_hash_invalide = []
            for entree in manifest.get("documents", []):
                chemin_dans_zip = entree.get("chemin_archive")
                if chemin_dans_zip not in archive.namelist():
                    return ResultatVerificationArchive(
                        False, f"Fichier annoncé absent de l'archive : {chemin_dans_zip}", manifest=manifest
                    )
                hash_attendu = entree.get("hash_sha256")
                if hash_attendu:
                    import hashlib
                    hash_reel = hashlib.sha256(archive.read(chemin_dans_zip)).hexdigest()
                    if hash_reel != hash_attendu:
                        fichiers_avec_hash_invalide.append(entree.get("nom_fichier", chemin_dans_zip))

            if fichiers_avec_hash_invalide:
                return ResultatVerificationArchive(
                    False, f"{len(fichiers_avec_hash_invalide)} fichier(s) avec un hash invalide.",
                    manifest=manifest, fichiers_avec_hash_invalide=fichiers_avec_hash_invalide,
                )

            return ResultatVerificationArchive(True, "Archive valide.", manifest=manifest)
    except zipfile.BadZipFile:
        return ResultatVerificationArchive(False, "Le fichier n'est pas une archive ZIP valide.")


def extraire_archive_securise(chemin_archive: Path, dossier_destination: Path) -> List[Path]:
    """
    Extrait une archive vers `dossier_destination`, en protégeant
    explicitement contre le path traversal (section 26/27) : tout
    membre dont le chemin résolu sortirait de `dossier_destination`
    (`../`, chemin absolu, lien symbolique détourné) est ignoré et
    journalisé, jamais extrait.
    """
    dossier_destination = dossier_destination.resolve()
    dossier_destination.mkdir(parents=True, exist_ok=True)
    fichiers_extraits: List[Path] = []

    with zipfile.ZipFile(chemin_archive, "r") as archive:
        for membre in archive.namelist():
            chemin_cible = (dossier_destination / membre).resolve()
            try:
                chemin_cible.relative_to(dossier_destination)
            except ValueError:
                logger.warning("Membre d'archive rejeté (path traversal détecté) : %s", membre)
                continue

            if membre.endswith("/"):
                chemin_cible.mkdir(parents=True, exist_ok=True)
                continue

            chemin_cible.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(membre) as source, open(chemin_cible, "wb") as destination:
                destination.write(source.read())
            fichiers_extraits.append(chemin_cible)

    return fichiers_extraits
