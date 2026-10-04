"""
Moteur de calcul de paie (module 05).

Service métier PUR : aucune dépendance à Streamlit, aux widgets, aux
pages, au HTML ou au CSS. Ne dépend que des repositories et modèles
existants (via les services de lecture des modules 02-04).

FORMULES (dans cet ordre)
--------------------------
1. Total heures      = semaine_1 + semaine_2 + semaine_3 + semaine_4 + semaine_5
2. Gain heures        = total_heures × taux_horaire
3. Base taxable        = gain_heures + prime_ap_pp + surveillance_secretariat
                          + indemnite_suggestion_admin
4. Taxe                 = base_taxable × taux de taxe de la période,
                          pour les VACATAIRES uniquement ; 0 pour un
                          permanent (periodes_paie.taux_taxe : 5,5 % par
                          défaut, config.settings.TAUX_TAXE ; paramétrable
                          par l'administrateur, figé à la validation — cf.
                          services/parametres_paie_service.py). Les périodes
                          validées avant la version 1.6.0 gardent l'ancienne
                          règle (periodes_paie.taxe_permanents = 1).
5. Net à percevoir      = base_taxable - taxe_5 - retenue_amicale - dette

PRÉCISION MONÉTAIRE
--------------------
Tous les calculs intermédiaires impliquant de l'argent sont effectués
en Decimal (jamais float). La conversion finale d'un Decimal vers
l'entier FCFA stocké/affiché utilise systématiquement
utils.money.arrondir_fcfa (arrondi commercial ROUND_HALF_UP,
documenté et testé dans utils/money.py) — jamais round() natif, jamais
un cast float.

SOURCE UNIQUE DE VÉRITÉ
-------------------------
Le total d'heures n'est jamais lu depuis une colonne stockée : il est
recalculé ici à partir des 5 saisies hebdomadaires individuelles
(mêmes données que heures_service.total_heures), exactement comme dans
le reste de l'application.

STATUT DE PÉRIODE
-------------------
- BROUILLON : le calcul est refusé (période pas encore prête).
- OUVERTE   : calcul autorisé, à titre de prévisualisation.
- VALIDEE   : calcul autorisé, en vue de la génération d'un bulletin.
- CLOTUREE  : calcul autorisé, sur des données figées (aucune donnée
              n'est modifiable pour une période clôturée — cf. triggers
              SQL du schéma — le calcul y est donc par nature toujours
              reproductible à l'identique).

Aucune donnée source n'est jamais modifiée par un calcul : ce moteur
n'effectue que des lectures (via les services des modules 02-04) et ne
persiste rien dans bulletins_paie — cette étape est hors périmètre du
module 05.

INDÉPENDANCE ET PERFORMANCE DU CALCUL GROUPÉ
-----------------------------------------------
`calculer_paie_groupe` appelle `calculer_paie_enseignant` pour chaque
enseignant, indépendamment. Aucun état mutable n'est partagé entre ces
appels (chaque résultat est un nouvel objet ResultatPaie construit à
partir de données fraîchement lues) : une erreur sur un enseignant ne
peut donc jamais corrompre le résultat d'un autre. Les erreurs
individuelles sont collectées séparément plutôt que d'interrompre tout
le groupe, ce qui est sûr ici car aucune écriture n'est effectuée
(contrairement à l'enregistrement groupé transactionnel du module 04).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Union

from config.settings import TAUX_TAXE
from database.repositories import enseignant_repository, periode_repository
from utils.validators import message_fiche_incomplete
from models.enums import StatutEnseignant, StatutPeriode
from models.resultat_paie import ResultatPaie
from services import heures_service, licence_service, remuneration_service, retenue_service
from utils.money import arrondir_fcfa

DbPath = Optional[Union[str, Path]]


class CalculPaieError(Exception):
    """
    Levée pour toute impossibilité de calculer la paie d'un enseignant :
    période introuvable, période au statut BROUILLON (pas encore prête
    pour un calcul), ou enseignant introuvable.
    """


@dataclass
class ResultatCalculGroupe:
    """
    Résultat d'un calcul groupé : les enseignants calculés avec succès
    d'un côté, les échecs individuels (par enseignant_id) de l'autre.
    Un échec sur un enseignant n'empêche jamais les autres de figurer
    dans `resultats`.
    """

    resultats: List[ResultatPaie] = field(default_factory=list)
    erreurs: Dict[int, str] = field(default_factory=dict)


@dataclass
class TotauxPaieGroupe:
    """
    Agrégats (sommes) d'un ensemble de ResultatPaie, pour affichage
    groupé (module 05) et exports comptables (module 06).

    Les champs `total_primes` et `total_retenues` restent des sommes
    combinées (pratiques pour un affichage synthétique) ; les champs
    détaillés par type ci-dessous sont nécessaires à la ligne TOTAL
    GÉNÉRAL de l'état comptable Excel, qui a une colonne par type.
    """

    total_heures: float = 0.0
    total_gain_heures: int = 0
    total_prime_ap_pp: int = 0
    total_surveillance_secretariat: int = 0
    total_indemnite_suggestion_admin: int = 0
    total_primes: int = 0
    total_taxe: int = 0
    total_retenue_amicale: int = 0
    total_dette: int = 0
    total_retenues: int = 0
    total_net_a_percevoir: int = 0


def _obtenir_periode_prete_ou_lever(periode_id: int, db_path: DbPath):
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise CalculPaieError(f"Aucune période avec l'id {periode_id}.")
    if periode.statut == StatutPeriode.BROUILLON:
        raise CalculPaieError(
            "Cette période est encore au statut Brouillon : elle n'est pas prête pour un "
            "calcul de paie (elle doit d'abord être ouverte)."
        )
    if periode.statut == StatutPeriode.OUVERTE:
        # Les périodes validées ou clôturées restent toujours consultables.
        try:
            licence_service.verifier_calcul_autorise(db_path=db_path)
        except licence_service.LicenceRequiseError as erreur:
            raise CalculPaieError(str(erreur)) from erreur
    return periode


def calculer_paie_enseignant(periode_id: int, enseignant_id: int, db_path: DbPath = None) -> ResultatPaie:
    """
    Calcule la paie d'UN enseignant pour UNE période et retourne un
    résultat structuré (ResultatPaie). Ne modifie aucune donnée
    source : lecture seule.

    Lève CalculPaieError si la période ou l'enseignant est introuvable,
    ou si la période est encore au statut BROUILLON.
    """
    periode = _obtenir_periode_prete_ou_lever(periode_id, db_path)

    enseignant = enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)
    if enseignant is None:
        raise CalculPaieError(f"Aucun enseignant avec l'id {enseignant_id}.")
    if not enseignant.est_complet:
        raise CalculPaieError(message_fiche_incomplete(enseignant))

    heures = heures_service.obtenir_heures_enseignant(periode_id, enseignant_id, db_path=db_path)
    remuneration = remuneration_service.obtenir_remuneration_enseignant(periode_id, enseignant_id, db_path=db_path)
    retenues = retenue_service.obtenir_retenues_enseignant(periode_id, enseignant_id, db_path=db_path)

    return _calculer_resultat(
        periode.id, enseignant, heures, remuneration, retenues,
        taux_taxe=periode.taux_taxe, taxe_permanents=periode.taxe_permanents,
    )


def _calculer_resultat(
    periode_id: int,
    enseignant,
    heures: Dict[int, float],
    remuneration: Dict[str, int],
    retenues: Dict[str, int],
    taux_taxe: Decimal = TAUX_TAXE,
    taxe_permanents: bool = False,
) -> ResultatPaie:
    """
    Applique les 5 formules officielles à des données déjà lues.
    Fonction pure : aucun accès base, aucun effet de bord, aucun état
    partagé — un nouvel objet est construit à chaque appel, garantissant
    l'indépendance totale entre enseignants lors d'un calcul groupé.
    """
    # 1. Total heures (Decimal, même source que heures_service : les 5 saisies hebdo)
    heures_par_semaine_decimal = {s: Decimal(str(heures.get(s, 0.0))) for s in range(1, 6)}
    total_heures_decimal = sum(heures_par_semaine_decimal.values())

    # 2. Gain par heures
    taux_horaire_decimal = Decimal(enseignant.taux_horaire)
    gain_heures_decimal = total_heures_decimal * taux_horaire_decimal
    gain_heures = arrondir_fcfa(gain_heures_decimal)

    prime_ap_pp = int(remuneration.get("prime_ap_pp", 0))
    surveillance_secretariat = int(remuneration.get("surveillance_secretariat", 0))
    indemnite_suggestion_admin = int(remuneration.get("indemnite_suggestion_admin", 0))

    # 3. Base taxable
    base_taxable_decimal = (
        Decimal(gain_heures)
        + Decimal(prime_ap_pp)
        + Decimal(surveillance_secretariat)
        + Decimal(indemnite_suggestion_admin)
    )
    base_taxable = arrondir_fcfa(base_taxable_decimal)

    # 4. Taxe (taux propre à la période ; 5,5 % par défaut = config.settings.TAUX_TAXE),
    #    due par les vacataires seulement (sauf ancienne règle d'une période validée).
    taux_taxe = Decimal(str(taux_taxe))
    if enseignant.statut != StatutEnseignant.VACATAIRE and not taxe_permanents:
        taux_taxe = Decimal("0")
    taxe_decimal = base_taxable_decimal * taux_taxe
    taxe_5 = arrondir_fcfa(taxe_decimal)

    retenue_amicale = int(retenues.get("retenue_amicale", 0))
    dette = int(retenues.get("dette", 0))

    # 5. Net à percevoir
    net_decimal = base_taxable_decimal - Decimal(taxe_5) - Decimal(retenue_amicale) - Decimal(dette)
    net_a_percevoir = arrondir_fcfa(net_decimal)

    return ResultatPaie(
        enseignant_id=enseignant.id,
        periode_id=periode_id,
        nom=enseignant.nom,
        prenom=enseignant.prenom,
        sexe=enseignant.sexe,
        statut=enseignant.statut,
        taux_horaire=enseignant.taux_horaire,
        semaine_1=float(heures_par_semaine_decimal[1]),
        semaine_2=float(heures_par_semaine_decimal[2]),
        semaine_3=float(heures_par_semaine_decimal[3]),
        semaine_4=float(heures_par_semaine_decimal[4]),
        semaine_5=float(heures_par_semaine_decimal[5]),
        total_heures=float(total_heures_decimal),
        gain_heures=gain_heures,
        prime_ap_pp=prime_ap_pp,
        surveillance_secretariat=surveillance_secretariat,
        indemnite_suggestion_admin=indemnite_suggestion_admin,
        base_taxable=base_taxable,
        taxe_5=taxe_5,
        retenue_amicale=retenue_amicale,
        dette=dette,
        net_a_percevoir=net_a_percevoir,
        taux_taxe=taux_taxe,
    )


def calculer_paie_groupe(
    periode_id: int, enseignant_ids: List[int], db_path: DbPath = None
) -> ResultatCalculGroupe:
    """
    Calcule la paie de PLUSIEURS enseignants pour une même période.

    Chaque enseignant est calculé indépendamment (aucun état mutable
    partagé) : une erreur sur l'un d'eux (enseignant introuvable, par
    exemple) est collectée dans `erreurs` sans empêcher le calcul des
    autres, qui apparaissent normalement dans `resultats`.

    Lève CalculPaieError uniquement si la période elle-même est
    introuvable ou encore en BROUILLON (condition préalable commune à
    tout le groupe, vérifiée une seule fois).
    """
    _obtenir_periode_prete_ou_lever(periode_id, db_path)  # vérifiée une fois pour tout le groupe

    resultats: List[ResultatPaie] = []
    erreurs: Dict[int, str] = {}

    for enseignant_id in enseignant_ids:
        try:
            resultats.append(calculer_paie_enseignant(periode_id, enseignant_id, db_path=db_path))
        except CalculPaieError as erreur:
            erreurs[enseignant_id] = str(erreur)

    return ResultatCalculGroupe(resultats=resultats, erreurs=erreurs)


def calculer_totaux_groupe(resultats: List[ResultatPaie]) -> TotauxPaieGroupe:
    """
    Agrège (somme) une liste de ResultatPaie déjà calculés — utilisé
    pour l'affichage des totaux globaux dans pages/4_Calcul_Paie.py.

    Fonction pure de PRÉSENTATION : elle ne recalcule aucune formule de
    paie, elle additionne des montants déjà produits par
    `calculer_paie_enseignant`.
    """
    if not resultats:
        return TotauxPaieGroupe()

    total_prime_ap_pp = sum(r.prime_ap_pp for r in resultats)
    total_surveillance_secretariat = sum(r.surveillance_secretariat for r in resultats)
    total_indemnite_suggestion_admin = sum(r.indemnite_suggestion_admin for r in resultats)
    total_retenue_amicale = sum(r.retenue_amicale for r in resultats)
    total_dette = sum(r.dette for r in resultats)

    return TotauxPaieGroupe(
        total_heures=sum(r.total_heures for r in resultats),
        total_gain_heures=sum(r.gain_heures for r in resultats),
        total_prime_ap_pp=total_prime_ap_pp,
        total_surveillance_secretariat=total_surveillance_secretariat,
        total_indemnite_suggestion_admin=total_indemnite_suggestion_admin,
        total_primes=total_prime_ap_pp + total_surveillance_secretariat + total_indemnite_suggestion_admin,
        total_taxe=sum(r.taxe_5 for r in resultats),
        total_retenue_amicale=total_retenue_amicale,
        total_dette=total_dette,
        total_retenues=total_retenue_amicale + total_dette,
        total_net_a_percevoir=sum(r.net_a_percevoir for r in resultats),
    )
