"""
Moteur de détection d'alertes (module 16).

Ce module NE CONTIENT AUCUNE règle de contrôle, d'intégrité ou de
diagnostic propre : il appelle exclusivement les services déjà
existants (controle_paie_service, document_integrity_service,
diagnostic_service, backup_service, periode_service) et traduit leurs
résultats en alertes via services/alert_service.py. C'est une couche
d'ORCHESTRATION ET DE NOTIFICATION, jamais un deuxième moteur de
règles (section 47).

Indépendant de Streamlit.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Union

from models.enums import NiveauAlerte, StatutPeriode
from services import alert_service, periode_service

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.alert_detection_service")

SOURCE_ENSEIGNANTS = "enseignants"
SOURCE_PERIODES = "periodes"
SOURCE_CONTROLE_PAIE = "controle_paie"
SOURCE_DOCUMENTS = "documents"
SOURCE_ADMINISTRATION = "administration"
SOURCE_IMPORT = "import"

SEUIL_SAUVEGARDE_ANCIENNE_JOURS = 7


@dataclass
class RapportDetection:
    """Synthèse d'une exécution du moteur de détection (section 24)."""

    alertes_actives: List[str] = field(default_factory=list)
    nombre_creees_ou_maj: int = 0
    nombre_resolues_automatiquement: int = 0


# ---------------------------------------------------------------------
# A. Alertes enseignants (section 4A)
# ---------------------------------------------------------------------

def detecter_alertes_enseignants(db_path: DbPath = None) -> RapportDetection:
    """Enseignant actif sans taux horaire — lecture directe du champ, aucun recalcul."""
    from services import enseignant_service

    rapport = RapportDetection()
    for enseignant in enseignant_service.lister_enseignants(inclure_inactifs=False, db_path=db_path):
        if enseignant.taux_horaire == 0:
            alerte = alert_service.creer_ou_mettre_a_jour_alerte(
                type_alerte="TAUX_HORAIRE_NUL", niveau=NiveauAlerte.AVERTISSEMENT,
                titre=f"Taux horaire nul — {enseignant.nom} {enseignant.prenom}",
                message=(
                    f"L'enseignant {enseignant.nom} {enseignant.prenom} (actif) a un taux horaire de 0 FCFA. "
                    "Vérifiez sa fiche avant tout calcul de paie."
                ),
                source=SOURCE_ENSEIGNANTS, enseignant_id=enseignant.id, db_path=db_path,
            )
            rapport.alertes_actives.append(alerte.cle_deduplication)
            rapport.nombre_creees_ou_maj += 1

    rapport.nombre_resolues_automatiquement += alert_service.resoudre_alertes_obsoletes(
        SOURCE_ENSEIGNANTS, rapport.alertes_actives, db_path=db_path
    )
    return rapport


# ---------------------------------------------------------------------
# B. Alertes périodes (section 4B) — informatives, jamais une erreur pour un état normal
# ---------------------------------------------------------------------

def detecter_alertes_periodes(db_path: DbPath = None) -> RapportDetection:
    rapport = RapportDetection()
    for periode in periode_service.lister_periodes(db_path=db_path):
        if periode.statut == StatutPeriode.BROUILLON:
            alerte = alert_service.creer_ou_mettre_a_jour_alerte(
                type_alerte="PERIODE_BROUILLON", niveau=NiveauAlerte.INFO,
                titre=f"Période en brouillon — {periode.libelle}",
                message=f"La période {periode.libelle} est encore en BROUILLON et n'a pas été ouverte à la saisie.",
                source=SOURCE_PERIODES, periode_id=periode.id, db_path=db_path,
            )
            rapport.alertes_actives.append(alerte.cle_deduplication)
            rapport.nombre_creees_ou_maj += 1

    rapport.nombre_resolues_automatiquement += alert_service.resoudre_alertes_obsoletes(
        SOURCE_PERIODES, rapport.alertes_actives, db_path=db_path
    )
    return rapport


# ---------------------------------------------------------------------
# C. Alertes de contrôle de paie (section 5/6/27) — réutilise le module 09 tel quel
# ---------------------------------------------------------------------

