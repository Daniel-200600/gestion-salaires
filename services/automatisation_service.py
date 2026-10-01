"""
Service central d'automatisation et génération massive (module 18).

Ce module N'EST QU'UNE COUCHE D'ORCHESTRATION : il n'implémente
AUCUNE formule de paie, AUCUNE logique de contrôle, de reporting,
d'import, d'archivage ou d'alerte propre. Il appelle exclusivement :

    services/controle_paie_service.py   -> préconditions, anomalies
    services/bulletin_service.py        -> génération de bulletin (déjà transactionnelle par ligne)
    services/document_service.py        -> registre documentaire (idempotence)
    services/document_integrity_service.py -> vérification d'intégrité
    services/archive_service.py         -> archive ZIP + manifest
    services/alert_service.py           -> notification en cas d'anomalie massive

Indépendant de Streamlit. Aucune nouvelle table SQL : le suivi d'une
opération est un objet en mémoire (retourné à l'appelant) et sa trace
durable passe par l'audit déjà existant (module 11) plus, pour les
opérations produisant des fichiers, un manifest.json (même convention
que services/archive_service.py, module 14) — pas de deuxième système
de persistance parallèle.
"""

import json
import logging
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from models.audit_log import AuditLog
from models.enums import (
    StatutOperationAutomatisation,
    TypeActionAudit,
    TypeDocument,
    TypeOperationAutomatisation,
)

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.automatisation_service")


class AutomatisationError(Exception):
    """Erreur de préparation ou d'exécution — message toujours compréhensible."""


# ---------------------------------------------------------------------
# Structures de suivi (section 15)
# ---------------------------------------------------------------------

@dataclass
class ResultatLigne:
    """Résultat individuel d'un traitement pour un enseignant (section 9)."""

    enseignant_id: int
    nom: str
    prenom: str
    statut: str  # "succes" | "ignore" | "erreur"
    etape: str
    message: str = ""


@dataclass
class OperationAutomatisation:
    """Suivi complet d'une opération massive (section 15/24)."""

    id: str
    type_operation: TypeOperationAutomatisation
    periode_id: int
    utilisateur: Optional[str] = None
    date_debut: Optional[str] = None
    date_fin: Optional[str] = None
    statut: StatutOperationAutomatisation = StatutOperationAutomatisation.PREPAREE
    lignes: List[ResultatLigne] = field(default_factory=list)
    fichiers_produits: List[Path] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.lignes)

    @property
    def succes(self) -> int:
        return sum(1 for l in self.lignes if l.statut == "succes")

    @property
    def erreurs(self) -> int:
        return sum(1 for l in self.lignes if l.statut == "erreur")

    @property
    def ignores(self) -> int:
        return sum(1 for l in self.lignes if l.statut == "ignore")

    @property
    def lignes_en_erreur(self) -> List[ResultatLigne]:
        return [l for l in self.lignes if l.statut == "erreur"]


def _nouvel_id_operation() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------
# Préconditions (section 6)
# ---------------------------------------------------------------------

@dataclass
class RapportPrecondition:
    ok: bool
    problemes_bloquants: List[str] = field(default_factory=list)
    avertissements: List[str] = field(default_factory=list)


def verifier_preconditions(periode_id: int, db_path: DbPath = None) -> RapportPrecondition:
    """
    Vérifie qu'une génération massive est possible pour cette période
    (section 6) — réutilise intégralement controle_paie_service (aucune
    règle de contrôle dupliquée) et vérifie la présence du template
    Word (déjà utilisé par bulletin_service, jamais recalculé ici).
    """
    from exports.word_export import TEMPLATE_PATH
    from services import controle_paie_service, periode_service

    problemes: List[str] = []
    avertissements: List[str] = []

    try:
        periode_service.obtenir_periode(periode_id, db_path=db_path)
    except Exception:
        return RapportPrecondition(ok=False, problemes_bloquants=[f"Aucune période avec l'id {periode_id}."])

    if not TEMPLATE_PATH.exists():
        problemes.append("Le modèle de bulletin (template Word) est introuvable.")

    try:
        rapport_controle = controle_paie_service.controler_periode(periode_id, db_path=db_path)
        if rapport_controle.est_bloque:
            problemes.append(
                f"{len(rapport_controle.erreurs)} erreur(s) bloquante(s) détectée(s) par le contrôle de paie."
            )
        if rapport_controle.avertissements:
            avertissements.append(f"{len(rapport_controle.avertissements)} avertissement(s) du contrôle de paie.")
    except Exception as erreur:  # noqa: BLE001
        avertissements.append(f"Contrôle de paie non exécutable pour l'instant : {erreur}")

    return RapportPrecondition(ok=(len(problemes) == 0), problemes_bloquants=problemes, avertissements=avertissements)


