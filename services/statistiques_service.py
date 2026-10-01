"""
Service central de statistiques avancées (module 17).

Réutilise exclusivement les services déjà existants pour obtenir les
données de base — AUCUNE formule de paie, de reporting, de contrôle
ou de diagnostic n'est recalculée ici :

    services/comptabilite_service.py    -> résultats de paie déjà calculés
    services/reporting_paie_service.py  -> synthèses par groupe, filtres, classement
    services/historique_paie_service.py -> historique multi-périodes d'un enseignant

Ce module ajoute exclusivement des capacités STATISTIQUES qui
n'existaient pas encore : statistique descriptive (moyenne, médiane,
écart-type, quartiles), détection d'outliers (méthode IQR), analyse
de tendance multi-périodes, et croisement à deux dimensions
(statut × sexe). Indépendant de Streamlit.
"""

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from models.enums import Sexe, StatutEnseignant
from models.periode_paie import PeriodePaie
from models.resultat_paie import ResultatPaie
from services.comptabilite_service import ComptabiliteError, EtatComptablePeriode, preparer_etat_comptable
from services.reporting_paie_service import SyntheseDetailleeGroupe
from utils.formatters import libelle_sexe, libelle_statut

DbPath = Optional[Union[str, Path]]


# ---------------------------------------------------------------------
# Statistique descriptive — robuste à 0/1 observation (section 10/21)
# ---------------------------------------------------------------------

@dataclass
class StatistiqueDescriptive:
    """Résumé statistique d'une série de valeurs. Toujours calculable, même avec 0 ou 1 observation."""

    nombre: int = 0
    total: float = 0.0
    moyenne: Optional[float] = None
    mediane: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    ecart_type: Optional[float] = None  # None si < 2 observations (non défini)
    premier_quartile: Optional[float] = None
    troisieme_quartile: Optional[float] = None


def calculer_statistique_descriptive(valeurs: List[float]) -> StatistiqueDescriptive:
    """
    Calcule moyenne/médiane/écart-type/quartiles sur une série de
    valeurs. Ne lève jamais d'exception : une liste vide retourne une
    statistique à zéro observation, une seule valeur retourne un
    écart-type et des quartiles à None (non mathématiquement définis).
    """
    if not valeurs:
        return StatistiqueDescriptive(nombre=0, total=0.0)

    resultat = StatistiqueDescriptive(
        nombre=len(valeurs), total=sum(valeurs), moyenne=statistics.mean(valeurs),
        mediane=statistics.median(valeurs), minimum=min(valeurs), maximum=max(valeurs),
    )
    if len(valeurs) >= 2:
        resultat.ecart_type = statistics.stdev(valeurs)
    if len(valeurs) >= 4:
        q1, _, q3 = statistics.quantiles(valeurs, n=4, method="inclusive")
        resultat.premier_quartile = q1
        resultat.troisieme_quartile = q3
    return resultat


# ---------------------------------------------------------------------
# Statistiques générales d'une période (section 6)
# ---------------------------------------------------------------------

@dataclass
class StatistiquesGenerales:
    periode: PeriodePaie
    nombre_enseignants_total: int
    nombre_enseignants_actifs: int
    nombre_enseignants_inactifs: int
    nombre_vacataires: int
    nombre_permanents: int
    nombre_hommes: int
    nombre_femmes: int
    heures: StatistiqueDescriptive
    taux_horaire: StatistiqueDescriptive
    remuneration_nette: StatistiqueDescriptive
    masse_salariale_brute: int
    total_taxe: int
    total_retenue_amicale: int
    total_dette: int
    total_net: int


def statistiques_generales(periode_id: int, db_path: DbPath = None) -> StatistiquesGenerales:
    """
    Assemble les statistiques générales d'une période (section 6),
    à partir des résultats déjà calculés par
    comptabilite_service.preparer_etat_comptable — aucun recalcul.

    Si la période ne contient encore aucune donnée de paie exploitable
    (ComptabiliteError), retourne des statistiques à zéro observation
    plutôt que de propager l'exception (section 21) — les effectifs
    d'enseignants restent néanmoins calculés normalement.
    """
    from database.repositories import enseignant_repository
    from services import periode_service

    tous_enseignants = enseignant_repository.lister(inclure_inactifs=True, db_path=db_path)
    actifs = [e for e in tous_enseignants if e.actif]

    try:
        etat = preparer_etat_comptable(periode_id, db_path=db_path)
        resultats = etat.resultats
        periode = etat.periode
    except ComptabiliteError:
        periode = periode_service.obtenir_periode(periode_id, db_path=db_path)
        resultats = []

    return StatistiquesGenerales(
        periode=periode,
        nombre_enseignants_total=len(tous_enseignants),
        nombre_enseignants_actifs=len(actifs),
        nombre_enseignants_inactifs=len(tous_enseignants) - len(actifs),
        nombre_vacataires=sum(1 for e in tous_enseignants if e.statut == StatutEnseignant.VACATAIRE),
        nombre_permanents=sum(1 for e in tous_enseignants if e.statut == StatutEnseignant.PERMANENT),
        nombre_hommes=sum(1 for e in tous_enseignants if e.sexe == Sexe.HOMME),
        nombre_femmes=sum(1 for e in tous_enseignants if e.sexe == Sexe.FEMME),
        heures=calculer_statistique_descriptive([r.total_heures for r in resultats]),
        taux_horaire=calculer_statistique_descriptive([r.taux_horaire for r in resultats]),
        remuneration_nette=calculer_statistique_descriptive([r.net_a_percevoir for r in resultats]),
        masse_salariale_brute=sum(
            r.gain_heures + r.prime_ap_pp + r.surveillance_secretariat + r.indemnite_suggestion_admin
            for r in resultats
        ),
        total_taxe=sum(r.taxe_5 for r in resultats),
        total_retenue_amicale=sum(r.retenue_amicale for r in resultats),
        total_dette=sum(r.dette for r in resultats),
        total_net=sum(r.net_a_percevoir for r in resultats),
    )


