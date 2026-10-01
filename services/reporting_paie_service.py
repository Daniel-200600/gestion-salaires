"""
Service de reporting comptable et financier de la paie (module 13).

Centralise TOUS les calculs de reporting/rapprochement : les pages
Streamlit n'exécutent ici aucune agrégation ni vérification
arithmétique elles-mêmes. Réutilise exclusivement des données déjà
calculées par services/paie_service.py (via
services/comptabilite_service.preparer_etat_comptable) et des
agrégations déjà écrites par services/dashboard_service.py et
services/historique_paie_service.py — AUCUNE formule de paie n'est
recalculée ici : le rapprochement compare des valeurs déjà produites
entre elles, il ne dérive jamais une valeur depuis les données brutes
(heures, taux) une seconde fois.

Ce module est strictement EN LECTURE : aucune fonction ici n'écrit de
donnée de paie, quel que soit le statut de la période (une période
clôturée reste donc automatiquement protégée, par construction).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Union

from models.enums import Sexe, StatutEnseignant
from models.periode_paie import PeriodePaie
from models.resultat_paie import ResultatPaie
from services.comptabilite_service import EtatComptablePeriode, preparer_etat_comptable
from services.historique_paie_service import ComparaisonPeriodes
from utils.formatters import libelle_sexe, libelle_statut

DbPath = Optional[Union[str, Path]]

# Seuil par défaut (documenté, configurable) au-delà duquel une
# variation entre deux périodes est signalée comme notable (section 14).
# Exprimé en points de pourcentage.
SEUIL_VARIATION_NOTABLE_POURCENT = 10.0


# ---------------------------------------------------------------------
# Synthèse détaillée par groupe (statut / sexe) — section 10/11
# ---------------------------------------------------------------------

@dataclass
class SyntheseDetailleeGroupe:
    """
    Agrégat descriptif COMPLET (toutes les composantes de paie) pour un
    groupe d'enseignants déjà calculés — pure somme de valeurs
    existantes, jamais une formule recalculée.
    """

    libelle: str
    nombre: int
    total_heures: float = 0.0
    total_gain_heures: int = 0
    total_prime_ap_pp: int = 0
    total_surveillance_secretariat: int = 0
    total_indemnite_suggestion_admin: int = 0
    total_base_taxable: int = 0
    total_taxe: int = 0
    total_retenue_amicale: int = 0
    total_dette: int = 0
    total_net: int = 0


def _synthese_detaillee_par_cle(resultats: List[ResultatPaie], cle) -> List[SyntheseDetailleeGroupe]:
    groupes: Dict[str, List[ResultatPaie]] = {}
    for resultat in resultats:
        groupes.setdefault(cle(resultat), []).append(resultat)

    return [
        SyntheseDetailleeGroupe(
            libelle=libelle,
            nombre=len(items),
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


def synthese_detaillee_par_statut(resultats: List[ResultatPaie]) -> List[SyntheseDetailleeGroupe]:
    """Synthèse complète Permanent/Vacataire (section 10)."""
    return _synthese_detaillee_par_cle(resultats, cle=lambda r: libelle_statut(r.statut))


def synthese_detaillee_par_sexe(resultats: List[ResultatPaie]) -> List[SyntheseDetailleeGroupe]:
    """Synthèse complète par sexe (section 11) — purement descriptive."""
    return _synthese_detaillee_par_cle(resultats, cle=lambda r: libelle_sexe(r.sexe))


# ---------------------------------------------------------------------
# Rapprochement mathématique — sections 6, 7, 8, 9
# ---------------------------------------------------------------------

class StatutRapprochement(str, Enum):
    OK = "OK"
    ECART = "ÉCART"
    ERREUR = "ERREUR"


@dataclass
class LigneRapprochement:
    """Une ligne de contrôle : compare un montant attendu (recomposé) à un montant enregistré."""

    element: str
    montant_attendu: int
    montant_enregistre: int
    ecart: int
    statut: StatutRapprochement


def _ligne_rapprochement(element: str, attendu: int, enregistre: int) -> LigneRapprochement:
    ecart = enregistre - attendu
    statut = StatutRapprochement.OK if ecart == 0 else StatutRapprochement.ECART
    return LigneRapprochement(
        element=element, montant_attendu=attendu, montant_enregistre=enregistre, ecart=ecart, statut=statut
    )


@dataclass
class RapportRapprochementEnseignant:
    """
    Rapprochement individuel : vérifie que les valeurs déjà produites
    par paie_service sont cohérentes ENTRE ELLES (base_taxable = somme
    des gains ; net = base_taxable - retenues). Ne recalcule jamais
    gain_heures ou taxe_5 depuis les heures/taux — cette vérification
    porte uniquement sur l'ADDITION/SOUSTRACTION de valeurs déjà
    calculées, jamais sur leur dérivation depuis les données brutes.
    """

    enseignant_id: int
    nom: str
    prenom: str
    lignes: List[LigneRapprochement] = field(default_factory=list)

    @property
    def toutes_ok(self) -> bool:
        return all(ligne.statut == StatutRapprochement.OK for ligne in self.lignes)


def rapprocher_enseignant(resultat: ResultatPaie) -> RapportRapprochementEnseignant:
    """
    Contrôle mathématique d'un résultat déjà calculé (section 6/8) :

        Gain + AP/PP + Surveillance/Secrétariat + Indemnité = Base taxable
        Base taxable - Taxe - Retenue amicale - Dette = Net à payer
    """
    base_taxable_attendue = (
        resultat.gain_heures + resultat.prime_ap_pp
        + resultat.surveillance_secretariat + resultat.indemnite_suggestion_admin
    )
    net_attendu = resultat.base_taxable - resultat.taxe_5 - resultat.retenue_amicale - resultat.dette

    lignes = [
        _ligne_rapprochement(
            "Base taxable (Gain + AP/PP + Surveillance + Indemnité)", base_taxable_attendue, resultat.base_taxable
        ),
        _ligne_rapprochement(
            "Net à payer (Base taxable - Taxe - Retenue amicale - Dette)", net_attendu, resultat.net_a_percevoir
        ),
    ]
    return RapportRapprochementEnseignant(
        enseignant_id=resultat.enseignant_id, nom=resultat.nom, prenom=resultat.prenom, lignes=lignes
    )


@dataclass
class RapportRapprochementGlobal:
    """Rapprochement de période (section 9) : somme des lignes individuelles vs totaux affichés."""

    periode_id: int
    lignes: List[LigneRapprochement] = field(default_factory=list)

    @property
    def toutes_ok(self) -> bool:
        return all(ligne.statut == StatutRapprochement.OK for ligne in self.lignes)


def rapprocher_periode(etat: EtatComptablePeriode) -> RapportRapprochementGlobal:
    """
    Vérifie que chaque total affiché correspond exactement à la somme
    des lignes individuelles de la période (section 9). `etat.totaux`
    provient déjà de paie_service.calculer_totaux_groupe : ce
    rapprochement ne fait que comparer deux sommes déjà produites,
    sans en recalculer aucune.
    """
    resultats = etat.resultats
    lignes = [
        _ligne_rapprochement(
            "Total heures", int(round(sum(r.total_heures for r in resultats))), int(round(etat.totaux.total_heures))
        ),
        _ligne_rapprochement("Total gains", sum(r.gain_heures for r in resultats), etat.totaux.total_gain_heures),
        _ligne_rapprochement("Total AP/PP", sum(r.prime_ap_pp for r in resultats), etat.totaux.total_prime_ap_pp),
        _ligne_rapprochement(
            "Total surveillance/secrétariat",
            sum(r.surveillance_secretariat for r in resultats), etat.totaux.total_surveillance_secretariat,
        ),
        _ligne_rapprochement(
            "Total indemnités",
            sum(r.indemnite_suggestion_admin for r in resultats), etat.totaux.total_indemnite_suggestion_admin,
        ),
        _ligne_rapprochement("Total taxe", sum(r.taxe_5 for r in resultats), etat.totaux.total_taxe),
        _ligne_rapprochement(
            "Total retenue amicale", sum(r.retenue_amicale for r in resultats), etat.totaux.total_retenue_amicale
        ),
        _ligne_rapprochement("Total dettes", sum(r.dette for r in resultats), etat.totaux.total_dette),
        _ligne_rapprochement(
            "Total net à payer", sum(r.net_a_percevoir for r in resultats), etat.totaux.total_net_a_percevoir
        ),
    ]
    return RapportRapprochementGlobal(periode_id=etat.periode.id, lignes=lignes)


# ---------------------------------------------------------------------
# Classement des enseignants — section 12
# ---------------------------------------------------------------------

CRITERES_CLASSEMENT = {
    "gain": lambda r: r.gain_heures,
    "base_taxable": lambda r: r.base_taxable,
    "net_a_percevoir": lambda r: r.net_a_percevoir,
    "total_heures": lambda r: r.total_heures,
}


def classer_enseignants(resultats: List[ResultatPaie], critere: str, decroissant: bool = True) -> List[ResultatPaie]:
    """
    Retourne une NOUVELLE liste triée selon `critere`
    ("gain"/"base_taxable"/"net_a_percevoir"/"total_heures") — purement
    informatif, ne modifie jamais `resultats` ni aucune donnée.
    """
    if critere not in CRITERES_CLASSEMENT:
        raise ValueError(f"Critère de classement inconnu : {critere!r} (attendu : {list(CRITERES_CLASSEMENT)}).")
    return sorted(resultats, key=CRITERES_CLASSEMENT[critere], reverse=decroissant)


def filtrer_resultats(
    resultats: List[ResultatPaie],
    statut: Optional[StatutEnseignant] = None,
    sexe: Optional[Sexe] = None,
) -> List[ResultatPaie]:
    """
    Filtre des résultats déjà calculés par statut et/ou sexe (section 26)
    — les filtres se combinent (ET logique). Ne modifie jamais
    `resultats` et ne recalcule rien : pure sélection sur des champs
    déjà présents sur chaque ResultatPaie.
    """
    filtres = resultats
    if statut is not None:
        filtres = [r for r in filtres if r.statut == statut]
    if sexe is not None:
        filtres = [r for r in filtres if r.sexe == sexe]
    return filtres


# ---------------------------------------------------------------------
# État des retenues — section 18
# ---------------------------------------------------------------------

@dataclass
class LigneRetenue:
    nom: str
    prenom: str
    taxe: int
    retenue_amicale: int
    dette: int
    total_retenues: int
    net: int


def etat_retenues(resultats: List[ResultatPaie]) -> List[LigneRetenue]:
    """Une ligne par enseignant, focalisée sur les retenues (section 18). Pure lecture, aucun recalcul."""
    return [
        LigneRetenue(
            nom=r.nom, prenom=r.prenom, taxe=r.taxe_5, retenue_amicale=r.retenue_amicale, dette=r.dette,
            total_retenues=r.taxe_5 + r.retenue_amicale + r.dette, net=r.net_a_percevoir,
        )
        for r in resultats
    ]


# ---------------------------------------------------------------------
# Comparaison entre périodes — section 13/14 (réutilise le module 12)
# ---------------------------------------------------------------------

def analyser_variations(
    comparaison: ComparaisonPeriodes, seuil_pourcent: float = SEUIL_VARIATION_NOTABLE_POURCENT
) -> List[str]:
    """
    Identifie automatiquement les évolutions notables (section 14) —
    seuil explicite et configurable (`seuil_pourcent`, par défaut
    `SEUIL_VARIATION_NOTABLE_POURCENT` = 10 %), jamais une valeur
    arbitraire non documentée. Ne fait que lire des écarts déjà
    calculés par `historique_paie_service.comparer_periodes`.
    """
    observations: List[str] = []
    for indicateur in comparaison.indicateurs:
        pourcentage = indicateur.variation_pourcentage
        if pourcentage is None:
            if indicateur.variation_absolue != 0:
                observations.append(
                    f"{indicateur.libelle} : valeur de référence nulle sur la période A "
                    f"(variation non exprimable en pourcentage)."
                )
            continue
        if abs(pourcentage) >= seuil_pourcent:
            direction = "Hausse" if pourcentage > 0 else "Baisse"
            observations.append(f"{direction} notable de « {indicateur.libelle} » : {pourcentage:+.1f} %.")
    return observations


# ---------------------------------------------------------------------
# État de paie complet — section 15
# ---------------------------------------------------------------------

@dataclass
class EtatPaieComplet:
    """Rapport synthétique complet d'une période (section 15), assemblant tous les états ci-dessus."""

    etablissement: str
    periode: PeriodePaie
    date_generation: str
    utilisateur: Optional[str]
    etat_comptable: EtatComptablePeriode
    synthese_statut: List[SyntheseDetailleeGroupe]
    synthese_sexe: List[SyntheseDetailleeGroupe]
    retenues: List[LigneRetenue]
    rapprochement: RapportRapprochementGlobal
    observations: List[str] = field(default_factory=list)


