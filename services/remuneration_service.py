"""
Logique métier des éléments de rémunération : prime AP/PP,
surveillance/secrétariat, indemnité suggestion/admin.

Mêmes règles que services/heures_service.py : écriture uniquement si
la période est OUVERTE et l'enseignant actif ; lecture toujours
possible. Réutilise DonneesPaieValidationError défini dans
heures_service.py : un seul type d'exception pour tout le module 04
(heures, rémunérations, retenues), pour que la page n'ait qu'un seul
except à gérer.
"""

from pathlib import Path
from typing import Dict, Optional, Union

from database.repositories import enseignant_repository, periode_repository, remuneration_repository
from models.element_remuneration import ElementRemuneration
from models.enums import TypeElementRemuneration
from services.heures_service import DonneesPaieValidationError
from utils.validators import valider_montant_fcfa, verifier_enseignant_payable, verifier_periode_ouverte

DbPath = Optional[Union[str, Path]]

TYPES_REMUNERATION = (
    TypeElementRemuneration.PRIME_AP_PP,
    TypeElementRemuneration.SURVEILLANCE_SECRETARIAT,
    TypeElementRemuneration.INDEMNITE_SUGGESTION_ADMIN,
)

_LIBELLES_CHAMP = {
    TypeElementRemuneration.PRIME_AP_PP: "montant de la prime AP/PP",
    TypeElementRemuneration.SURVEILLANCE_SECRETARIAT: "montant de surveillance/secrétariat",
    TypeElementRemuneration.INDEMNITE_SUGGESTION_ADMIN: "montant de l'indemnité suggestion/admin",
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


def enregistrer_remuneration_enseignant(
    periode_id: int,
    enseignant_id: int,
    prime_ap_pp=0,
    surveillance_secretariat=0,
    indemnite_suggestion_admin=0,
    db_path: DbPath = None,
) -> Dict[str, int]:
    """Enregistre (upsert) les 3 éléments de rémunération d'un enseignant pour une période."""
    periode = _obtenir_periode_ou_lever(periode_id, db_path)
    enseignant = _obtenir_enseignant_ou_lever(enseignant_id, db_path)

    valeurs_brutes = {
        TypeElementRemuneration.PRIME_AP_PP: prime_ap_pp,
        TypeElementRemuneration.SURVEILLANCE_SECRETARIAT: surveillance_secretariat,
        TypeElementRemuneration.INDEMNITE_SUGGESTION_ADMIN: indemnite_suggestion_admin,
    }

    try:
        verifier_periode_ouverte(periode)
        verifier_enseignant_payable(enseignant)
        montants_valides = {
            type_element: valider_montant_fcfa(valeur, _LIBELLES_CHAMP[type_element])
            for type_element, valeur in valeurs_brutes.items()
        }
    except ValueError as erreur:
        raise DonneesPaieValidationError(str(erreur)) from erreur

    for type_element, montant in montants_valides.items():
        remuneration_repository.upsert(
            ElementRemuneration(
                enseignant_id=enseignant_id,
                periode_id=periode_id,
                type_element=type_element,
                montant=montant,
            ),
            db_path=db_path,
        )

    return obtenir_remuneration_enseignant(periode_id, enseignant_id, db_path=db_path)


def obtenir_remuneration_enseignant(
    periode_id: int, enseignant_id: int, db_path: DbPath = None
) -> Dict[str, int]:
    """Retourne {type_element: montant} pour les 3 types, 0 par défaut si absent. Toujours lisible."""
    elements = remuneration_repository.lister_par_enseignant_periode(enseignant_id, periode_id, db_path=db_path)
    montants = {type_element.value: 0 for type_element in TYPES_REMUNERATION}
    for element in elements:
        montants[element.type_element.value] = element.montant
    return montants


def lister_remuneration_periode(periode_id: int, db_path: DbPath = None) -> Dict[int, Dict[str, int]]:
    """Retourne {enseignant_id: {type_element: montant}} pour tous les enseignants ayant une saisie."""
    elements = remuneration_repository.lister_par_periode(periode_id, db_path=db_path)
    resultat: Dict[int, Dict[str, int]] = {}
    for element in elements:
        resultat.setdefault(element.enseignant_id, {t.value: 0 for t in TYPES_REMUNERATION})
        resultat[element.enseignant_id][element.type_element.value] = element.montant
    return resultat
