"""
Logique métier de gestion des enseignants.

Cette couche ne dépend jamais de Streamlit et n'exécute aucun SQL
directement : elle valide les données (via utils.validators), puis
délègue la persistance à database.repositories.enseignant_repository.

Deux façons distinctes de retirer un enseignant :
- `desactiver_enseignant` : l'enseignant reste en base (champ actif),
  son historique reste consultable. C'est la voie normale.
- `supprimer_enseignant_definitivement` : suppression PHYSIQUE et
  IRRÉVERSIBLE, refusée sans exception si le moindre bulletin de paie
  existe pour cet enseignant (traçabilité des salaires protégée).
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional, Union
import sqlite3

from database.connection import get_connection
from database.repositories import (
    bulletin_repository,
    enseignant_repository,
    heures_repository,
    remuneration_repository,
    retenue_repository,
)
from database.repositories import audit_log_repository
from models.audit_log import AuditLog
from models.enseignant import Enseignant
from models.enums import TypeActionAudit
from utils.validators import (
    EnseignantValidationError,
    nettoyer_champ_optionnel,
    nettoyer_texte,
    valider_nom_ou_prenom,
    valider_sexe,
    valider_statut,
    valider_taux_horaire,
)

DbPath = Optional[Union[str, Path]]

# Réexporté ici pour que la page (et les appelants) n'aient besoin que
# d'importer depuis services.enseignant_service, sans connaître la
# couche utils.validators sous-jacente.
__all__ = [
    "EnseignantValidationError",
    "EnseignantNotFoundError",
    "DependancesEnseignant",
    "MESSAGE_BULLETIN_EXISTANT",
    "creer_enseignant",
    "obtenir_enseignant",
    "lister_enseignants",
    "rechercher_enseignants",
    "modifier_enseignant",
    "lister_enseignants_a_completer",
    "lister_enseignants_payables",
    "changer_statut_enseignant",
    "desactiver_enseignant",
    "reactiver_enseignant",
    "obtenir_dependances_enseignant",
    "supprimer_enseignant_definitivement",
]


class EnseignantNotFoundError(EnseignantValidationError):
    """
    Levée quand l'enseignant demandé n'existe pas en base.

    Hérite de EnseignantValidationError : du point de vue de l'appelant
    (page ou test), cibler un enseignant inexistant est une forme
    d'entrée invalide ; un seul type d'exception métier suffit à
    capturer l'ensemble des cas d'erreur du module.
    """


def _construire_enseignant_valide(
    nom, prenom, sexe, statut, taux_horaire, email, telephone, adresse,
    enseignant_id: Optional[int] = None,
    actif: bool = True,
) -> Enseignant:
    """Valide l'ensemble des champs et construit un Enseignant prêt à persister."""
    return Enseignant(
        id=enseignant_id,
        nom=valider_nom_ou_prenom(nom, "nom"),
        prenom=valider_nom_ou_prenom(prenom, "prenom"),
        sexe=valider_sexe(sexe),
        statut=valider_statut(statut),
        taux_horaire=valider_taux_horaire(taux_horaire),
        email=nettoyer_champ_optionnel(email),
        telephone=nettoyer_champ_optionnel(telephone),
        adresse=nettoyer_champ_optionnel(adresse),
        actif=actif,
    )


def creer_enseignant(
    nom: str,
    prenom: str,
    sexe,
    statut,
    taux_horaire,
    email: Optional[str] = None,
    telephone: Optional[str] = None,
    adresse: Optional[str] = None,
    db_path: DbPath = None,
) -> Enseignant:
    """Valide puis crée un nouvel enseignant (actif par défaut)."""
    enseignant = _construire_enseignant_valide(
        nom, prenom, sexe, statut, taux_horaire, email, telephone, adresse, actif=True
    )
    nouvel_id = enseignant_repository.creer(enseignant, db_path=db_path)
    return enseignant_repository.obtenir_par_id(nouvel_id, db_path=db_path)


def obtenir_enseignant(enseignant_id: int, db_path: DbPath = None) -> Enseignant:
    """Retourne un enseignant par son id, ou lève EnseignantNotFoundError."""
    enseignant = enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)
    if enseignant is None:
        raise EnseignantNotFoundError(f"Aucun enseignant avec l'id {enseignant_id}.")
    return enseignant


