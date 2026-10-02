"""
Logique métier de gestion des périodes de paie.

Cycle de vie strict : BROUILLON -> OUVERTE -> VALIDEE -> CLOTUREE.
Chaque transition a sa propre fonction (ouvrir_periode, valider_periode,
cloturer_periode) plutôt qu'une fonction générique de changement de
statut, afin que chaque règle métier soit explicite, isolément
testable, et ne puisse pas être contournée par un appel générique.

Cette couche ne dépend jamais de Streamlit et n'exécute aucun SQL
directement : elle valide les données puis délègue la persistance à
database.repositories.periode_repository. Le contrôle des transitions
est de plus garanti au niveau SQL par des triggers (cf. schema.sql) :
même un bug dans ce service ne pourrait pas produire une transition
illégale en base.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from database.connection import get_connection
from database.repositories import (
    audit_log_repository,
    heures_repository,
    periode_repository,
    remuneration_repository,
    retenue_repository,
)
from models.audit_log import AuditLog
from models.enums import StatutPeriode, TypeActionAudit
from models.periode_paie import PeriodePaie
from utils.formatters import nom_mois

DbPath = Optional[Union[str, Path]]

MOIS_MIN = 1
MOIS_MAX = 12
ANNEE_MIN = 2000
ANNEE_MAX = 2100


class PeriodeValidationError(Exception):
    """Levée quand une donnée de période est invalide ou qu'une transition est illégale."""


class PeriodeNotFoundError(PeriodeValidationError):
    """
    Levée quand la période demandée n'existe pas en base.

    Hérite de PeriodeValidationError pour qu'un seul type d'exception
    métier suffise à capturer l'ensemble des cas d'erreur du module,
    côté page comme côté tests.
    """


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def _valider_mois(mois) -> int:
    try:
        mois_int = int(mois)
    except (TypeError, ValueError):
        raise PeriodeValidationError("Le mois doit être un nombre entier.")
    if mois_int < MOIS_MIN or mois_int > MOIS_MAX:
        raise PeriodeValidationError(f"Le mois doit être compris entre {MOIS_MIN} et {MOIS_MAX}.")
    return mois_int


def _valider_annee(annee) -> int:
    try:
        annee_int = int(annee)
    except (TypeError, ValueError):
        raise PeriodeValidationError("L'année doit être un nombre entier.")
    if annee_int < ANNEE_MIN or annee_int > ANNEE_MAX:
        raise PeriodeValidationError(
            f"L'année doit être comprise entre {ANNEE_MIN} et {ANNEE_MAX}."
        )
    return annee_int


def generer_libelle(mois: int, annee: int) -> str:
    """Génère automatiquement le libellé d'une période, ex: 'Août 2026'."""
    return f"{nom_mois(mois)} {annee}"


# ---------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------

def obtenir_periode(periode_id: int, db_path: DbPath = None) -> PeriodePaie:
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise PeriodeNotFoundError(f"Aucune période avec l'id {periode_id}.")
    return periode


def est_modifiable(periode: PeriodePaie) -> bool:
    """
    Vrai si la période autorise encore la saisie ou la modification de
    données de paie (heures, rémunérations, retenues) — c'est-à-dire
    si son statut est exactement OUVERTE.

    Règle unique du projet, déjà appliquée à deux niveaux depuis les
    modules 03/04 : `utils.validators.verifier_periode_ouverte` (appelée
    par heures_service/remuneration_service/retenue_service avant toute
    écriture) ET les triggers SQL `*_periode_modifiable` sur
    saisies_heures/elements_remuneration/retenues (cf. schema.sql), qui
    n'autorisent INSERT/UPDATE que si le statut de la période est
    'ouverte'. Cette fonction n'introduit aucune troisième règle : elle
    expose la même condition sous un nom explicite, pour les pages qui
    doivent savoir si les contrôles de saisie sont à afficher, sans
    disposer d'un enregistrement de saisie concret à valider.
    """
    return periode.statut == StatutPeriode.OUVERTE


def verifier_periode_modifiable(periode: PeriodePaie) -> None:
    """Lève PeriodeValidationError si la période n'autorise plus la modification de ses données de paie."""
    if not est_modifiable(periode):
        raise PeriodeValidationError(
            f"Cette période est au statut '{periode.statut.value}' : ses données de paie "
            "ne sont plus modifiables."
        )