# ---------------------------------------------------------------------
# Croisement statut × sexe (section 7) — nouvelle capacité, pas dans reporting_paie_service
# ---------------------------------------------------------------------

def synthese_croisee_statut_sexe(resultats: List[ResultatPaie]) -> List[SyntheseDetailleeGroupe]:
    """
    Croisement à deux dimensions (statut × sexe), absent de
    reporting_paie_service.py (qui ne propose qu'un seul axe à la
    fois). Réutilise la même structure SyntheseDetailleeGroupe.
    """
    groupes: Dict[str, List[ResultatPaie]] = {}
    for r in resultats:
        cle = f"{libelle_statut(r.statut)} — {libelle_sexe(r.sexe)}"
        groupes.setdefault(cle, []).append(r)

    return [
        SyntheseDetailleeGroupe(
            libelle=libelle, nombre=len(items),
            total_heures=sum(r.total_heures for r in items),
            total_gain_heures=sum(r.gain_heures for r in items),
            total_prime_ap_pp=sum(r.prime_ap_pp for r in items),
            total_surveillance_secretariat=sum(r.surveillance_secretariat for r in items),
            total_indemnite_suggestion_admin=sum(r.indemnite_suggestion_admin for r in items),
            total_base_taxable=sum(r.base_taxable for r in items),
            total_taxe=sum(r.taxe_5 for r in items),
            total_retenue_amicale=sum(r.retenue_amicale for r in items),
            total_dette=sum(r.dette for r in items),
            total_net=sum(r.net_a_percevoir for r in items),
        )
        for libelle, items in sorted(groupes.items())
    ]


# ---------------------------------------------------------------------
# Analyse des composantes de la paie (section 9)
# ---------------------------------------------------------------------

@dataclass
class ComposantePaie:
    libelle: str
    montant_total: int
    part_pourcentage: Optional[float]  # None si le total de référence est nul


def analyser_composantes(resultats: List[ResultatPaie]) -> List[ComposantePaie]:
    """
    Décompose la masse salariale brute par composante (section 9) et
    calcule la part de chacune — jamais de division par zéro (part
    laissée à None si le brut total est nul).
    """
    composantes_brutes = {
        "Gain horaire": sum(r.gain_heures for r in resultats),
        "AP/PP": sum(r.prime_ap_pp for r in resultats),
        "Surveillance/secrétariat": sum(r.surveillance_secretariat for r in resultats),
        "Indemnité suggestion/admin": sum(r.indemnite_suggestion_admin for r in resultats),
    }
    total_brut = sum(composantes_brutes.values())

    return [
        ComposantePaie(
            libelle=libelle, montant_total=montant,
            part_pourcentage=(montant / total_brut * 100) if total_brut > 0 else None,
        )
        for libelle, montant in composantes_brutes.items()
    ]


# ---------------------------------------------------------------------
# Analyse multi-périodes / évolution (section 8)
# ---------------------------------------------------------------------

@dataclass
class PointPeriode:
    periode: PeriodePaie
    nombre_enseignants: int
    heures_totales: float
    taux_horaire_moyen: Optional[float]
    masse_salariale_brute: int
    total_net: int
    total_taxe: int
    total_retenues: int
    total_dettes: int
    variation_net_absolue: Optional[int] = None
    variation_net_pourcentage: Optional[float] = None