def lister_enseignants(inclure_inactifs: bool = False, db_path: DbPath = None) -> List[Enseignant]:
    """
    Liste les enseignants.

    Par défaut (inclure_inactifs=False) : seuls les enseignants actifs
    sont retournés, conformément à la règle métier (un enseignant
    désactivé ne doit plus apparaître par défaut dans les listes
    destinées aux nouvelles paies).
    """
    return enseignant_repository.lister(inclure_inactifs=inclure_inactifs, db_path=db_path)


def rechercher_enseignants(
    terme: str, inclure_inactifs: bool = False, db_path: DbPath = None
) -> List[Enseignant]:
    """Recherche par nom, prénom ou nom complet, insensible à la casse."""
    terme_nettoye = (terme or "").strip()
    if not terme_nettoye:
        return enseignant_repository.lister(inclure_inactifs=inclure_inactifs, db_path=db_path)
    return enseignant_repository.rechercher(terme_nettoye, inclure_inactifs=inclure_inactifs, db_path=db_path)


def modifier_enseignant(
    enseignant_id: int,
    nom: str,
    prenom: str,
    sexe,
    statut,
    taux_horaire,
    email: Optional[str] = None,
    telephone: Optional[str] = None,
    adresse: Optional[str] = None,
    db_path: DbPath = None,
    utilisateur: Optional[str] = None,
) -> Enseignant:
    """
    Valide puis applique une modification à un enseignant existant. Ne
    touche pas à `actif`. Un changement de statut est journalisé (voir
    `changer_statut_enseignant`).
    """
    existant = obtenir_enseignant(enseignant_id, db_path=db_path)  # lève si inexistant
    # Compléter une fiche importée : une information encore inconnue (None)
    # garde sa valeur actuelle, éventuellement vide ; elle n'efface jamais
    # une valeur déjà renseignée. Prénom vide accepté seulement s'il l'était.
    enseignant_modifie = Enseignant(
        id=existant.id,
        nom=valider_nom_ou_prenom(nom, "nom"),
        prenom=(nettoyer_texte(prenom) if not existant.prenom and not nettoyer_texte(prenom)
                else valider_nom_ou_prenom(prenom, "prenom")),
        sexe=existant.sexe if _vide(sexe) else valider_sexe(sexe),
        statut=existant.statut if _vide(statut) else valider_statut(statut),
        taux_horaire=existant.taux_horaire if _vide(taux_horaire) else valider_taux_horaire(taux_horaire),
        email=nettoyer_champ_optionnel(email),
        telephone=nettoyer_champ_optionnel(telephone),
        adresse=nettoyer_champ_optionnel(adresse),
        actif=existant.actif,
    )
    enseignant_repository.mettre_a_jour(enseignant_modifie, db_path=db_path)
    if enseignant_modifie.statut != existant.statut:
        _journaliser_changement_statut(existant, enseignant_modifie.statut, utilisateur, db_path)
    return enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)


_LIBELLES_STATUT = {"V": "Vacataire", "P": "Permanent", None: "non renseigné"}


def _vide(valeur) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def lister_enseignants_a_completer(db_path: DbPath = None) -> List[Enseignant]:
    """Enseignants actifs dont la fiche est incomplète (exclus de la paie tant qu'elle l'est)."""
    return [e for e in enseignant_repository.lister(db_path=db_path) if not e.est_complet]


def lister_enseignants_payables(db_path: DbPath = None) -> List[Enseignant]:
    """Enseignants actifs à fiche complète : les seuls proposés pour la saisie et le calcul de la paie."""
    return [e for e in enseignant_repository.lister(db_path=db_path) if e.est_complet]


def _journaliser_changement_statut(enseignant: Enseignant, nouveau_statut, utilisateur: Optional[str],
                                   db_path: DbPath) -> None:
    audit_log_repository.enregistrer(
        AuditLog(
            type_action=TypeActionAudit.STATUT_ENSEIGNANT_MODIFIE, entite="enseignant", entite_id=enseignant.id,
            utilisateur=utilisateur,
            details=(f"{enseignant.nom} {enseignant.prenom} : {_LIBELLES_STATUT[enseignant.statut.value if enseignant.statut else None]} -> "
                     f"{_LIBELLES_STATUT[nouveau_statut.value]}"),
        ),
        db_path=db_path,
    )


