"""
Service de contrôle de la paie (module 09).

Vérifie la cohérence et la complétude des données de paie d'une
période AVANT sa validation, sans jamais recalculer les formules de
salaire : tous les résultats contrôlés proviennent de
services/paie_service.py (via calculer_paie_groupe), exactement comme
services/dashboard_service.py et services/comptabilite_service.py.
Réutilise en particulier dashboard_service.controler_coherence_resultats
pour les contrôles arithmétiques déjà écrits et testés (aucune
duplication) plutôt que de les réécrire ici.

Produit une liste structurée d'ANOMALIES (niveau, code, enseignant,
message, valeur, recommandation), distinguant :
- ERREUR         : empêche la validation de la période.
- AVERTISSEMENT  : n'empêche pas la validation, mais mérite l'attention
  du responsable.

Ce module fournit également le WORKFLOW COMPLET de validation et de
clôture d'une période « avec contrôle » (contrôle -> confirmation ->
transaction -> audit), en réutilisant intégralement les repositories
déjà validés de database/repositories/periode_repository.py — aucune
règle de transition n'est dupliquée ici.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from database.connection import get_connection
from database.repositories import audit_log_repository, periode_repository
from models.audit_log import AuditLog
from models.enums import Sexe, StatutEnseignant, StatutPeriode, TypeActionAudit
from models.periode_paie import PeriodePaie
from models.resultat_paie import ResultatPaie
from services import dashboard_service, heures_service, remuneration_service, retenue_service
from services.paie_service import CalculPaieError, calculer_paie_groupe
from services.periode_service import PeriodeValidationError, obtenir_periode

DbPath = Optional[Union[str, Path]]

# Seuils d'avertissement : réglages métier simples (pas des formules de
# paie) permettant de signaler une situation inhabituelle au responsable.
SEUIL_HEURES_ELEVEES = 300.0
SEUIL_DETTE_ELEVEE = 100_000
SEUIL_RETENUE_ELEVEE = 50_000


class ControlePaieError(PeriodeValidationError):
    """
    Levée pour toute impossibilité de valider/clôturer une période via
    le workflow contrôlé : erreurs bloquantes détectées, confirmation
    manquante, statut incompatible. Hérite de PeriodeValidationError
    pour rester attrapable par du code existant qui capture déjà ce type.
    """


class NiveauAnomalie(str, Enum):
    ERREUR = "erreur"
    AVERTISSEMENT = "avertissement"


@dataclass
class Anomalie:
    """Une anomalie détectée par le contrôle, prête à être affichée/filtrée côté interface."""

    niveau: NiveauAnomalie
    code: str
    enseignant_id: Optional[int]
    enseignant_nom: Optional[str]
    message: str
    valeur: Optional[str] = None
    recommandation: Optional[str] = None


@dataclass
class RapportControle:
    """Résultat complet du contrôle d'une période."""

    periode_id: int
    nombre_enseignants: int
    anomalies: List[Anomalie] = field(default_factory=list)

    @property
    def erreurs(self) -> List[Anomalie]:
        return [a for a in self.anomalies if a.niveau == NiveauAnomalie.ERREUR]

    @property
    def avertissements(self) -> List[Anomalie]:
        return [a for a in self.anomalies if a.niveau == NiveauAnomalie.AVERTISSEMENT]

    @property
    def nombre_conformes(self) -> int:
        """Enseignants ne figurant dans aucune anomalie (ni erreur, ni avertissement)."""
        ids_avec_anomalie = {a.enseignant_id for a in self.anomalies if a.enseignant_id is not None}
        return max(self.nombre_enseignants - len(ids_avec_anomalie), 0)

    @property
    def est_bloque(self) -> bool:
        """Vrai si au moins une erreur bloquante empêche la validation."""
        return len(self.erreurs) > 0


def _enseignants_avec_donnees(periode_id: int, db_path: DbPath) -> List[int]:
    """Même logique que comptabilite_service : tous les enseignants ayant au moins une saisie."""
    heures = heures_service.lister_heures_periode(periode_id, db_path=db_path)
    remuneration = remuneration_service.lister_remuneration_periode(periode_id, db_path=db_path)
    retenues = retenue_service.lister_retenues_periode(periode_id, db_path=db_path)
    return sorted(set(heures) | set(remuneration) | set(retenues))