def est_cloturee(periode: PeriodePaie) -> bool:
    """Vrai si la période est définitivement clôturée (aucune modification possible, dans aucun cas)."""
    return periode.statut == StatutPeriode.CLOTUREE


TRANSITIONS_AUTORISEES = {
    StatutPeriode.BROUILLON: StatutPeriode.OUVERTE,
    StatutPeriode.OUVERTE: StatutPeriode.VALIDEE,
    StatutPeriode.VALIDEE: StatutPeriode.CLOTUREE,
}


def transition_autorisee(statut_actuel: StatutPeriode, statut_cible: StatutPeriode) -> bool:
    """
    Vrai si la transition d'un statut à l'autre est autorisée par le
    workflow (section 5) : BROUILLON -> OUVERTE -> VALIDEE -> CLOTUREE
    uniquement, jamais en arrière. Reflète exactement les règles déjà
    appliquées par ouvrir_periode/valider_periode/cloturer_periode et
    par le trigger SQL trg_periodes_paie_transition_invalide (défense
    en profondeur, cf. schema.sql) — aucune règle supplémentaire.
    """
    return TRANSITIONS_AUTORISEES.get(statut_actuel) == statut_cible


def lister_periodes(
    annee: Optional[int] = None,
    statut: Optional[StatutPeriode] = None,
    db_path: DbPath = None,
) -> List[PeriodePaie]:
    """Liste les périodes (les plus récentes en premier), avec filtres optionnels."""
    return periode_repository.lister(annee=annee, statut=statut, db_path=db_path)


# ---------------------------------------------------------------------
# Création et modification (BROUILLON uniquement)
# ---------------------------------------------------------------------

def creer_periode(mois, annee, db_path: DbPath = None) -> PeriodePaie:
    """Valide, vérifie l'absence de doublon (mois, année), puis crée la période (BROUILLON)."""
    mois_valide = _valider_mois(mois)
    annee_valide = _valider_annee(annee)

    if periode_repository.obtenir_par_mois_annee(mois_valide, annee_valide, db_path=db_path):
        raise PeriodeValidationError(
            f"Une période existe déjà pour {generer_libelle(mois_valide, annee_valide)}."
        )

    libelle = generer_libelle(mois_valide, annee_valide)
    # Le taux de taxe en vigueur à la création est recopié sur la période
    # (modifiable ensuite jusqu'à la validation, cf. parametres_paie_service).
    from services.parametres_paie_service import obtenir_taux_taxe_defaut  # import local : évite un cycle
    periode = PeriodePaie(
        mois=mois_valide, annee=annee_valide, libelle=libelle,
        taux_taxe=obtenir_taux_taxe_defaut(db_path=db_path),
    )

    try:
        nouvel_id = periode_repository.creer(periode, db_path=db_path)
    except sqlite3.IntegrityError:
        # Filet de sécurité (ex: appel concurrent) : la contrainte UNIQUE
        # du schéma protège même si la vérification préalable est
        # contournée. On la traduit en erreur métier lisible.
        raise PeriodeValidationError(
            f"Une période existe déjà pour {generer_libelle(mois_valide, annee_valide)}."
        )
    return periode_repository.obtenir_par_id(nouvel_id, db_path=db_path)


def modifier_periode(
    periode_id: int, mois=None, annee=None, db_path: DbPath = None
) -> PeriodePaie:
    """
    Corrige le mois et/ou l'année d'une période, UNIQUEMENT si elle est
    encore en BROUILLON. Dès qu'une période a été ouverte, validée ou
    clôturée, elle ne doit plus pouvoir être renommée ou déplacée : il
    faut créer une nouvelle période plutôt que déplacer une période déjà
    en circulation.
    """
    existante = obtenir_periode(periode_id, db_path=db_path)
    if existante.statut != StatutPeriode.BROUILLON:
        raise PeriodeValidationError(
            "Seule une période au statut BROUILLON peut être modifiée "
            f"(statut actuel : '{existante.statut.value}')."
        )

    nouveau_mois = _valider_mois(mois) if mois is not None else existante.mois
    nouvelle_annee = _valider_annee(annee) if annee is not None else existante.annee

    if (nouveau_mois, nouvelle_annee) != (existante.mois, existante.annee):
        doublon = periode_repository.obtenir_par_mois_annee(
            nouveau_mois, nouvelle_annee, db_path=db_path
        )
        if doublon is not None and doublon.id != existante.id:
            raise PeriodeValidationError(
                f"Une période existe déjà pour {generer_libelle(nouveau_mois, nouvelle_annee)}."
            )

    periode_modifiee = PeriodePaie(
        id=existante.id,
        mois=nouveau_mois,
        annee=nouvelle_annee,
        libelle=generer_libelle(nouveau_mois, nouvelle_annee),
        statut=existante.statut,
        date_creation=existante.date_creation,
        date_cloture=existante.date_cloture,
    )
    periode_repository.modifier(periode_modifiee, db_path=db_path)
    return periode_repository.obtenir_par_id(periode_id, db_path=db_path)