def detecter_alertes_controle_paie(periode_id: int, db_path: DbPath = None) -> RapportDetection:
    """
    Traduit chaque Anomalie déjà produite par controle_paie_service en
    alerte — ne recalcule et ne réinterprète rien : le contrôle de
    paie reste l'unique source de vérité (section 27).
    """
    from services import controle_paie_service

    rapport = RapportDetection()
    try:
        resultat = controle_paie_service.controler_periode(periode_id, db_path=db_path)
    except Exception as erreur:  # noqa: BLE001 — jamais bloquant pour la détection
        logger.warning("Détection du contrôle de paie impossible pour la période %s : %s", periode_id, erreur)
        return rapport

    for anomalie in resultat.anomalies:
        niveau = NiveauAlerte.ERREUR if anomalie.niveau.value == "erreur" else NiveauAlerte.AVERTISSEMENT
        titre = f"{anomalie.code} — {anomalie.enseignant_nom or 'Période'}"
        message = anomalie.message
        if anomalie.recommandation:
            message += f" Recommandation : {anomalie.recommandation}"

        alerte = alert_service.creer_ou_mettre_a_jour_alerte(
            type_alerte=f"CONTROLE_{anomalie.code}", niveau=niveau, titre=titre, message=message,
            source=SOURCE_CONTROLE_PAIE, periode_id=periode_id, enseignant_id=anomalie.enseignant_id,
            db_path=db_path,
        )
        rapport.alertes_actives.append(alerte.cle_deduplication)
        rapport.nombre_creees_ou_maj += 1

    rapport.nombre_resolues_automatiquement += alert_service.resoudre_alertes_obsoletes(
        SOURCE_CONTROLE_PAIE, rapport.alertes_actives, db_path=db_path
    )
    return rapport


# ---------------------------------------------------------------------
# D. Alertes documentaires (section 7/30) — réutilise le module 14 tel quel
# ---------------------------------------------------------------------

def detecter_alertes_documents(
    dossiers_a_scanner: Optional[List[Path]] = None, db_path: DbPath = None
) -> RapportDetection:
    """
    Traduit le rapport d'intégrité documentaire (module 14) en
    alertes — ne recalcule jamais de hash indépendamment.
    """
    from services import document_integrity_service

    rapport = RapportDetection()
    rapport_integrite = document_integrity_service.verifier_integrite_complete(
        dossiers_a_scanner=dossiers_a_scanner, db_path=db_path
    )

    for document in rapport_integrite.documents_manquants:
        alerte = alert_service.creer_ou_mettre_a_jour_alerte(
            type_alerte="DOCUMENT_MANQUANT", niveau=NiveauAlerte.ERREUR,
            titre=f"Document manquant — {document.nom_fichier}",
            message=f"Le document « {document.nom_fichier} » est référencé mais introuvable sur le disque.",
            source=SOURCE_DOCUMENTS, periode_id=document.periode_id, enseignant_id=document.enseignant_id,
            document_id=document.id, db_path=db_path,
        )
        rapport.alertes_actives.append(alerte.cle_deduplication)
        rapport.nombre_creees_ou_maj += 1

    for document in rapport_integrite.documents_modifies:
        alerte = alert_service.creer_ou_mettre_a_jour_alerte(
            type_alerte="DOCUMENT_MODIFIE", niveau=NiveauAlerte.AVERTISSEMENT,
            titre=f"Document modifié après génération — {document.nom_fichier}",
            message=f"Le contenu de « {document.nom_fichier} » a changé depuis sa génération (hash différent).",
            source=SOURCE_DOCUMENTS, periode_id=document.periode_id, enseignant_id=document.enseignant_id,
            document_id=document.id, db_path=db_path,
        )
        rapport.alertes_actives.append(alerte.cle_deduplication)
        rapport.nombre_creees_ou_maj += 1

    for chemin_orphelin in rapport_integrite.documents_orphelins:
        alerte = alert_service.creer_ou_mettre_a_jour_alerte(
            type_alerte="DOCUMENT_ORPHELIN", niveau=NiveauAlerte.INFO,
            titre=f"Document orphelin — {chemin_orphelin.name}",
            message=f"Le fichier « {chemin_orphelin.name} » est présent sur le disque sans référence au registre.",
            source=SOURCE_DOCUMENTS, db_path=db_path,
        )
        rapport.alertes_actives.append(alerte.cle_deduplication)
        rapport.nombre_creees_ou_maj += 1

    rapport.nombre_resolues_automatiquement += alert_service.resoudre_alertes_obsoletes(
        SOURCE_DOCUMENTS, rapport.alertes_actives, db_path=db_path
    )
    return rapport


# ---------------------------------------------------------------------
# E. Alertes administratives (section 9) — réutilise le module 10 tel quel
# ---------------------------------------------------------------------