def _nom_complet(resultat: ResultatPaie) -> str:
    return f"{resultat.nom} {resultat.prenom}".strip()


def _controler_identite(resultat: ResultatPaie) -> List[Anomalie]:
    nom = _nom_complet(resultat)
    anomalies: List[Anomalie] = []
    if not resultat.nom or not resultat.nom.strip():
        anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "NOM_MANQUANT", resultat.enseignant_id, nom,
                                   "Le nom de l'enseignant est manquant."))
    if not resultat.prenom or not resultat.prenom.strip():
        anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "PRENOM_MANQUANT", resultat.enseignant_id, nom,
                                   "Le prénom de l'enseignant est manquant."))
    if resultat.sexe not in (Sexe.HOMME, Sexe.FEMME):
        anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "SEXE_INVALIDE", resultat.enseignant_id, nom,
                                   "Le sexe de l'enseignant n'est pas valide."))
    if resultat.statut not in (StatutEnseignant.VACATAIRE, StatutEnseignant.PERMANENT):
        anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "STATUT_INVALIDE", resultat.enseignant_id, nom,
                                   "Le statut de l'enseignant n'est pas valide."))
    return anomalies


def _controler_heures(resultat: ResultatPaie) -> List[Anomalie]:
    nom = _nom_complet(resultat)
    anomalies: List[Anomalie] = []
    semaines = [resultat.semaine_1, resultat.semaine_2, resultat.semaine_3, resultat.semaine_4, resultat.semaine_5]

    for numero, valeur in enumerate(semaines, start=1):
        # Défensif : la saisie (heures_service) interdit déjà toute valeur
        # négative en amont ; ce contrôle ne peut donc normalement jamais
        # se déclencher, mais protège contre une donnée corrompue par un
        # autre moyen (import direct, migration, etc.).
        if valeur < 0:
            anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "HEURE_NEGATIVE", resultat.enseignant_id, nom,
                                       f"Semaine {numero} : heures négatives détectées.", valeur=str(valeur)))

    total_recompose = sum(semaines)
    if abs(total_recompose - resultat.total_heures) > 1e-6:
        anomalies.append(Anomalie(
            NiveauAnomalie.ERREUR, "TOTAL_HEURES_INCOHERENT", resultat.enseignant_id, nom,
            "Le total des heures ne correspond pas à la somme des 5 semaines.",
            valeur=f"total={resultat.total_heures:g} / somme semaines={total_recompose:g}",
        ))

    if resultat.total_heures > SEUIL_HEURES_ELEVEES:
        anomalies.append(Anomalie(
            NiveauAnomalie.AVERTISSEMENT, "VOLUME_HEURES_ELEVE", resultat.enseignant_id, nom,
            "Volume d'heures inhabituellement élevé sur la période.",
            valeur=f"{resultat.total_heures:g} h",
            recommandation="Vérifiez la saisie des heures pour cet enseignant.",
        ))
    return anomalies