def analyser_periodes(periode_ids: List[int], db_path: DbPath = None) -> List[PointPeriode]:
    """
    Analyse d'évolution sur plusieurs périodes (section 8), triées
    chronologiquement. Chaque point réutilise
    comptabilite_service.preparer_etat_comptable (aucun recalcul de
    paie). Les périodes sans donnée exploitable sont incluses avec
    des totaux à zéro plutôt que provoquer une erreur — jamais de
    division par zéro pour la variation.
    """
    from services import periode_service

    points: List[PointPeriode] = []
    for periode_id in periode_ids:
        try:
            etat = preparer_etat_comptable(periode_id, db_path=db_path)
            resultats = etat.resultats
            point = PointPeriode(
                periode=etat.periode, nombre_enseignants=len(resultats),
                heures_totales=etat.totaux.total_heures,
                taux_horaire_moyen=(
                    statistics.mean([r.taux_horaire for r in resultats]) if resultats else None
                ),
                masse_salariale_brute=etat.totaux.total_gain_heures + etat.totaux.total_primes,
                total_net=etat.totaux.total_net_a_percevoir, total_taxe=etat.totaux.total_taxe,
                total_retenues=etat.totaux.total_retenue_amicale, total_dettes=etat.totaux.total_dette,
            )
        except ComptabiliteError:
            periode = periode_service.obtenir_periode(periode_id, db_path=db_path)
            point = PointPeriode(
                periode=periode, nombre_enseignants=0, heures_totales=0.0, taux_horaire_moyen=None,
                masse_salariale_brute=0, total_net=0, total_taxe=0, total_retenues=0, total_dettes=0,
            )
        points.append(point)

    points.sort(key=lambda p: (p.periode.annee, p.periode.mois))

    for i in range(1, len(points)):
        precedent, actuel = points[i - 1], points[i]
        actuel.variation_net_absolue = actuel.total_net - precedent.total_net
        if precedent.total_net != 0:
            actuel.variation_net_pourcentage = (actuel.variation_net_absolue / precedent.total_net) * 100

    return points


# ---------------------------------------------------------------------
# Détection de valeurs atypiques — méthode IQR (section 11)
# ---------------------------------------------------------------------

@dataclass
class ValeurAtypique:
    """
    Une observation signalée comme statistiquement atypique —
    terminologie volontairement prudente : ceci n'est PAS un jugement
    d'erreur métier, seulement une invitation à vérifier.
    """

    enseignant_id: int
    nom: str
    prenom: str
    champ: str
    valeur: float
    borne_basse: float
    borne_haute: float
    niveau: str = "À vérifier"


def detecter_valeurs_atypiques(resultats: List[ResultatPaie], champ: str) -> List[ValeurAtypique]:
    """
    Détection IQR (section 11) : Q1, Q3, IQR = Q3-Q1, bornes à
    1,5×IQR. Nécessite au moins 4 observations pour un calcul de
    quartiles significatif (statistics.quantiles) — retourne une
    liste vide sinon plutôt que de signaler des faux positifs sur des
    données insuffisantes.
    """
    champs_valides = {
        "total_heures": lambda r: r.total_heures, "taux_horaire": lambda r: r.taux_horaire,
        "net_a_percevoir": lambda r: r.net_a_percevoir, "gain_heures": lambda r: r.gain_heures,
    }
    if champ not in champs_valides:
        raise ValueError(f"Champ inconnu pour la détection d'outliers : {champ!r}.")
    extracteur = champs_valides[champ]

    if len(resultats) < 4:
        return []

    valeurs = [extracteur(r) for r in resultats]
    q1, _, q3 = statistics.quantiles(valeurs, n=4, method="inclusive")
    iqr = q3 - q1
    borne_basse = q1 - 1.5 * iqr
    borne_haute = q3 + 1.5 * iqr

    return [
        ValeurAtypique(
            enseignant_id=r.enseignant_id, nom=r.nom, prenom=r.prenom, champ=champ,
            valeur=extracteur(r), borne_basse=borne_basse, borne_haute=borne_haute,
        )
        for r in resultats
        if extracteur(r) < borne_basse or extracteur(r) > borne_haute
    ]


# ---------------------------------------------------------------------
# Analyse individuelle (section 12) — réutilise historique_paie_service
# ---------------------------------------------------------------------

@dataclass
class EcartIndividuel:
    libelle: str
    valeur_enseignant: float
    valeur_groupe: float
    ecart_absolu: float
    ecart_pourcentage: Optional[float]  # None si la référence du groupe est nulle


def comparer_enseignant_au_groupe(
    resultat: ResultatPaie, resultats_groupe: List[ResultatPaie]
) -> List[EcartIndividuel]:
    """
    Compare un enseignant à la moyenne de son groupe (section 12).
    Jamais de division par zéro : `ecart_pourcentage` reste None si
    la moyenne du groupe est nulle.
    """
    if not resultats_groupe:
        return []

    champs = [
        ("Heures", lambda r: r.total_heures), ("Taux horaire", lambda r: r.taux_horaire),
        ("Gain", lambda r: r.gain_heures), ("Net à payer", lambda r: r.net_a_percevoir),
    ]
    ecarts = []
    for libelle, extracteur in champs:
        moyenne_groupe = statistics.mean([extracteur(r) for r in resultats_groupe])
        valeur_ens = extracteur(resultat)
        ecart_absolu = valeur_ens - moyenne_groupe
        ecart_pct = (ecart_absolu / moyenne_groupe * 100) if moyenne_groupe != 0 else None
        ecarts.append(EcartIndividuel(libelle, valeur_ens, moyenne_groupe, ecart_absolu, ecart_pct))
    return ecarts
