"""
Service central des alertes (module 16).

Indépendant de Streamlit. Ne détecte AUCUNE anomalie lui-même — cela
reste la responsabilité de services/alert_detection_service.py, qui
appelle ce module pour créer/mettre à jour les alertes qui en
résultent. Ce module gère exclusivement le CYCLE DE VIE d'une alerte
déjà détectée : création avec déduplication, transitions de statut,
recherche, compteurs.

Transitions de statut autorisées (section 12) :

    NOUVELLE -> LUE -> ACQUITTEE -> RESOLUE
    (NOUVELLE | LUE | ACQUITTEE) -> IGNOREE
    toute alerte active -> RESOLUE (résolution automatique, section 14)

Aucune autre transition n'est autorisée (ex. RESOLUE -> LUE est
impossible : une alerte résolue redevient une nouvelle alerte si
l'anomalie réapparaît, jamais une réouverture directe).

Marquer une alerte comme LUE est une interaction de lecture à faible
enjeu : elle n'est volontairement pas auditée (même politique que la
simple consultation d'une page ailleurs dans l'application) — seules
les actions ACQUITTEE/RESOLUE/IGNOREE, qui engagent une décision,
sont journalisées.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from database.repositories import alerte_repository
from models.alerte import Alerte
from models.audit_log import AuditLog
from models.enums import NiveauAlerte, StatutAlerte, TypeActionAudit

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.alert_service")

_TRANSITIONS_AUTORISEES = {
    StatutAlerte.NOUVELLE: {StatutAlerte.LUE, StatutAlerte.ACQUITTEE, StatutAlerte.IGNOREE, StatutAlerte.RESOLUE},
    StatutAlerte.LUE: {StatutAlerte.ACQUITTEE, StatutAlerte.IGNOREE, StatutAlerte.RESOLUE},
    StatutAlerte.ACQUITTEE: {StatutAlerte.RESOLUE, StatutAlerte.IGNOREE},
    StatutAlerte.RESOLUE: set(),
    StatutAlerte.IGNOREE: set(),
}

_AUDIT_PAR_STATUT = {
    StatutAlerte.ACQUITTEE: TypeActionAudit.ALERTE_ACQUITTEE,
    StatutAlerte.RESOLUE: TypeActionAudit.ALERTE_RESOLUE,
    StatutAlerte.IGNOREE: TypeActionAudit.ALERTE_IGNOREE,
}


class AlertServiceError(Exception):
    """Erreur de transition ou de recherche d'alerte — message toujours compréhensible."""


def construire_cle_deduplication(
    type_alerte: str,
    periode_id: Optional[int] = None,
    enseignant_id: Optional[int] = None,
    document_id: Optional[int] = None,
    import_id: Optional[int] = None,
) -> str:
    """
    Clé logique unique identifiant « la même anomalie » (section 13) :
    type + objet(s) concerné(s). Deux détections successives de la
    même anomalie sur le même objet produisent toujours la même clé.
    """
    return "|".join([
        type_alerte,
        f"periode:{periode_id}" if periode_id is not None else "periode:-",
        f"enseignant:{enseignant_id}" if enseignant_id is not None else "enseignant:-",
        f"document:{document_id}" if document_id is not None else "document:-",
        f"import:{import_id}" if import_id is not None else "import:-",
    ])


def creer_ou_mettre_a_jour_alerte(
    type_alerte: str,
    niveau: NiveauAlerte,
    titre: str,
    message: str,
    source: str,
    periode_id: Optional[int] = None,
    enseignant_id: Optional[int] = None,
    document_id: Optional[int] = None,
    import_id: Optional[int] = None,
    utilisateur_concerne: Optional[str] = None,
    db_path: DbPath = None,
) -> Alerte:
    """
    Point d'entrée unique pour signaler une anomalie détectée
    (section 10/13). Si une alerte ACTIVE (ni résolue ni ignorée)
    porte déjà la même clé de déduplication, met simplement à jour sa
    date de dernière détection et son message — ne crée jamais de
    doublon. Sinon, crée une nouvelle alerte au statut NOUVELLE.

    La contrainte d'unicité partielle du schéma
    (`idx_alertes_dedup_active`) constitue un filet de sécurité
    supplémentaire au niveau base, en plus de cette vérification
    applicative.
    """
    cle = construire_cle_deduplication(type_alerte, periode_id, enseignant_id, document_id, import_id)
    existante = alerte_repository.obtenir_par_cle_active(cle, db_path=db_path)

    if existante is not None:
        alerte_repository.mettre_a_jour_detection(existante.id, titre, message, db_path=db_path)
        return alerte_repository.obtenir_par_id(existante.id, db_path=db_path)

    alerte = Alerte(
        type_alerte=type_alerte, niveau=niveau, titre=titre, message=message, source=source,
        cle_deduplication=cle, periode_id=periode_id, enseignant_id=enseignant_id,
        document_id=document_id, import_id=import_id, utilisateur_concerne=utilisateur_concerne,
    )
    alerte.id = alerte_repository.creer(alerte, db_path=db_path)
    _journaliser_audit(alerte, TypeActionAudit.ALERTE_CREEE, "Créée", db_path=db_path)
    return alerte_repository.obtenir_par_id(alerte.id, db_path=db_path)