def construire_etat_paie_complet(
    periode_id: int,
    etablissement: str = "Établissement scolaire",
    utilisateur: Optional[str] = None,
    enseignant_ids: Optional[List[int]] = None,
    db_path: DbPath = None,
) -> EtatPaieComplet:
    """
    Assemble l'état de paie complet d'une période (section 15) à
    partir exclusivement des états déjà produits ci-dessus — aucun
    nouveau calcul de paie.
    """
    etat = preparer_etat_comptable(periode_id, enseignant_ids=enseignant_ids, db_path=db_path)
    rapprochement = rapprocher_periode(etat)

    observations: List[str] = []
    if not rapprochement.toutes_ok:
        lignes_en_ecart = [l.element for l in rapprochement.lignes if l.statut != StatutRapprochement.OK]
        observations.append(f"Écart(s) détecté(s) sur : {', '.join(lignes_en_ecart)}.")
    if etat.erreurs:
        observations.append(f"{len(etat.erreurs)} enseignant(s) n'ont pas pu être calculés.")
    if not observations:
        observations.append("Aucune anomalie détectée. Rapprochement conforme (écart 0 FCFA).")

    return EtatPaieComplet(
        etablissement=etablissement,
        periode=etat.periode,
        date_generation=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        utilisateur=utilisateur,
        etat_comptable=etat,
        synthese_statut=synthese_detaillee_par_statut(etat.resultats),
        synthese_sexe=synthese_detaillee_par_sexe(etat.resultats),
        retenues=etat_retenues(etat.resultats),
        rapprochement=rapprochement,
        observations=observations,
    )