def changer_statut_enseignant(
    enseignant_id: int, nouveau_statut, utilisateur: Optional[str] = None, db_path: DbPath = None
) -> Enseignant:
    """
    Change le statut d'un enseignant (Vacataire <-> Permanent). Le
    nouveau statut s'applique aux calculs et bulletins produits à partir
    de maintenant. Les bulletins déjà émis pour une période validée ou
    clôturée gardent le statut enregistré dans leur instantané
    (services/bulletin_service.py). Le changement est journalisé.
    """
    existant = obtenir_enseignant(enseignant_id, db_path=db_path)  # lève si inexistant
    statut = valider_statut(nouveau_statut)
    if statut == existant.statut:
        raise EnseignantValidationError(
            f"L'enseignant est déjà {_LIBELLES_STATUT[statut.value].lower()} : aucun changement."
        )
    enseignant_repository.mettre_a_jour(replace(existant, statut=statut), db_path=db_path)
    _journaliser_changement_statut(existant, statut, utilisateur, db_path)
    return enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)


def desactiver_enseignant(enseignant_id: int, db_path: DbPath = None) -> Enseignant:
    """
    Désactive un enseignant (actif = 0). Ne supprime jamais la ligne :
    l'historique de paie associé reste intact et consultable.
    """
    obtenir_enseignant(enseignant_id, db_path=db_path)  # lève si inexistant
    enseignant_repository.changer_statut_actif(enseignant_id, actif=False, db_path=db_path)
    return enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)


def reactiver_enseignant(enseignant_id: int, db_path: DbPath = None) -> Enseignant:
    """Réactive un enseignant précédemment désactivé (actif = 1)."""
    obtenir_enseignant(enseignant_id, db_path=db_path)  # lève si inexistant
    enseignant_repository.changer_statut_actif(enseignant_id, actif=True, db_path=db_path)
    return enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)


# ---------------------------------------------------------------------
# Suppression définitive (irréversible)
# ---------------------------------------------------------------------

MESSAGE_BULLETIN_EXISTANT = (
    "Cet enseignant possède un historique de paie. Pour préserver la traçabilité des "
    "salaires, il ne peut pas être supprimé définitivement. Vous pouvez le désactiver."
)


@dataclass
class DependancesEnseignant:
    """
    Dénombrement des données liées à un enseignant, utilisé pour
    informer l'administrateur avant confirmation d'une suppression
    définitive (cf. pages/1_Enseignants.py).
    """

    nombre_heures: int = 0
    nombre_elements_remuneration: int = 0
    nombre_retenues: int = 0
    nombre_bulletins: int = 0
    bulletins_generes_sur_disque: bool = False

    @property
    def a_des_donnees_de_paie(self) -> bool:
        """Vrai si l'enseignant a des heures, rémunérations ou retenues (CAS 2)."""
        return self.nombre_heures > 0 or self.nombre_elements_remuneration > 0 or self.nombre_retenues > 0

    @property
    def a_des_bulletins(self) -> bool:
        """
        Vrai si l'enseignant a au moins un bulletin (CAS 3 : suppression
        interdite). Combine deux sources : la table bulletins_paie
        (persistance future, non alimentée par le module 07 actuel) et
        les fichiers .docx réellement générés sur disque par
        services/bulletin_service.py — sans cette seconde vérification,
        un bulletin bel et bien généré par le module 07 ne serait
        jamais détecté ici.
        """
        return self.nombre_bulletins > 0 or self.bulletins_generes_sur_disque


def obtenir_dependances_enseignant(enseignant_id: int, db_path: DbPath = None) -> DependancesEnseignant:
    """
    Dénombre toutes les données liées à un enseignant (heures,
    rémunérations, retenues, bulletins), toutes périodes confondues.
    Lecture seule, ne modifie rien.
    """
    from services import bulletin_service  # import différé : évite tout cycle au chargement du module

    enseignant = enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)
    bulletins_sur_disque = (
        bulletin_service.enseignant_a_des_bulletins(enseignant.nom, enseignant.prenom, db_path=db_path)
        if enseignant is not None
        else False
    )

    return DependancesEnseignant(
        nombre_heures=heures_repository.compter_par_enseignant(enseignant_id, db_path=db_path),
        nombre_elements_remuneration=remuneration_repository.compter_par_enseignant(
            enseignant_id, db_path=db_path
        ),
        nombre_retenues=retenue_repository.compter_par_enseignant(enseignant_id, db_path=db_path),
        nombre_bulletins=bulletin_repository.compter_par_enseignant(enseignant_id, db_path=db_path),
        bulletins_generes_sur_disque=bulletins_sur_disque,
    )


