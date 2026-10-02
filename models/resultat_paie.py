"""
Modèle de résultat de calcul de paie (module 05).

Structure de données PURE représentant le résultat du calcul de paie
d'un enseignant pour une période — PAS un modèle persisté en base : il
n'existe dans aucune table, c'est un objet de calcul/prévisualisation,
produit par services/paie_service.py et consommé par
pages/4_Calcul_Paie.py.

Lorsqu'un bulletin sera définitivement généré (module ultérieur), ses
valeurs alimenteront un BulletinPaie (models/bulletin_paie.py) — qui
lui est un snapshot persisté et immuable dans bulletins_paie. La
correspondance des champs est directe (mêmes valeurs, noms presque
identiques) :

    ResultatPaie.taxe_5           -> BulletinPaie.taxe_5pct
    ResultatPaie.net_a_percevoir  -> BulletinPaie.net_a_payer
    (tous les autres champs partagent déjà exactement le même nom)

Ce module ne modifie et ne casse en rien la logique de snapshot déjà
en place pour bulletins_paie (immutabilité, triggers SQL) : le module
05 ne persiste rien.

Précision monétaire : tous les montants sont des FCFA entiers (int),
jamais des float — cohérent avec la stratégie déjà en place dans toute
l'application (cf. database/schema.sql, models/bulletin_paie.py).
Seules les heures (semaine_1..5, total_heures) restent en float.
"""

from dataclasses import dataclass
from decimal import Decimal

from config.settings import TAUX_TAXE

from models.enums import Sexe, StatutEnseignant


@dataclass
class ResultatPaie:
    enseignant_id: int
    periode_id: int

    # Identité (snapshot au moment du calcul — pas de re-lecture différée)
    nom: str
    prenom: str
    sexe: Sexe
    statut: StatutEnseignant
    taux_horaire: int

    # Heures (durées, float — jamais stockées séparément : dérivées des saisies)
    semaine_1: float
    semaine_2: float
    semaine_3: float
    semaine_4: float
    semaine_5: float
    total_heures: float

    # Montants (FCFA entiers)
    gain_heures: int
    prime_ap_pp: int
    surveillance_secretariat: int
    indemnite_suggestion_admin: int
    base_taxable: int
    taxe_5: int
    retenue_amicale: int
    dette: int
    net_a_percevoir: int

    # Taux de taxe appliqué (fraction, ex. Decimal("0.055")) — celui de la période.
    taux_taxe: Decimal = TAUX_TAXE