def _controler_taux_et_montants(resultat: ResultatPaie) -> List[Anomalie]:
    nom = _nom_complet(resultat)
    anomalies: List[Anomalie] = []

    if resultat.taux_horaire <= 0 and resultat.salaire_fixe is None:  # salaire fixe : pas de taux
        anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "TAUX_INVALIDE", resultat.enseignant_id, nom,
                                   "Le taux horaire est nul ou négatif.", valeur=str(resultat.taux_horaire)))

    montants_a_verifier = (
        ("prime_ap_pp", resultat.prime_ap_pp),
        ("surveillance_secretariat", resultat.surveillance_secretariat),
        ("indemnite_suggestion_admin", resultat.indemnite_suggestion_admin),
        ("retenue_amicale", resultat.retenue_amicale),
        ("dette", resultat.dette),
    )
    for champ, valeur in montants_a_verifier:
        # Défensif également : déjà garanti >= 0 par la saisie (utils.validators).
        if valeur < 0:
            anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "MONTANT_NEGATIF", resultat.enseignant_id, nom,
                                       f"Le montant « {champ} » est négatif.", valeur=str(valeur)))

    if (
        resultat.prime_ap_pp == 0
        and resultat.surveillance_secretariat == 0
        and resultat.indemnite_suggestion_admin == 0
        and resultat.retenue_amicale == 0
        and resultat.dette == 0
    ):
        anomalies.append(Anomalie(
            NiveauAnomalie.AVERTISSEMENT, "AUCUN_ELEMENT_VARIABLE", resultat.enseignant_id, nom,
            "Aucune prime, indemnité ou retenue saisie pour cet enseignant (heures seules).",
            recommandation="Vérifiez que la saisie de paie est complète pour cet enseignant.",
        ))

    if resultat.dette >= SEUIL_DETTE_ELEVEE:
        anomalies.append(Anomalie(
            NiveauAnomalie.AVERTISSEMENT, "DETTE_ELEVEE", resultat.enseignant_id, nom,
            "Dette particulièrement élevée sur cette période.", valeur=str(resultat.dette),
            recommandation="Vérifiez le montant de la dette avec l'enseignant avant validation.",
        ))
    if resultat.retenue_amicale >= SEUIL_RETENUE_ELEVEE:
        anomalies.append(Anomalie(
            NiveauAnomalie.AVERTISSEMENT, "RETENUE_ELEVEE", resultat.enseignant_id, nom,
            "Retenue amicale particulièrement élevée sur cette période.", valeur=str(resultat.retenue_amicale),
        ))
    return anomalies


def _controler_resultat(resultat: ResultatPaie) -> List[Anomalie]:
    """Applique tous les contrôles individuels à UN résultat déjà calculé par paie_service."""
    return (
        _controler_identite(resultat)
        + _controler_heures(resultat)
        + _controler_taux_et_montants(resultat)
    )


def controler_periode(
    periode_id: int, enseignant_ids: Optional[List[int]] = None, db_path: DbPath = None
) -> RapportControle:
    """
    Exécute le contrôle complet d'une période avant validation.

    Réutilise paie_service.calculer_paie_groupe (résultats déjà
    calculés, jamais recalculés ici) et
    dashboard_service.controler_coherence_resultats (contrôles
    arithmétiques déjà écrits et testés, non dupliqués).
    """
    obtenir_periode(periode_id, db_path=db_path)  # lève PeriodeNotFoundError si absente

    if enseignant_ids is None:
        enseignant_ids = _enseignants_avec_donnees(periode_id, db_path=db_path)

    if not enseignant_ids:
        return RapportControle(
            periode_id=periode_id,
            nombre_enseignants=0,
            anomalies=[Anomalie(
                NiveauAnomalie.AVERTISSEMENT, "PERIODE_VIDE", None, None,
                "Aucun enseignant n'a de données de paie sur cette période.",
                recommandation="Vérifiez que la saisie des données de paie a bien été effectuée.",
            )],
        )

    anomalies: List[Anomalie] = []

    try:
        groupe = calculer_paie_groupe(periode_id, enseignant_ids, db_path=db_path)
    except CalculPaieError as erreur:
        anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "PERIODE_NON_CALCULABLE", None, None, str(erreur)))
        return RapportControle(periode_id=periode_id, nombre_enseignants=len(enseignant_ids), anomalies=anomalies)

    for enseignant_id, message in groupe.erreurs.items():
        anomalies.append(Anomalie(
            NiveauAnomalie.ERREUR, "ENSEIGNANT_NON_CALCULABLE", enseignant_id, None, message,
            recommandation="Retirez cet enseignant de la sélection ou vérifiez son existence.",
        ))

    for resultat in groupe.resultats:
        anomalies.extend(_controler_resultat(resultat))

    # Réutilisation directe des contrôles arithmétiques déjà écrits et
    # testés au module 08 (aucune duplication de la logique de cohérence).
    for message in dashboard_service.controler_coherence_resultats(groupe.resultats):
        anomalies.append(Anomalie(NiveauAnomalie.ERREUR, "INCOHERENCE_CALCUL", None, None, message))

    return RapportControle(periode_id=periode_id, nombre_enseignants=len(enseignant_ids), anomalies=anomalies)


