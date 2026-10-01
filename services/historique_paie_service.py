"""
Service historique de paie (module 08).

Consultation en lecture seule de l'historique de paie d'un enseignant
à travers plusieurs périodes. RÈGLE ABSOLUE (identique à
services/dashboard_service.py) : ce module ne recalcule JAMAIS
gain_heures, taxe_5 ou net_a_percevoir — il réutilise exclusivement
services/paie_service.py, période par période.

Aucune dépendance à Streamlit. Aucune écriture en base : toutes les
fonctions de ce module sont des lectures pures. Une période clôturée
ne peut donc, par construction, jamais être modifiée depuis ce
service (Contrôle 4 du module 08) : aucune fonction d'écriture n'existe
ici.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from models.periode_paie import PeriodePaie
from models.resultat_paie import ResultatPaie
from services.comptabilite_service import ComptabiliteError, preparer_etat_comptable
from services.paie_service import CalculPaieError, TotauxPaieGroupe, calculer_paie_enseignant, calculer_totaux_groupe
from services.periode_service import PeriodeNotFoundError, lister_periodes, obtenir_periode

DbPath = Optional[Union[str, Path]]


@dataclass
class LigneHistorique:
    """Un point de l'historique : le résultat de paie déjà calculé pour une période donnée."""

    periode_id: int
    libelle_periode: str
    resultat: ResultatPaie


def _resultat_est_vide(resultat: ResultatPaie) -> bool:
    """Vrai si l'enseignant n'a strictement aucune donnée sur cette période (aucune saisie effectuée)."""
    return (
        resultat.total_heures == 0
        and resultat.prime_ap_pp == 0
        and resultat.surveillance_secretariat == 0
        and resultat.indemnite_suggestion_admin == 0
        and resultat.retenue_amicale == 0
        and resultat.dette == 0
    )


def historique_enseignant(
    enseignant_id: int,
    periode_ids: Optional[List[int]] = None,
    inclure_periodes_sans_donnees: bool = False,
    db_path: DbPath = None,
) -> List[LigneHistorique]:
    """
    Retourne l'historique de paie d'un enseignant, trié chronologiquement
    (année puis mois).

    - `periode_ids=None` (par défaut) : parcourt TOUTES les périodes
      existantes.
    - `periode_ids=[...]` : limite la consultation aux périodes
      indiquées (sélection d'une ou plusieurs périodes).
    - Les périodes non exploitables pour ce calcul (BROUILLON, ou
      période/enseignant introuvable) sont silencieusement ignorées :
      un historique n'exige pas la complétude, il reflète ce qui est
      réellement disponible.
    - Par défaut, les périodes où l'enseignant n'a aucune donnée
      saisie sont également omises (`inclure_periodes_sans_donnees=True`
      pour les voir apparaître avec des valeurs à zéro).
    """
    toutes_periodes = {p.id: p for p in lister_periodes(db_path=db_path)}

    if periode_ids is None:
        cibles = sorted(toutes_periodes.values(), key=lambda p: (p.annee, p.mois))
    else:
        cibles = sorted(
            (toutes_periodes[pid] for pid in periode_ids if pid in toutes_periodes),
            key=lambda p: (p.annee, p.mois),
        )

    lignes: List[LigneHistorique] = []
    for periode in cibles:
        try:
            resultat = calculer_paie_enseignant(periode.id, enseignant_id, db_path=db_path)
        except CalculPaieError:
            continue  # période non exploitable (brouillon, enseignant introuvable...) : ignorée

        if not inclure_periodes_sans_donnees and _resultat_est_vide(resultat):
            continue

        lignes.append(LigneHistorique(periode_id=periode.id, libelle_periode=periode.libelle, resultat=resultat))

    return lignes


def totaux_historique(lignes: List[LigneHistorique]) -> TotauxPaieGroupe:
    """
    Agrège l'historique sur l'ensemble des périodes consultées.
    Réutilise directement paie_service.calculer_totaux_groupe (aucune
    duplication de la logique d'agrégation, déjà écrite et testée au
    module 05/06).
    """
    return calculer_totaux_groupe([ligne.resultat for ligne in lignes])


# ---------------------------------------------------------------------
# Comparaison entre deux périodes (module 09, section 20)
# ---------------------------------------------------------------------

@dataclass
class EcartIndicateur:
    """Un indicateur comparé entre deux périodes : valeurs brutes + écarts."""

    libelle: str
    valeur_a: float
    valeur_b: float

    @property
    def variation_absolue(self) -> float:
        return self.valeur_b - self.valeur_a

    @property
    def variation_pourcentage(self) -> Optional[float]:
        """None si la valeur de référence (période A) est nulle (pourcentage non défini)."""
        if self.valeur_a == 0:
            return None
        return (self.variation_absolue / self.valeur_a) * 100


@dataclass
class ComparaisonPeriodes:
    periode_a: PeriodePaie
    periode_b: PeriodePaie
    indicateurs: List[EcartIndicateur]


def comparer_periodes(periode_id_a: int, periode_id_b: int, db_path: DbPath = None) -> ComparaisonPeriodes:
    """
    Compare deux périodes sur les indicateurs globaux déjà calculés par
    services/comptabilite_service.py (masse salariale, heures, gains,
    taxe, retenues, dettes, net, nombre d'enseignants) — aucune formule
    de paie n'est recalculée ici, uniquement une différence entre deux
    totaux déjà produits.

    Lève ComptabiliteError si l'une des deux périodes n'a aucune
    donnée exploitable (même comportement que
    comptabilite_service.preparer_etat_comptable).
    """
    periode_a = obtenir_periode(periode_id_a, db_path=db_path)
    periode_b = obtenir_periode(periode_id_b, db_path=db_path)

    etat_a = preparer_etat_comptable(periode_id_a, db_path=db_path)
    etat_b = preparer_etat_comptable(periode_id_b, db_path=db_path)

    indicateurs = [
        EcartIndicateur("Nombre d'enseignants", len(etat_a.resultats), len(etat_b.resultats)),
        EcartIndicateur("Total heures", etat_a.totaux.total_heures, etat_b.totaux.total_heures),
        EcartIndicateur("Total gains", etat_a.totaux.total_gain_heures, etat_b.totaux.total_gain_heures),
        EcartIndicateur("Total taxe", etat_a.totaux.total_taxe, etat_b.totaux.total_taxe),
        EcartIndicateur("Total retenues", etat_a.totaux.total_retenues, etat_b.totaux.total_retenues),
        EcartIndicateur("Total dettes", etat_a.totaux.total_dette, etat_b.totaux.total_dette),
        EcartIndicateur("Total net à payer", etat_a.totaux.total_net_a_percevoir, etat_b.totaux.total_net_a_percevoir),
    ]

    return ComparaisonPeriodes(periode_a=periode_a, periode_b=periode_b, indicateurs=indicateurs)