# ---------------------------------------------------------------------
# Dry run / analyse (section 18)
# ---------------------------------------------------------------------

@dataclass
class LigneAnalyseBulletin:
    enseignant_id: int
    nom: str
    prenom: str
    etat: str  # "pret" | "deja_existant" | "erreur_potentielle"
    detail: str = ""


@dataclass
class RapportAnalyseBulletins:
    nombre_enseignants: int
    lignes: List[LigneAnalyseBulletin] = field(default_factory=list)

    @property
    def nombre_prets(self) -> int:
        return sum(1 for l in self.lignes if l.etat == "pret")

    @property
    def nombre_deja_existants(self) -> int:
        return sum(1 for l in self.lignes if l.etat == "deja_existant")

    @property
    def nombre_erreurs_potentielles(self) -> int:
        return sum(1 for l in self.lignes if l.etat == "erreur_potentielle")


def analyser_generation_bulletins(
    periode_id: int, enseignant_ids: Optional[List[int]] = None, db_path: DbPath = None
) -> RapportAnalyseBulletins:
    """
    Dry run (section 18) : n'écrit RIEN. Détermine, pour chaque
    enseignant concerné, si son bulletin est prêt à générer, déjà
    existant (registre documentaire, module 14), ou probablement en
    erreur (paie non calculable). Chargement groupé (une seule requête
    pour tous les documents de la période) — jamais une requête par
    enseignant (section 30).
    """
    from database.repositories import document_repository
    from services import enseignant_service
    from services.paie_service import CalculPaieError, calculer_paie_enseignant

    enseignants = enseignant_service.lister_enseignants(inclure_inactifs=False, db_path=db_path)
    if enseignant_ids is not None:
        enseignants = [e for e in enseignants if e.id in enseignant_ids]

    documents_existants = document_repository.rechercher(
        periode_id=periode_id, type_document=TypeDocument.BULLETIN, db_path=db_path
    )
    ids_avec_bulletin = {d.enseignant_id for d in documents_existants}

    lignes = []
    for e in enseignants:
        if e.id in ids_avec_bulletin:
            lignes.append(LigneAnalyseBulletin(e.id, e.nom, e.prenom, "deja_existant", "Un bulletin est déjà enregistré pour cette période."))
            continue
        try:
            calculer_paie_enseignant(periode_id, e.id, db_path=db_path)
            lignes.append(LigneAnalyseBulletin(e.id, e.nom, e.prenom, "pret"))
        except CalculPaieError as erreur:
            lignes.append(LigneAnalyseBulletin(e.id, e.nom, e.prenom, "erreur_potentielle", str(erreur)))

    return RapportAnalyseBulletins(nombre_enseignants=len(enseignants), lignes=lignes)


# ---------------------------------------------------------------------
# Génération massive des bulletins (section 8/9/10)
# ---------------------------------------------------------------------

def generer_bulletins_massif(
    periode_id: int,
    enseignant_ids: Optional[List[int]] = None,
    forcer_regeneration: bool = False,
    utilisateur: Optional[str] = None,
    db_path: DbPath = None,
) -> OperationAutomatisation:
    """
    Génération massive avec idempotence (section 10) : un enseignant
    ayant déjà un bulletin enregistré pour cette période est IGNORÉ
    par défaut (jamais de doublon créé aveuglément) — sauf si
    `forcer_regeneration=True`, auquel cas
    bulletin_service.generer_bulletin_enseignant reprend son
    comportement habituel (versionnement automatique, ou refus pur et
    simple si la période est CLOTUREE — règle du module 07/12,
    jamais contournée ici).

    Chaque enseignant est traité indépendamment (section 9) : une
    erreur sur l'un n'interrompt jamais le traitement des autres.
    """
    from database.repositories import document_repository
    from services import bulletin_service, enseignant_service

    operation = OperationAutomatisation(
        id=_nouvel_id_operation(), type_operation=TypeOperationAutomatisation.BULLETINS_MASSIFS,
        periode_id=periode_id, utilisateur=utilisateur, date_debut=datetime.now().isoformat(),
        statut=StatutOperationAutomatisation.EN_COURS,
    )
    _journaliser_audit(TypeActionAudit.AUTOMATISATION_PREPAREE, operation, db_path=db_path)

    enseignants = enseignant_service.lister_enseignants(inclure_inactifs=False, db_path=db_path)
    if enseignant_ids is not None:
        enseignants = [e for e in enseignants if e.id in enseignant_ids]

    documents_existants = document_repository.rechercher(
        periode_id=periode_id, type_document=TypeDocument.BULLETIN, db_path=db_path
    )
    ids_avec_bulletin = {d.enseignant_id for d in documents_existants}

    for e in enseignants:
        if e.id in ids_avec_bulletin and not forcer_regeneration:
            operation.lignes.append(ResultatLigne(e.id, e.nom, e.prenom, "ignore", "generation", "Document déjà existant — ignoré (idempotence)."))
            continue
        try:
            resultat = bulletin_service.generer_bulletin_enseignant(periode_id, e.id, db_path=db_path, utilisateur=utilisateur)
            operation.fichiers_produits.append(resultat.chemin)
            operation.lignes.append(ResultatLigne(e.id, e.nom, e.prenom, "succes", "generation", resultat.chemin.name))
        except Exception as erreur:  # noqa: BLE001 — une erreur individuelle ne bloque jamais le lot
            logger.warning("Échec de génération pour l'enseignant id=%s : %s", e.id, erreur)
            operation.lignes.append(ResultatLigne(e.id, e.nom, e.prenom, "erreur", "generation", str(erreur)))

    operation.date_fin = datetime.now().isoformat()
    operation.statut = (
        StatutOperationAutomatisation.TERMINEE_AVEC_ERREURS if operation.erreurs > 0
        else StatutOperationAutomatisation.TERMINEE
    )

    _journaliser_audit(TypeActionAudit.GENERATION_MASSIVE_BULLETINS, operation, db_path=db_path)
    _alerter_si_necessaire(operation, db_path=db_path)
    return operation