def detecter_alertes_administratives(db_path: DbPath = None) -> RapportDetection:
    from services import backup_service, diagnostic_service
    from services.diagnostic_service import EtatSysteme

    rapport = RapportDetection()
    diagnostic = diagnostic_service.diagnostiquer_systeme(db_path=db_path)

    if diagnostic.etat_global == EtatSysteme.ROUGE:
        alerte = alert_service.creer_ou_mettre_a_jour_alerte(
            type_alerte="SYSTEME_ETAT_ROUGE", niveau=NiveauAlerte.CRITIQUE,
            titre="État système critique",
            message=(
                "Le diagnostic système signale un état ROUGE (base inaccessible, intégrité échouée, "
                "ou fichier critique manquant). Consultez Administration → Diagnostic."
            ),
            source=SOURCE_ADMINISTRATION, db_path=db_path,
        )
        rapport.alertes_actives.append(alerte.cle_deduplication)
        rapport.nombre_creees_ou_maj += 1

    sauvegardes = backup_service.lister_sauvegardes()
    if not sauvegardes:
        alerte = alert_service.creer_ou_mettre_a_jour_alerte(
            type_alerte="AUCUNE_SAUVEGARDE", niveau=NiveauAlerte.AVERTISSEMENT,
            titre="Aucune sauvegarde disponible",
            message="Aucune sauvegarde n'a encore été créée. Rendez-vous dans Administration → Sauvegarde.",
            source=SOURCE_ADMINISTRATION, db_path=db_path,
        )
        rapport.alertes_actives.append(alerte.cle_deduplication)
        rapport.nombre_creees_ou_maj += 1
    else:
        derniere = sauvegardes[0]
        age = datetime.now() - derniere.date_creation
        if age > timedelta(days=SEUIL_SAUVEGARDE_ANCIENNE_JOURS):
            alerte = alert_service.creer_ou_mettre_a_jour_alerte(
                type_alerte="SAUVEGARDE_ANCIENNE", niveau=NiveauAlerte.AVERTISSEMENT,
                titre="Dernière sauvegarde ancienne",
                message=(
                    f"La dernière sauvegarde date du {derniere.date_creation.strftime('%d/%m/%Y')} "
                    f"(plus de {SEUIL_SAUVEGARDE_ANCIENNE_JOURS} jours)."
                ),
                source=SOURCE_ADMINISTRATION, db_path=db_path,
            )
            rapport.alertes_actives.append(alerte.cle_deduplication)
            rapport.nombre_creees_ou_maj += 1

    rapport.nombre_resolues_automatiquement += alert_service.resoudre_alertes_obsoletes(
        SOURCE_ADMINISTRATION, rapport.alertes_actives, db_path=db_path
    )
    return rapport


# ---------------------------------------------------------------------
# F. Alerte d'import (section 8/31) — une alerte de synthèse, jamais une par ligne
# ---------------------------------------------------------------------

def detecter_alerte_import(journal, db_path: DbPath = None):
    """
    Crée une alerte de synthèse après un import (module 15), UNIQUEMENT
    si l'import présente quelque chose de notable (échec, erreurs ou
    rejets) — jamais une alerte pour un import pleinement réussi, afin
    de ne jamais transformer chaque opération normale en notification
    (section 32).
    """
    if journal.statut.value == "echec":
        niveau, titre = NiveauAlerte.ERREUR, f"Échec d'import — {journal.nom_fichier}"
    elif journal.nb_erreurs > 0 or journal.nb_rejetees > 0:
        niveau, titre = NiveauAlerte.AVERTISSEMENT, f"Import avec anomalies — {journal.nom_fichier}"
    else:
        return None

    message = (
        f"{journal.nb_lignes} ligne(s) analysée(s), {journal.nb_creations} création(s), "
        f"{journal.nb_mises_a_jour} mise(s) à jour, {journal.nb_rejetees} rejet(s), {journal.nb_erreurs} erreur(s)."
    )
    return alert_service.creer_ou_mettre_a_jour_alerte(
        type_alerte="IMPORT_ANOMALIE", niveau=niveau, titre=titre, message=message,
        source=SOURCE_IMPORT, periode_id=journal.periode_id, import_id=journal.id,
        utilisateur_concerne=journal.utilisateur, db_path=db_path,
    )


# ---------------------------------------------------------------------
# Orchestration complète (section 24)
# ---------------------------------------------------------------------

def executer_toutes_detections(periode_id: Optional[int] = None, db_path: DbPath = None) -> dict:
    """
    Lance l'ensemble des détections (section 24) : enseignants,
    périodes, administration, documents, et — si une période est
    fournie — son contrôle de paie. Retourne un résumé par catégorie.
    """
    resultats = {
        "enseignants": detecter_alertes_enseignants(db_path=db_path),
        "periodes": detecter_alertes_periodes(db_path=db_path),
        "administration": detecter_alertes_administratives(db_path=db_path),
        "documents": detecter_alertes_documents(db_path=db_path),
    }
    if periode_id is not None:
        resultats["controle_paie"] = detecter_alertes_controle_paie(periode_id, db_path=db_path)
    return resultats