def _enregistrer_audit_suppression(
    enseignant: Enseignant,
    resultat: str,
    db_path: DbPath = None,
    conn: "Optional[sqlite3.Connection]" = None,
) -> None:
    """
    Journalise une tentative ou une suppression définitive réussie.

    Ne conserve que le strict nécessaire à la traçabilité (nom/prénom
    au moment de l'action, résultat) — aucune donnée sensible (email,
    téléphone, adresse) n'est stockée dans l'audit.
    """
    entree = AuditLog(
        type_action=TypeActionAudit.SUPPRESSION_DEFINITIVE,
        entite="enseignant",
        entite_id=enseignant.id,
        details=f"{enseignant.nom} {enseignant.prenom} — {resultat}",
    )
    audit_log_repository.enregistrer(entree, db_path=db_path, conn=conn)


def supprimer_enseignant_definitivement(
    enseignant_id: int, confirmation: bool = False, db_path: DbPath = None
) -> DependancesEnseignant:
    """
    Supprime PHYSIQUEMENT et IRRÉVERSIBLEMENT un enseignant, ainsi que
    toutes ses données de paie dépendantes (heures, rémunérations,
    retenues), dans une SEULE TRANSACTION SQLite.

    Règles appliquées :
    - CAS 1 (aucune donnée liée) : suppression autorisée.
    - CAS 2 (heures/rémunérations/retenues mais aucun bulletin) :
      suppression autorisée, données dépendantes purgées dans la même
      transaction que l'enseignant.
    - CAS 3 (au moins un bulletin existant) : suppression TOUJOURS
      refusée, sans exception — l'historique de paie est protégé.

    `confirmation=True` est un garde-fou explicite, obligatoire : cette
    fonction refuse toute suppression tant qu'il n'est pas fourni,
    même pour un enseignant sans aucune donnée liée. C'est une
    protection au niveau service, en plus de la confirmation en deux
    étapes exigée côté interface (pages/1_Enseignants.py) — la règle
    ne peut donc jamais être contournée depuis l'UI.

    En cas d'erreur à N'IMPORTE quelle étape (y compris après que des
    dépendances ont déjà été supprimées) : ROLLBACK complet, rien
    n'est modifié.

    Retourne le dénombrement des dépendances qui viennent d'être
    supprimées (pour un message de confirmation côté page).
    """
    enseignant = enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)
    if enseignant is None:
        raise EnseignantNotFoundError(f"Aucun enseignant avec l'id {enseignant_id}.")

    if not confirmation:
        raise EnseignantValidationError(
            "La suppression définitive nécessite une confirmation explicite."
        )

    dependances = obtenir_dependances_enseignant(enseignant_id, db_path=db_path)

    if dependances.a_des_bulletins:
        # CAS 3 : refus absolu, jamais contournable. On journalise la
        # tentative (aucune donnée n'a été touchée, pas besoin de
        # transaction dédiée).
        _enregistrer_audit_suppression(enseignant, resultat="Refusé (bulletin existant)", db_path=db_path)
        raise EnseignantValidationError(MESSAGE_BULLETIN_EXISTANT)

    # CAS 1 ou CAS 2 : suppression en cascade, une seule transaction.
    with get_connection(db_path) as conn:
        try:
            heures_repository.supprimer_par_enseignant(enseignant_id, conn=conn)
            remuneration_repository.supprimer_par_enseignant(enseignant_id, conn=conn)
            retenue_repository.supprimer_par_enseignant(enseignant_id, conn=conn)
            enseignant_repository.supprimer_definitivement(enseignant_id, conn=conn)
            _enregistrer_audit_suppression(enseignant, resultat="Succès", conn=conn)
        except Exception as erreur:
            conn.rollback()
            raise EnseignantValidationError(
                f"La suppression définitive a échoué et a été entièrement annulée : {erreur}"
            ) from erreur
        else:
            conn.commit()

    return dependances