# ---------------------------------------------------------------------
# Transitions (une fonction dédiée par transition)
# ---------------------------------------------------------------------

def ouvrir_periode(periode_id: int, db_path: DbPath = None) -> PeriodePaie:
    """Transition BROUILLON -> OUVERTE : ouvre la période à la saisie des heures/primes/retenues."""
    periode = obtenir_periode(periode_id, db_path=db_path)
    if periode.statut != StatutPeriode.BROUILLON:
        raise PeriodeValidationError(
            f"Impossible d'ouvrir une période au statut '{periode.statut.value}' "
            "(seule une période BROUILLON peut être ouverte)."
        )
    periode_repository.changer_statut(periode_id, StatutPeriode.OUVERTE, db_path=db_path)
    return periode_repository.obtenir_par_id(periode_id, db_path=db_path)


def valider_periode(periode_id: int, db_path: DbPath = None) -> PeriodePaie:
    """Transition OUVERTE -> VALIDEE : gèle les données de paie et prépare la génération des bulletins."""
    periode = obtenir_periode(periode_id, db_path=db_path)
    if periode.statut != StatutPeriode.OUVERTE:
        raise PeriodeValidationError(
            f"Impossible de valider une période au statut '{periode.statut.value}' "
            "(seule une période OUVERTE peut être validée)."
        )
    periode_repository.changer_statut(periode_id, StatutPeriode.VALIDEE, db_path=db_path)
    return periode_repository.obtenir_par_id(periode_id, db_path=db_path)


def cloturer_periode(periode_id: int, db_path: DbPath = None) -> PeriodePaie:
    """Transition VALIDEE -> CLOTUREE : clôture définitivement la période (renseigne date_cloture)."""
    periode = obtenir_periode(periode_id, db_path=db_path)
    if periode.statut != StatutPeriode.VALIDEE:
        raise PeriodeValidationError(
            f"Impossible de clôturer une période au statut '{periode.statut.value}' "
            "(seule une période VALIDEE peut être clôturée)."
        )
    periode_repository.cloturer(periode_id, db_path=db_path)
    return periode_repository.obtenir_par_id(periode_id, db_path=db_path)


# ---------------------------------------------------------------------
# Suppression définitive (irréversible)
# ---------------------------------------------------------------------

MESSAGE_BULLETIN_EXISTANT = (
    "Suppression définitive impossible : cette période possède un ou plusieurs bulletins de paie. "
    "La période doit être conservée afin de préserver l'historique."
)

MESSAGE_STATUT_NON_BROUILLON = (
    "Suppression définitive impossible : seule une période encore au statut BROUILLON peut être "
    "supprimée définitivement. Les périodes OUVERTE, VALIDEE ou CLOTUREE doivent être conservées "
    "afin de préserver l'historique de paie."
)


@dataclass
class DependancesPeriode:
    """
    Dénombrement des données liées à une période, utilisé pour
    informer l'administrateur avant confirmation d'une suppression
    définitive (cf. pages/2_Periodes_Paie.py).
    """

    nombre_heures: int = 0
    nombre_elements_remuneration: int = 0
    nombre_retenues: int = 0
    bulletins_generes_sur_disque: bool = False

    @property
    def a_des_donnees_de_paie(self) -> bool:
        """Vrai si la période a des heures, rémunérations ou retenues saisies (tout enseignant confondu)."""
        return self.nombre_heures > 0 or self.nombre_elements_remuneration > 0 or self.nombre_retenues > 0

    @property
    def a_des_bulletins(self) -> bool:
        """Vrai si au moins un bulletin a été généré pour cette période : suppression toujours interdite."""
        return self.bulletins_generes_sur_disque