def reprendre_erreurs(
    operation_precedente: OperationAutomatisation, utilisateur: Optional[str] = None, db_path: DbPath = None
) -> OperationAutomatisation:
    """
    Reprise ciblée (section 25) : ne retraite QUE les enseignants en
    erreur lors de l'opération précédente — jamais les succès déjà
    obtenus. Réutilise generer_bulletins_massif avec
    `forcer_regeneration=True` (le but explicite d'une reprise est de
    produire enfin le document manquant).
    """
    ids_en_erreur = [l.enseignant_id for l in operation_precedente.lignes_en_erreur]
    if not ids_en_erreur:
        raise AutomatisationError("Aucune erreur à reprendre dans cette opération.")

    return generer_bulletins_massif(
        operation_precedente.periode_id, enseignant_ids=ids_en_erreur, forcer_regeneration=True,
        utilisateur=utilisateur, db_path=db_path,
    )


# ---------------------------------------------------------------------
# Vérification d'intégrité (section 23) — réutilise le module 14 tel quel
# ---------------------------------------------------------------------

def verifier_integrite_periode(periode_id: int, dossiers_a_scanner: Optional[List[Path]] = None, db_path: DbPath = None):
    """Délègue entièrement à document_integrity_service (module 14) — aucun recalcul de hash ici."""
    from services import document_integrity_service
    return document_integrity_service.verifier_integrite_complete(dossiers_a_scanner=dossiers_a_scanner, db_path=db_path)


# ---------------------------------------------------------------------
# Archive massive (section 29) — réutilise archive_service tel quel
# ---------------------------------------------------------------------

def archiver_periode_massif(
    periode_id: int, etablissement: str = "Établissement scolaire", utilisateur: Optional[str] = None,
    dossier_destination: Optional[Path] = None, db_path: DbPath = None,
):
    """
    Délègue entièrement à services/archive_service.archiver_periode
    (module 14) : mêmes garanties (période CLOTUREE exigée, manifest,
    protection path traversal) — pas de second service d'archivage.
    """
    from services import archive_service

    rapport = archive_service.archiver_periode(
        periode_id, etablissement=etablissement, utilisateur=utilisateur,
        dossier_destination=dossier_destination, db_path=db_path,
    )
    _journaliser_audit_simple(
        TypeActionAudit.ARCHIVE_MASSIVE, periode_id, utilisateur,
        f"{rapport.chemin_archive.name} — {rapport.nombre_documents} document(s)", db_path=db_path,
    )
    return rapport


# ---------------------------------------------------------------------
# Pack de paie (section 13/14)
# ---------------------------------------------------------------------

