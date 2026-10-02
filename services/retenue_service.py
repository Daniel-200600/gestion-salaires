"""
Logique métier des retenues : retenue amicale, dette.

Mêmes règles que services/heures_service.py et
services/remuneration_service.py : écriture uniquement si la période
est OUVERTE et l'enseignant actif ; lecture toujours possible.
Réutilise DonneesPaieValidationError défini dans heures_service.py.
"""

from pathlib import Path
from typing import Dict, Optional, Union

from database.repositories import enseignant_repository, periode_repository, retenue_repository
from models.enums import TypeRetenue
from models.retenue import Retenue
from services.heures_service import DonneesPaieValidationError
from utils.validators import valider_montant_fcfa, verifier_enseignant_payable, verifier_periode_ouverte

DbPath = Optional[Union[str, Path]]

TYPES_RETENUE = (TypeRetenue.RETENUE_AMICALE, TypeRetenue.DETTE)

_LIBELLES_CHAMP = {
    TypeRetenue.RETENUE_AMICALE: "montant de la retenue amicale",
    TypeRetenue.DETTE: "montant de la dette",
}


def _obtenir_periode_ou_lever(periode_id: int, db_path: DbPath):
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise DonneesPaieValidationError(f"Aucune période avec l'id {periode_id}.")
    return periode


def _obtenir_enseignant_ou_lever(enseignant_id: int, db_path: DbPath):
    enseignant = enseignant_repository.obtenir_par_id(enseignant_id, db_path=db_path)
    if enseignant is None:
        raise DonneesPaieValidationError(f"Aucun enseignant avec l'id {enseignant_id}.")
    return enseignant


def enregistrer_retenues_enseignant(
    periode_id: int,
    enseignant_id: int,
    retenue_amicale=0,
    dette=0,
    db_path: DbPath = None,
) -> Dict[str, int]:
    """Enregistre (upsert) les 2 retenues d'un enseignant pour une période."""
    periode = _obtenir_periode_ou_lever(periode_id, db_path)
    enseignant = _obtenir_enseignant_ou_lever(enseignant_id, db_path)

    valeurs_brutes = {
        TypeRetenue.RETENUE_AMICALE: retenue_amicale,
        TypeRetenue.DETTE: dette,
    }

    try:
        verifier_periode_ouverte(periode)
        verifier_enseignant_payable(enseignant)
        montants_valides = {
            type_retenue: valider_montant_fcfa(valeur, _LIBELLES_CHAMP[type_retenue])
            for type_retenue, valeur in valeurs_brutes.items()
        }
    except ValueError as erreur:
        raise DonneesPaieValidationError(str(erreur)) from erreur

    for type_retenue, montant in montants_valides.items():
        retenue_repository.upsert(
            Retenue(
                enseignant_id=enseignant_id,
                periode_id=periode_id,
                type_retenue=type_retenue,
                montant=montant,
            ),
            db_path=db_path,
        )

    return obtenir_retenues_enseignant(periode_id, enseignant_id, db_path=db_path)


def obtenir_retenues_enseignant(periode_id: int, enseignant_id: int, db_path: DbPath = None) -> Dict[str, int]:
    """Retourne {type_retenue: montant} pour les 2 types, 0 par défaut si absent. Toujours lisible."""
    retenues = retenue_repository.lister_par_enseignant_periode(enseignant_id, periode_id, db_path=db_path)
    montants = {type_retenue.value: 0 for type_retenue in TYPES_RETENUE}
    for retenue in retenues:
        montants[retenue.type_retenue.value] = retenue.montant
    return montants


def lister_retenues_periode(periode_id: int, db_path: DbPath = None) -> Dict[int, Dict[str, int]]:
    """Retourne {enseignant_id: {type_retenue: montant}} pour tous les enseignants ayant une saisie."""
    retenues = retenue_repository.lister_par_periode(periode_id, db_path=db_path)
    resultat: Dict[int, Dict[str, int]] = {}
    for retenue in retenues:
        resultat.setdefault(retenue.enseignant_id, {t.value: 0 for t in TYPES_RETENUE})
        resultat[retenue.enseignant_id][retenue.type_retenue.value] = retenue.montant
    return resultat