# ---------------------------------------------------------------------
# Workflow complet : validation et clôture AVEC contrôle
# ---------------------------------------------------------------------

def _enregistrer_audit(
    periode: PeriodePaie,
    type_action: TypeActionAudit,
    resultat: str,
    db_path: DbPath = None,
    conn=None,
    utilisateur: Optional[str] = None,
) -> None:
    entree = AuditLog(
        type_action=type_action,
        entite="periode_paie",
        entite_id=periode.id,
        details=f"{periode.libelle} — {resultat}",
        utilisateur=utilisateur,
    )
    audit_log_repository.enregistrer(entree, db_path=db_path, conn=conn)


def ouvrir_periode_avec_audit(periode_id: int, db_path: DbPath = None, utilisateur: Optional[str] = None) -> PeriodePaie:
    """
    Transition BROUILLON -> OUVERTE, journalisée dans l'audit
    (section 18 du module 12). La validation de statut et la
    transition elle-même sont intégralement déléguées à
    database.repositories.periode_repository.changer_statut — la même
    fonction bas niveau qu'utilise services.periode_service.ouvrir_periode
    (aucune règle de transition dupliquée ici, seul l'audit est ajouté),
    dans UNE SEULE transaction SQLite avec l'écriture d'audit.
    """
    periode = obtenir_periode(periode_id, db_path=db_path)
    if periode.statut != StatutPeriode.BROUILLON:
        raise ControlePaieError(
            f"Impossible d'ouvrir une période au statut '{periode.statut.value}' "
            "(seule une période BROUILLON peut être ouverte)."
        )

    with get_connection(db_path) as conn:
        try:
            periode_repository.changer_statut(periode_id, StatutPeriode.OUVERTE, conn=conn)
            _enregistrer_audit(periode, TypeActionAudit.PERIODE_OUVERTE, resultat="Succès", conn=conn, utilisateur=utilisateur)
        except Exception as erreur:
            conn.rollback()
            raise ControlePaieError(
                f"L'ouverture a échoué et a été entièrement annulée : {erreur}"
            ) from erreur
        else:
            conn.commit()

    return periode_repository.obtenir_par_id(periode_id, db_path=db_path)


def valider_periode_avec_controle(
    periode_id: int, confirmation: bool = False, db_path: DbPath = None, utilisateur: Optional[str] = None
) -> RapportControle:
    """
    Workflow complet de validation d'une période (section 11) :

    1. vérifie l'existence de la période ;
    2. exécute le contrôle complet (`controler_periode`) ;
    3. refuse la validation si des erreurs bloquantes existent
       (les avertissements, eux, n'empêchent pas la validation mais
       sont retournés dans le rapport pour affichage) ;
    4. exige une confirmation explicite ;
    5. effectue la transition OUVERTE -> VALIDEE — intégralement
       déléguée à database.repositories.periode_repository.changer_statut
       (la même fonction bas niveau qu'utilise
       services.periode_service.valider_periode : aucune règle de
       transition dupliquée) — et l'écriture d'audit dans UNE SEULE
       transaction SQLite ;
    6. retourne le rapport de contrôle (avec les avertissements résiduels).

    Lève ControlePaieError si le contrôle échoue, si la confirmation
    est absente, ou si le statut de la période ne permet pas la
    validation.
    """
    periode = obtenir_periode(periode_id, db_path=db_path)  # lève PeriodeNotFoundError si absente

    rapport = controler_periode(periode_id, db_path=db_path)
    if rapport.est_bloque:
        _enregistrer_audit(
            periode, TypeActionAudit.VALIDATION_REFUSEE,
            resultat=f"{len(rapport.erreurs)} erreur(s) bloquante(s)",
            db_path=db_path, utilisateur=utilisateur,
        )
        raise ControlePaieError(
            f"Validation refusée : {len(rapport.erreurs)} erreur(s) bloquante(s) détectée(s). "
            "Corrigez les données de paie avant de valider cette période."
        )

    if not confirmation:
        raise ControlePaieError("La validation nécessite une confirmation explicite.")

    if periode.statut != StatutPeriode.OUVERTE:
        _enregistrer_audit(
            periode, TypeActionAudit.VALIDATION_REFUSEE,
            resultat=f"Statut invalide ({periode.statut.value})",
            db_path=db_path, utilisateur=utilisateur,
        )
        raise ControlePaieError(
            f"Impossible de valider une période au statut '{periode.statut.value}' "
            "(seule une période OUVERTE peut être validée)."
        )

    with get_connection(db_path) as conn:
        try:
            periode_repository.changer_statut(periode_id, StatutPeriode.VALIDEE, conn=conn)
            _enregistrer_audit(
                periode, TypeActionAudit.VALIDATION_PERIODE,
                resultat=f"Succès ({len(rapport.avertissements)} avertissement(s))",
                conn=conn, utilisateur=utilisateur,
            )
        except Exception as erreur:
            conn.rollback()
            raise ControlePaieError(
                f"La validation a échoué et a été entièrement annulée : {erreur}"
            ) from erreur
        else:
            conn.commit()

    return rapport