def creer_pack_paie(
    periode_id: int, etablissement: str = "Établissement scolaire", utilisateur: Optional[str] = None,
    dossier_destination: Optional[Path] = None, db_path: DbPath = None,
) -> Path:
    """
    Assemble un dossier ZIP complet (section 13) à partir des
    documents DÉJÀ enregistrés au registre (module 14) — ne génère
    rien de nouveau, ne recalcule rien : rassemble ce qui existe déjà.
    Contient un manifest.json (section 14), jamais de mot de passe ni
    donnée d'authentification.
    """
    from database.repositories import document_repository
    from services import periode_service

    periode = periode_service.obtenir_periode(periode_id, db_path=db_path)
    documents = document_repository.rechercher(periode_id=periode_id, db_path=db_path)

    dossier = dossier_destination if dossier_destination is not None else Path.cwd()
    dossier.mkdir(parents=True, exist_ok=True)
    nom_zip = f"PAIE_{periode.libelle.replace(' ', '_')}.zip"
    chemin_zip = dossier / nom_zip
    compteur = 1
    while chemin_zip.exists():
        chemin_zip = dossier / f"PAIE_{periode.libelle.replace(' ', '_')}_{compteur}.zip"
        compteur += 1

    sous_dossiers = {
        TypeDocument.BULLETIN: "Bulletins", TypeDocument.ETAT_PAIE: "Rapports",
        TypeDocument.EXPORT_EXCEL: "Exports", TypeDocument.RAPPORT_PAIE: "Rapports",
    }
    entrees_manifest = []
    documents_manquants = []

    with zipfile.ZipFile(chemin_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for document in documents:
            chemin_source = Path(document.chemin)
            if not chemin_source.exists():
                documents_manquants.append(document.nom_fichier)
                continue
            sous_dossier = sous_dossiers.get(document.type_document, "Documents")
            nom_dans_zip = f"{sous_dossier}/{document.nom_fichier}"
            archive.write(chemin_source, arcname=nom_dans_zip)
            entrees_manifest.append({
                "nom_fichier": document.nom_fichier, "type": document.type_document.value,
                "chemin_archive": nom_dans_zip, "taille": document.taille, "hash_sha256": document.hash_fichier,
            })

        manifest = {
            "etablissement": etablissement, "periode": periode.libelle, "statut_periode": periode.statut.value,
            "date_generation": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "utilisateur": utilisateur,
            "nombre_documents": len(entrees_manifest), "documents_manquants": documents_manquants,
            "documents": entrees_manifest,
        }
        archive.writestr("Manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        readme = (
            f"Pack de paie — {periode.libelle}\n"
            f"Généré le {manifest['date_generation']}\n\n"
            "Bulletins/  : bulletins individuels\n"
            "Exports/    : exports Excel\n"
            "Rapports/   : états et rapports de paie\n"
        )
        archive.writestr("README.txt", readme)

    _journaliser_audit_simple(
        TypeActionAudit.EXPORT_MASSIF, periode_id, utilisateur, f"Pack de paie {chemin_zip.name}", db_path=db_path
    )
    return chemin_zip


# ---------------------------------------------------------------------
# Audit et alertes (sections 21/22 — réutilisent les systèmes existants)
# ---------------------------------------------------------------------

def _journaliser_audit(type_action: TypeActionAudit, operation: OperationAutomatisation, db_path: DbPath = None) -> None:
    _journaliser_audit_simple(
        type_action, operation.periode_id, operation.utilisateur,
        f"{operation.type_operation.value} [{operation.id}] — {operation.succes} succès, "
        f"{operation.erreurs} erreur(s), {operation.ignores} ignoré(s)",
        db_path=db_path,
    )


def _journaliser_audit_simple(
    type_action: TypeActionAudit, periode_id: int, utilisateur: Optional[str], details: str, db_path: DbPath = None
) -> None:
    try:
        from database.repositories import audit_log_repository
        audit_log_repository.enregistrer(
            AuditLog(
                type_action=type_action, entite="periode_paie", entite_id=periode_id,
                utilisateur=utilisateur, details=details,
            ),
            db_path=db_path,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Impossible de journaliser l'automatisation dans l'audit : %s", erreur)


def _alerter_si_necessaire(operation: OperationAutomatisation, db_path: DbPath = None) -> None:
    """
    Notifie via le système d'alertes existant (module 16) en cas
    d'échecs massifs — ne crée jamais de nouveau moteur d'alertes.
    """
    if operation.erreurs == 0:
        return
    try:
        from services import alert_service
        from models.enums import NiveauAlerte
        niveau = NiveauAlerte.ERREUR if operation.erreurs >= operation.total else NiveauAlerte.AVERTISSEMENT
        alert_service.creer_ou_mettre_a_jour_alerte(
            type_alerte="AUTOMATISATION_ERREURS", niveau=niveau,
            titre=f"Génération massive avec erreurs — {operation.type_operation.value}",
            message=f"{operation.erreurs} erreur(s) sur {operation.total} traitement(s) lors de l'opération {operation.id}.",
            source="automatisation", periode_id=operation.periode_id, utilisateur_concerne=operation.utilisateur,
            db_path=db_path,
        )
    except Exception as erreur:  # noqa: BLE001 — une alerte non créée ne doit jamais faire échouer l'opération
        logger.warning("Impossible de créer l'alerte d'automatisation : %s", erreur)
