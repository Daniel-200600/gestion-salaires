"""
Service de diagnostic système (module 10).

Rassemble un état de santé global de l'application : accessibilité et
intégrité de la base, présence des tables attendues (dérivées du
schéma SQL réel, jamais d'une liste arbitraire codée en dur), taille
des données, dénombrements non sensibles (nombre d'enseignants,
périodes, bulletins, entrées d'audit), présence du template Word et
des dossiers essentiels, et nombre de sauvegardes disponibles.

Aucune donnée personnelle n'est exposée par ce module : uniquement des
compteurs et des états (présent/absent, valide/invalide).
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from config.settings import BACKUP_DIR, DATA_DIR, DB_PATH, SCHEMA_PATH
from database.initialization import get_table_names
from database.repositories import (
    audit_log_repository,
    document_repository,
    enseignant_repository,
    periode_repository,
    utilisateur_repository,
)
from exports.excel_export import EXPORT_DIR
from exports.word_export import EXPORT_DIR_BULLETINS, TEMPLATE_PATH
from services import backup_service


class EtatSysteme(str, Enum):
    VERT = "vert"
    ORANGE = "orange"
    ROUGE = "rouge"


@dataclass
class VerificationTable:
    nom: str
    presente: bool


@dataclass
class DiagnosticSysteme:
    """Résultat complet du diagnostic, prêt à afficher côté interface."""

    base_accessible: bool
    integrite: "backup_service.ResultatIntegrite"
    taille_base_octets: int
    tables: List[VerificationTable] = field(default_factory=list)

    nombre_enseignants: int = 0
    nombre_periodes: int = 0
    nombre_bulletins: int = 0
    nombre_lignes_audit: int = 0

    nombre_utilisateurs: int = 0
    nombre_utilisateurs_actifs: int = 0
    nombre_admins_actifs: int = 0

    nombre_documents: int = 0
    documents_manquants: int = 0
    taille_documents_octets: int = 0

    taille_exports_octets: int = 0
    nombre_sauvegardes: int = 0

    template_bulletin_present: bool = False
    dossiers_essentiels_ok: bool = True
    dossiers_manquants: List[str] = field(default_factory=list)

    @property
    def toutes_tables_presentes(self) -> bool:
        return all(t.presente for t in self.tables)

    @property
    def etat_global(self) -> EtatSysteme:
        """
        Calcule l'état global à partir des diagnostics réels
        (section 21) :
        - ROUGE : base inaccessible, intégrité échouée, ou fichier/table
          critique manquant (template, table essentielle).
        - ORANGE : tout le reste est correct mais un élément non
          bloquant manque (ex : aucune sauvegarde disponible).
        - VERT : tout est en ordre.
        """
        if not self.base_accessible or not self.integrite.valide or not self.toutes_tables_presentes:
            return EtatSysteme.ROUGE
        if not self.template_bulletin_present or not self.dossiers_essentiels_ok:
            return EtatSysteme.ROUGE
        if self.nombre_utilisateurs > 0 and self.nombre_admins_actifs == 0:
            # Ne peut normalement jamais se produire (protégé par
            # services/utilisateur_service.py), mais un système sans
            # aucun administrateur actif serait inadministrable :
            # signalé comme critique si cela survenait malgré tout.
            return EtatSysteme.ROUGE
        if self.nombre_sauvegardes == 0:
            return EtatSysteme.ORANGE
        return EtatSysteme.VERT


def _taille_dossier(dossier: Path) -> int:
    """Taille totale d'un dossier (récursive). Retourne 0 si le dossier n'existe pas."""
    if not dossier.exists():
        return 0
    return sum(chemin.stat().st_size for chemin in dossier.rglob("*") if chemin.is_file())


def _tables_attendues_depuis_schema(schema_path: Path = SCHEMA_PATH) -> List[str]:
    """
    Extrait les noms de tables directement du schéma SQL de référence
    (source de vérité unique) plutôt que de maintenir une liste
    arbitraire dupliquée ici.
    """
    if not schema_path.exists():
        return []
    contenu = schema_path.read_text(encoding="utf-8")
    return re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", contenu)


def diagnostiquer_systeme(db_path: Optional[Path] = None) -> DiagnosticSysteme:
    """
    Exécute le diagnostic complet du système. Ne lève jamais
    d'exception : toute défaillance (base inaccessible, dossier
    manquant) est reflétée dans le résultat, jamais propagée.
    """
    cible = Path(db_path) if db_path is not None else DB_PATH

    integrite = backup_service.verifier_integrite(cible)
    base_accessible = integrite.valide
    taille_base = cible.stat().st_size if cible.exists() else 0

    tables_attendues = _tables_attendues_depuis_schema()
    if base_accessible:
        tables_presentes = set(get_table_names(cible))
    else:
        tables_presentes = set()
    tables = [VerificationTable(nom=nom, presente=nom in tables_presentes) for nom in tables_attendues]

    nombre_enseignants = 0
    nombre_periodes = 0
    nombre_lignes_audit = 0
    nombre_utilisateurs = 0
    nombre_utilisateurs_actifs = 0
    nombre_admins_actifs = 0
    nombre_documents = 0
    documents_manquants = 0
    taille_documents = 0
    if base_accessible:
        try:
            nombre_enseignants = len(enseignant_repository.lister(inclure_inactifs=True, db_path=cible))
            nombre_periodes = len(periode_repository.lister(db_path=cible))
            nombre_lignes_audit = audit_log_repository.compter_tout(db_path=cible)
            nombre_utilisateurs = utilisateur_repository.compter_tout(db_path=cible)
            nombre_utilisateurs_actifs = utilisateur_repository.compter_actifs(db_path=cible)
            nombre_admins_actifs = utilisateur_repository.compter_admins_actifs(db_path=cible)

            # Vérification LÉGÈRE uniquement (présence du fichier, aucun
            # hash recalculé) : la vérification complète est réservée à
            # l'action dédiée « Vérifier l'intégrité maintenant » (section 38).
            documents = document_repository.rechercher(db_path=cible)
            nombre_documents = len(documents)
            documents_manquants = sum(1 for d in documents if not Path(d.chemin).exists())
            taille_documents = document_repository.taille_totale(db_path=cible)
        except Exception:
            # Une table manquante ou une base partiellement corrompue ne
            # doit jamais faire planter le diagnostic lui-même.
            pass

    # Bulletins : fichiers .docx réellement générés (le système du
    # module 07 produit des fichiers, pas des lignes en base).
    nombre_bulletins = len(list(EXPORT_DIR_BULLETINS.rglob("*.docx"))) if EXPORT_DIR_BULLETINS.exists() else 0

    taille_exports = _taille_dossier(EXPORT_DIR)
    nombre_sauvegardes = len(backup_service.lister_sauvegardes(backup_dir=BACKUP_DIR))

    dossiers_essentiels = {"data": DATA_DIR, "exports": EXPORT_DIR, "sauvegardes": BACKUP_DIR}
    dossiers_manquants = [nom for nom, chemin in dossiers_essentiels.items() if not chemin.exists()]

    return DiagnosticSysteme(
        base_accessible=base_accessible,
        integrite=integrite,
        taille_base_octets=taille_base,
        tables=tables,
        nombre_enseignants=nombre_enseignants,
        nombre_periodes=nombre_periodes,
        nombre_bulletins=nombre_bulletins,
        nombre_lignes_audit=nombre_lignes_audit,
        nombre_utilisateurs=nombre_utilisateurs,
        nombre_utilisateurs_actifs=nombre_utilisateurs_actifs,
        nombre_admins_actifs=nombre_admins_actifs,
        nombre_documents=nombre_documents,
        documents_manquants=documents_manquants,
        taille_documents_octets=taille_documents,
        taille_exports_octets=taille_exports,
        nombre_sauvegardes=nombre_sauvegardes,
        template_bulletin_present=TEMPLATE_PATH.exists(),
        dossiers_essentiels_ok=len(dossiers_manquants) == 0,
        dossiers_manquants=dossiers_manquants,
    )


def formater_taille(taille_octets: int) -> str:
    """Formate une taille en octets vers l'unité la plus lisible (o/Ko/Mo/Go)."""
    taille = float(taille_octets)
    for unite in ("o", "Ko", "Mo", "Go"):
        if taille < 1024:
            return f"{taille:.1f} {unite}"
        taille /= 1024
    return f"{taille:.1f} To"