def cloturer_periode_avec_controle(
    periode_id: int, confirmation: bool = False, db_path: DbPath = None, utilisateur: Optional[str] = None
) -> RapportControle:
    """
    Workflow complet de clôture d'une période (section 12) : mêmes
    étapes que `valider_periode_avec_controle`, pour la transition
    VALIDEE -> CLOTUREE. Le contrôle est ré-exécuté par prudence (les
    données étant gelées depuis la validation, il ne devrait plus
    révéler d'erreur bloquante nouvelle, mais garantit qu'aucune
    incohérence n'a pu apparaître entre-temps).
    """
    periode = obtenir_periode(periode_id, db_path=db_path)

    rapport = controler_periode(periode_id, db_path=db_path)
    if rapport.est_bloque:
        _enregistrer_audit(
            periode, TypeActionAudit.CLOTURE_REFUSEE,
            resultat=f"{len(rapport.erreurs)} erreur(s) bloquante(s)",
            db_path=db_path, utilisateur=utilisateur,
        )
        raise ControlePaieError(
            f"Clôture refusée : {len(rapport.erreurs)} erreur(s) bloquante(s) détectée(s)."
        )

    if not confirmation:
        raise ControlePaieError("La clôture nécessite une confirmation explicite.")

    if periode.statut != StatutPeriode.VALIDEE:
        _enregistrer_audit(
            periode, TypeActionAudit.CLOTURE_REFUSEE,
            resultat=f"Statut invalide ({periode.statut.value})",
            db_path=db_path, utilisateur=utilisateur,
        )
        raise ControlePaieError(
            f"Impossible de clôturer une période au statut '{periode.statut.value}' "
            "(seule une période VALIDEE peut être clôturée)."
        )

    with get_connection(db_path) as conn:
        try:
            periode_repository.cloturer(periode_id, conn=conn)
            _enregistrer_audit(
                periode, TypeActionAudit.CLOTURE_PERIODE,
                resultat=f"Succès ({len(rapport.avertissements)} avertissement(s))",
                conn=conn, utilisateur=utilisateur,
            )
        except Exception as erreur:
            conn.rollback()
            raise ControlePaieError(
                f"La clôture a échoué et a été entièrement annulée : {erreur}"
            ) from erreur
        else:
            conn.commit()

    return rapport


# ---------------------------------------------------------------------
# Statistiques descriptives (récapitulatif global, section 19)
# ---------------------------------------------------------------------

@dataclass
class StatistiquesNet:
    """Indicateurs statistiques simples sur le net à percevoir d'un ensemble de résultats déjà calculés."""

    moyenne: float = 0.0
    mediane: float = 0.0
    minimum: int = 0
    maximum: int = 0


def statistiques_net(resultats: List[ResultatPaie]) -> StatistiquesNet:
    """
    Calcule moyenne/médiane/min/max du net à percevoir sur un ensemble
    de résultats déjà produits par paie_service. Agrégation purement
    descriptive : aucune formule de paie n'est recalculée ici.
    """
    if not resultats:
        return StatistiquesNet()

    import statistics

    nets = [r.net_a_percevoir for r in resultats]
    return StatistiquesNet(
        moyenne=statistics.mean(nets),
        mediane=statistics.median(nets),
        minimum=min(nets),
        maximum=max(nets),
    )
