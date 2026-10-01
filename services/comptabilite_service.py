"""
Service comptable (module 06).

Prépare les données consommées par le générateur Excel
(exports/excel_export.py), exclusivement à partir des résultats déjà
calculés par le moteur de paie (services/paie_service.py).

RÈGLE ABSOLUE : ce service ne recalcule JAMAIS gain_heures, taxe_5 ou
net_a_percevoir — il ne fait qu'orchestrer la récupération des
enseignants concernés, déléguer le calcul à
paie_service.calculer_paie_groupe(), puis structurer/agréger ces
résultats déjà produits (paie_service.calculer_totaux_groupe(), et une
petite synthèse par statut construite ici en pure agrégation).

Aucune dépendance à Streamlit.

COMPATIBILITÉ FUTURE (bulletins Word)
---------------------------------------
`preparer_etat_comptable()` retourne un objet EtatComptablePeriode
totalement indépendant d'Excel : il contient uniquement des résultats
de paie structurés (ResultatPaie, TotauxPaieGroupe, synthèse par
statut). Le futur module de génération de bulletins Word pourra
consommer cette même fonction plutôt que de redemander un calcul —
une seule source de résultats, deux exports possibles.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from database.repositories import periode_repository
from models.enums import StatutEnseignant, StatutPeriode
from models.periode_paie import PeriodePaie
from models.resultat_paie import ResultatPaie
from services import heures_service, remuneration_service, retenue_service
from services.paie_service import TotauxPaieGroupe, calculer_paie_groupe, calculer_totaux_groupe

DbPath = Optional[Union[str, Path]]


class ComptabiliteError(Exception):
    """
    Levée pour toute impossibilité de préparer un état comptable :
    période introuvable, période encore en BROUILLON, ou aucun
    enseignant disponible pour la période.
    """


@dataclass
class SyntheseParStatut:
    """Nombre d'enseignants et total net par statut (Permanent / Vacataire)."""

    statut: StatutEnseignant
    nombre: int
    total_net: int


@dataclass
class EtatComptablePeriode:
    """
    Regroupe tout ce dont exports/excel_export.py a besoin pour générer
    le fichier : la période, les résultats individuels déjà calculés,
    les totaux déjà agrégés, la synthèse par statut, et les éventuelles
    erreurs de calcul par enseignant (ne bloquent pas la génération des
    autres résultats, cohérent avec paie_service.calculer_paie_groupe).
    """

    periode: PeriodePaie
    resultats: List[ResultatPaie]
    totaux: TotauxPaieGroupe
    synthese_par_statut: List[SyntheseParStatut]
    erreurs: Dict[int, str] = field(default_factory=dict)
    date_generation: str = ""


def _enseignants_avec_donnees(periode_id: int, db_path: DbPath = None) -> List[int]:
    """
    Liste triée des identifiants d'enseignants ayant au moins une
    donnée de paie saisie (heures, rémunération ou retenue) pour la
    période — lecture seule, réutilise les services de lecture déjà
    existants des modules 02-04.
    """
    heures = heures_service.lister_heures_periode(periode_id, db_path=db_path)
    remuneration = remuneration_service.lister_remuneration_periode(periode_id, db_path=db_path)
    retenues = retenue_service.lister_retenues_periode(periode_id, db_path=db_path)
    return sorted(set(heures) | set(remuneration) | set(retenues))


def _construire_synthese_par_statut(resultats: List[ResultatPaie]) -> List[SyntheseParStatut]:
    """
    Agrège (nombre, total net) par statut d'enseignant. Pure
    agrégation de valeurs déjà calculées par le moteur de paie —
    aucune formule de paie n'est recalculée ici.
    """
    groupes: Dict[StatutEnseignant, List[ResultatPaie]] = {}
    for resultat in resultats:
        groupes.setdefault(resultat.statut, []).append(resultat)

    return [
        SyntheseParStatut(
            statut=statut,
            nombre=len(items),
            total_net=sum(item.net_a_percevoir for item in items),
        )
        for statut, items in sorted(groupes.items(), key=lambda paire: paire[0].value)
    ]


def preparer_etat_comptable(
    periode_id: int,
    enseignant_ids: Optional[List[int]] = None,
    db_path: DbPath = None,
) -> EtatComptablePeriode:
    """
    Prépare l'état comptable complet d'une période.

    Étapes (aucune n'implique de calcul de paie ici) :
    1. Vérifie que la période existe et n'est pas en BROUILLON.
    2. Détermine les enseignants concernés (tous ceux ayant des
       données de paie sur la période, sauf si `enseignant_ids` est
       fourni explicitement).
    3. Demande à paie_service.calculer_paie_groupe() les résultats.
    4. Agrège les totaux et la synthèse par statut à partir de CES
       résultats déjà calculés.

    Lève ComptabiliteError si la période est introuvable, encore en
    BROUILLON, si aucun enseignant n'est disponible, ou si aucun
    résultat n'a pu être calculé.
    """
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise ComptabiliteError(f"Aucune période avec l'id {periode_id}.")

    if periode.statut == StatutPeriode.BROUILLON:
        raise ComptabiliteError(
            "Cette période est encore au statut Brouillon : elle n'est pas prête pour un état comptable."
        )

    if enseignant_ids is None:
        enseignant_ids = _enseignants_avec_donnees(periode_id, db_path=db_path)

    if not enseignant_ids:
        raise ComptabiliteError("Aucun enseignant disponible pour cette période.")

    groupe = calculer_paie_groupe(periode_id, enseignant_ids, db_path=db_path)

    if not groupe.resultats:
        raise ComptabiliteError(
            "Aucun résultat de paie n'a pu être calculé pour cette période "
            "(données manquantes ou enseignants introuvables)."
        )

    resultats_tries = sorted(groupe.resultats, key=lambda r: (r.nom, r.prenom))

    return EtatComptablePeriode(
        periode=periode,
        resultats=resultats_tries,
        totaux=calculer_totaux_groupe(resultats_tries),
        synthese_par_statut=_construire_synthese_par_statut(resultats_tries),
        erreurs=groupe.erreurs,
        date_generation=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
