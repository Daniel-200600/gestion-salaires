"""
Paramètres de paie modifiables : taux de taxe.

Fonctionnement
--------------
- Un **taux par défaut** (table parametres_paie, clé `taux_taxe_defaut`)
  est appliqué à chaque NOUVELLE période au moment de sa création.
  Tant qu'il n'a jamais été modifié, il vaut config.settings.TAUX_TAXE
  (5,5 %). La taxe ne s'applique qu'aux vacataires (services/paie_service.py).
- Chaque période porte **son propre taux** (colonne periodes_paie.taux_taxe).
  Il peut être ajusté tant que la période est en brouillon ou ouverte,
  puis il est **figé** dès la validation (contrôle ici et trigger SQL).
  Un bulletin validé ou clôturé est donc toujours recalculé à l'identique,
  même si le taux par défaut change ensuite.

La formule elle-même (taxe = base taxable × taux) reste exclusivement
dans services/paie_service.py ; ce service ne fait que stocker et
valider le taux.

Les contrôles d'autorisation (ADMIN) sont appliqués par la façade
services/administration_service.py, seule porte d'entrée utilisée par
les pages.
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Union

from config.settings import TAUX_TAXE
from database.repositories import audit_log_repository, parametres_paie_repository, periode_repository
from models.audit_log import AuditLog
from models.enums import StatutPeriode, TypeActionAudit
from models.periode_paie import PeriodePaie
from utils.formatters import formater_taux_taxe

DbPath = Optional[Union[str, Path]]

CLE_TAUX_TAXE_DEFAUT = "taux_taxe_defaut"

# Bornes raisonnables pour une saisie en pourcentage (garde-fou contre une
# faute de frappe du type 55 au lieu de 5,5).
POURCENTAGE_MAX = Decimal("50")


class ParametrePaieError(ValueError):
    """Valeur de paramètre de paie invalide ou modification refusée."""


def pourcentage_vers_taux(pourcentage) -> Decimal:
    """
    Convertit une saisie en pourcentage (5,5 / "5,5" / "5.5" / Decimal)
    en fraction décimale (Decimal("0.055")). Lève ParametrePaieError si
    la valeur est invalide, négative, supérieure à 50 % ou trop précise.
    """
    texte = str(pourcentage).strip().replace(",", ".").replace("%", "").strip()
    try:
        valeur = Decimal(texte)
    except (InvalidOperation, ValueError):
        raise ParametrePaieError(f"Taux de taxe invalide : « {pourcentage} ». Saisissez un nombre, par exemple 5,5.")
    if not valeur.is_finite():
        raise ParametrePaieError("Taux de taxe invalide.")
    if valeur < 0:
        raise ParametrePaieError("Le taux de taxe ne peut pas être négatif.")
    if valeur > POURCENTAGE_MAX:
        raise ParametrePaieError(
            f"Le taux de taxe ne peut pas dépasser {POURCENTAGE_MAX} %. Vérifiez la saisie (5,5 et non 55)."
        )
    if valeur != valeur.quantize(Decimal("0.01")):
        raise ParametrePaieError("Le taux de taxe accepte au plus deux décimales (ex. 5,25).")
    taux = (valeur / Decimal(100)).normalize()
    return taux if taux != 0 else Decimal("0")


def taux_vers_pourcentage(taux: Decimal) -> Decimal:
    """Decimal("0.055") -> Decimal("5.5")."""
    return (Decimal(str(taux)) * 100).normalize()


def formater_taux(taux: Decimal) -> str:
    """Decimal("0.055") -> "5,5 %" ; Decimal("0.05") -> "5 %"."""
    return formater_taux_taxe(taux)


def obtenir_taux_taxe_defaut(db_path: DbPath = None) -> Decimal:
    """Taux appliqué aux nouvelles périodes. 5,5 % (config.settings.TAUX_TAXE) tant qu'il n'a pas été modifié."""
    valeur = parametres_paie_repository.lire(CLE_TAUX_TAXE_DEFAUT, db_path=db_path)
    if valeur is None:
        return TAUX_TAXE
    try:
        return Decimal(valeur)
    except InvalidOperation:
        return TAUX_TAXE


def definir_taux_taxe_defaut(pourcentage, utilisateur: Optional[str] = None, db_path: DbPath = None) -> Decimal:
    """
    Enregistre le taux par défaut des nouvelles périodes (saisi en %).
    N'affecte AUCUNE période existante. Journalisé.
    """
    ancien = obtenir_taux_taxe_defaut(db_path=db_path)
    taux = pourcentage_vers_taux(pourcentage)
    parametres_paie_repository.ecrire(CLE_TAUX_TAXE_DEFAUT, str(taux), utilisateur=utilisateur, db_path=db_path)
    audit_log_repository.enregistrer(
        AuditLog(
            type_action=TypeActionAudit.PARAMETRE_PAIE_MODIFIE, entite="parametres_paie", entite_id=None,
            utilisateur=utilisateur,
            details=f"Taux de taxe par défaut : {formater_taux(ancien)} -> {formater_taux(taux)}",
        ),
        db_path=db_path,
    )
    return taux


def taux_periode_modifiable(periode: PeriodePaie) -> bool:
    """Le taux d'une période n'est modifiable qu'en brouillon ou ouverte (figé à la validation)."""
    return periode.statut in (StatutPeriode.BROUILLON, StatutPeriode.OUVERTE)


def definir_taux_taxe_periode(
    periode_id: int, pourcentage, utilisateur: Optional[str] = None, db_path: DbPath = None
) -> PeriodePaie:
    """
    Modifie le taux de taxe d'une période encore en brouillon ou ouverte.
    Refusé pour une période validée ou clôturée. Journalisé.
    """
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise ParametrePaieError(f"Aucune période avec l'id {periode_id}.")
    if not taux_periode_modifiable(periode):
        raise ParametrePaieError(
            f"Le taux de la période {periode.libelle} est figé : la période est "
            f"{'validée' if periode.statut == StatutPeriode.VALIDEE else 'clôturée'}."
        )
    taux = pourcentage_vers_taux(pourcentage)
    ancien = periode.taux_taxe
    periode_repository.modifier_taux_taxe(periode_id, taux, db_path=db_path)
    audit_log_repository.enregistrer(
        AuditLog(
            type_action=TypeActionAudit.PARAMETRE_PAIE_MODIFIE, entite="periode", entite_id=periode_id,
            utilisateur=utilisateur,
            details=f"Taux de taxe de {periode.libelle} : {formater_taux(ancien)} -> {formater_taux(taux)}",
        ),
        db_path=db_path,
    )
    return periode_repository.obtenir_par_id(periode_id, db_path=db_path)