def obtenir_dependances_periode(periode_id: int, db_path: DbPath = None) -> DependancesPeriode:
    """
    Dénombre toutes les données liées à une période (heures,
    rémunérations, retenues, bulletins), tout enseignant confondu.
    Lecture seule, ne modifie rien.
    """
    from services import bulletin_service  # import différé : évite tout cycle au chargement du module

    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    bulletins_sur_disque = bulletin_service.periode_a_des_bulletins(periode.libelle) if periode is not None else False

    return DependancesPeriode(
        nombre_heures=heures_repository.compter_par_periode(periode_id, db_path=db_path),
        nombre_elements_remuneration=remuneration_repository.compter_par_periode(periode_id, db_path=db_path),
        nombre_retenues=retenue_repository.compter_par_periode(periode_id, db_path=db_path),
        bulletins_generes_sur_disque=bulletins_sur_disque,
    )


def _enregistrer_audit_suppression_periode(
    periode: PeriodePaie,
    resultat: str,
    db_path: DbPath = None,
    conn: "Optional[sqlite3.Connection]" = None,
) -> None:
    """Journalise une tentative ou une suppression définitive réussie de période."""
    entree = AuditLog(
        type_action=TypeActionAudit.SUPPRESSION_DEFINITIVE,
        entite="periode_paie",
        entite_id=periode.id,
        details=f"{periode.libelle} — {resultat}",
    )
    audit_log_repository.enregistrer(entree, db_path=db_path, conn=conn)


def supprimer_periode_definitivement(
    periode_id: int, confirmation: bool = False, db_path: DbPath = None
) -> DependancesPeriode:
    """
    Supprime PHYSIQUEMENT et IRRÉVERSIBLEMENT une période de paie,
    ainsi que ses données dépendantes (heures, rémunérations,
    retenues, tout enseignant confondu), dans une SEULE TRANSACTION
    SQLite.

    Règles appliquées, dans cet ordre :
    1. Bulletin existant (n'importe quel enseignant) -> refus absolu,
       sans exception, quel que soit le statut de la période.
    2. Statut différent de BROUILLON -> refus. Seule une période
       BROUILLON (qui, par construction, n'a jamais pu recevoir de
       données de paie — la saisie exige le statut OUVERTE) peut être
       supprimée. Ce même principe est appliqué au niveau SQL par le
       trigger trg_periodes_paie_suppression_limitee (cf. schema.sql) :
       même en cas de bug ici, la base rejetterait la suppression.
    3. Sinon : suppression en cascade des dépendances puis de la
       période, dans une transaction unique.

    `confirmation=True` est un garde-fou explicite et obligatoire,
    identique dans son principe à
    services.enseignant_service.supprimer_enseignant_definitivement :
    protection au niveau service, en plus de la confirmation exigée
    côté interface — jamais contournable depuis l'UI.

    En cas d'erreur à N'IMPORTE quelle étape : ROLLBACK complet, rien
    n'est modifié. Retourne le dénombrement des dépendances supprimées.
    """
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise PeriodeNotFoundError(f"Aucune période avec l'id {periode_id}.")

    if not confirmation:
        raise PeriodeValidationError("La suppression définitive nécessite une confirmation explicite.")

    dependances = obtenir_dependances_periode(periode_id, db_path=db_path)

    if dependances.a_des_bulletins:
        _enregistrer_audit_suppression_periode(periode, resultat="Refusé (bulletin existant)", db_path=db_path)
        raise PeriodeValidationError(MESSAGE_BULLETIN_EXISTANT)

    if periode.statut != StatutPeriode.BROUILLON:
        _enregistrer_audit_suppression_periode(
            periode, resultat=f"Refusé (statut {periode.statut.value})", db_path=db_path
        )
        raise PeriodeValidationError(MESSAGE_STATUT_NON_BROUILLON)

    with get_connection(db_path) as conn:
        try:
            heures_repository.supprimer_par_periode(periode_id, conn=conn)
            remuneration_repository.supprimer_par_periode(periode_id, conn=conn)
            retenue_repository.supprimer_par_periode(periode_id, conn=conn)
            periode_repository.supprimer_definitivement(periode_id, conn=conn)
            _enregistrer_audit_suppression_periode(periode, resultat="Succès", conn=conn)
        except Exception as erreur:
            conn.rollback()
            raise PeriodeValidationError(
                f"La suppression définitive a échoué et a été entièrement annulée : {erreur}"
            ) from erreur
        else:
            conn.commit()

    return dependances