def resoudre_alertes_obsoletes(source: str, cles_encore_actives: List[str], db_path: DbPath = None) -> int:
    """
    Résolution automatique (section 14) : pour une source donnée,
    toute alerte encore active dont la clé n'apparaît PLUS parmi les
    anomalies détectées lors de la dernière analyse est marquée
    RESOLUE — l'anomalie a disparu. L'historique est conservé
    (jamais de suppression), la résolution reste tracée.
    Retourne le nombre d'alertes résolues automatiquement.
    """
    compteur = 0
    for alerte in alerte_repository.lister_actives_par_source(source, db_path=db_path):
        if alerte.cle_deduplication not in cles_encore_actives:
            alerte_repository.changer_statut(alerte.id, StatutAlerte.RESOLUE, utilisateur=None, db_path=db_path)
            compteur += 1
    return compteur


def _changer_statut_avec_validation(
    alerte_id: int, nouveau_statut: StatutAlerte, utilisateur: Optional[str], db_path: DbPath
) -> Alerte:
    alerte = alerte_repository.obtenir_par_id(alerte_id, db_path=db_path)
    if alerte is None:
        raise AlertServiceError(f"Aucune alerte avec l'id {alerte_id}.")

    if nouveau_statut not in _TRANSITIONS_AUTORISEES.get(alerte.statut, set()):
        raise AlertServiceError(
            f"Transition invalide : « {alerte.statut.value} » -> « {nouveau_statut.value} »."
        )

    alerte_repository.changer_statut(alerte_id, nouveau_statut, utilisateur=utilisateur, db_path=db_path)
    alerte_mise_a_jour = alerte_repository.obtenir_par_id(alerte_id, db_path=db_path)

    type_audit = _AUDIT_PAR_STATUT.get(nouveau_statut)
    if type_audit is not None:
        _journaliser_audit(
            alerte_mise_a_jour, type_audit, f"{alerte.statut.value} -> {nouveau_statut.value}",
            utilisateur=utilisateur, db_path=db_path,
        )
    return alerte_mise_a_jour


def marquer_lue(alerte_id: int, utilisateur: Optional[str] = None, db_path: DbPath = None) -> Alerte:
    return _changer_statut_avec_validation(alerte_id, StatutAlerte.LUE, utilisateur, db_path)


def acquitter(alerte_id: int, utilisateur: Optional[str] = None, db_path: DbPath = None) -> Alerte:
    return _changer_statut_avec_validation(alerte_id, StatutAlerte.ACQUITTEE, utilisateur, db_path)


def resoudre(alerte_id: int, utilisateur: Optional[str] = None, db_path: DbPath = None) -> Alerte:
    return _changer_statut_avec_validation(alerte_id, StatutAlerte.RESOLUE, utilisateur, db_path)


def ignorer(alerte_id: int, utilisateur: Optional[str] = None, db_path: DbPath = None) -> Alerte:
    return _changer_statut_avec_validation(alerte_id, StatutAlerte.IGNOREE, utilisateur, db_path)


def lister_alertes(
    niveau: Optional[NiveauAlerte] = None,
    statut: Optional[StatutAlerte] = None,
    type_alerte: Optional[str] = None,
    periode_id: Optional[int] = None,
    enseignant_id: Optional[int] = None,
    source: Optional[str] = None,
    terme: Optional[str] = None,
    db_path: DbPath = None,
) -> List[Alerte]:
    return alerte_repository.rechercher(
        niveau=niveau, statut=statut, type_alerte=type_alerte, periode_id=periode_id,
        enseignant_id=enseignant_id, source=source, terme=terme, db_path=db_path,
    )


def compter_alertes_actives(db_path: DbPath = None) -> Dict[str, int]:
    """Synthèse par niveau (section 16/26), alertes actives uniquement (ni résolues ni ignorées)."""
    return alerte_repository.compter_par_niveau(
        statut_exclu=[StatutAlerte.RESOLUE, StatutAlerte.IGNOREE], db_path=db_path
    )


def _journaliser_audit(
    alerte: Alerte, type_action: TypeActionAudit, resultat: str, utilisateur: Optional[str] = None, db_path: DbPath = None
) -> None:
    try:
        from database.repositories import audit_log_repository
        audit_log_repository.enregistrer(
            AuditLog(
                type_action=type_action, entite="alerte", entite_id=alerte.id,
                utilisateur=utilisateur or alerte.utilisateur_concerne,
                details=f"{alerte.type_alerte} — {alerte.titre} — {resultat}",
            ),
            db_path=db_path,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Impossible de journaliser l'action d'alerte dans l'audit : %s", erreur)
