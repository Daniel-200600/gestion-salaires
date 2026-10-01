"""
Utilitaires de précision monétaire (FCFA).

Centralise la façon dont l'application convertit un montant Decimal
(résultat d'un calcul) en entier FCFA à stocker ou afficher. Utilisé
par le moteur de calcul de paie (services/paie_service.py) et
réutilisable par tout futur module manipulant des montants calculés
(génération de bulletins, exports Excel/Word).

RÈGLE D'ARRONDI RETENUE
------------------------
Arrondi commercial (ROUND_HALF_UP) à l'entier FCFA le plus proche :
un montant dont la partie décimale est >= 0,5 est arrondi au FCFA
supérieur (ex : 11750,50 -> 11751 ; 11750,49 -> 11750).

C'est la convention la plus courante et la plus intuitive pour des
montants monétaires (le FCFA n'a pas de sous-unité active), et surtout
la plus prévisible pour un comptable relisant un bulletin — contrairement
à l'arrondi "au pair" (banker's rounding) qu'applique par défaut le
round() natif de Python, qui peut surprendre (round(0.5) == 0).

Cette règle est déterministe : à Decimal égal, le résultat est toujours
identique, quel que soit le nombre d'appels ou l'ordre des opérations.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

UN_FCFA = Decimal("1")


def arrondir_fcfa(valeur: Union[Decimal, int, str]) -> int:
    """
    Arrondit un montant à l'entier FCFA le plus proche, selon la règle
    ROUND_HALF_UP (arrondi commercial, cf. docstring du module).

    Toujours utiliser cette fonction pour convertir un montant calculé
    (Decimal) en entier FCFA — jamais `round()` Python natif (arrondi
    "au pair", différent et moins prévisible en contexte comptable) ni
    une conversion via float (imprécision binaire).
    """
    if not isinstance(valeur, Decimal):
        valeur = Decimal(str(valeur))
    return int(valeur.quantize(UN_FCFA, rounding=ROUND_HALF_UP))
