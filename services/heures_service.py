"""
Logique métier de saisie des heures effectuées.

Une saisie (ou modification) d'heures n'est possible que pour une
période au statut OUVERTE, et pour un enseignant actif : une nouvelle
saisie n'est jamais proposée pour un enseignant désactivé, mais ses
données déjà enregistrées restent lisibles (fonctions de lecture,
sans aucune vérification de statut ni d'activité).

Le TOTAL D'HEURES est une valeur DÉRIVÉE : il n'est jamais stocké en
base (pas de deuxième source de vérité). `total_heures()` le
recalcule à la demande à partir des saisies individuelles.

Le stockage utilise un upsert SQL (cf. database/repositories/
heures_repository.py) sur la contrainte UNIQUE
(enseignant_id, periode_id, numero_semaine) : aucune resaisie ne peut
créer de doublon.

DonneesPaieValidationError est l'exception commune à tout le module 04
(heures, rémunérations, retenues) : elle est définie ici et réutilisée
par services/remuneration_service.py et services/retenue_service.py,
afin qu'un seul type d'exception suffise côté page.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

from database.repositories import enseignant_repository, heures_repository, periode_repository
from models.saisie_heures import SaisieHeures
from utils.validators import (
    valider_heures,
    valider_numero_semaine,
    verifier_enseignant_actif,
    verifier_periode_ouverte,
)

DbPath = Optional[Union[str, Path]]

SEMAINES = (1, 2, 3, 4, 5)


class DonneesPaieValidationError(Exception):
    """
    Levée pour toute erreur de validation des données de paie (heures,
    éléments de rémunération, retenues) : valeur invalide, numéro de
    semaine hors 1-5, période introuvable ou non ouverte, enseignant
    introuvable ou désactivé.
    """


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


def enregistrer_heures_enseignant(
    periode_id: int,
    enseignant_id: int,
    heures_par_semaine: Dict[int, float],
    db_path: DbPath = None,
) -> List[SaisieHeures]:
    """
    Enregistre (upsert) les heures d'un enseignant pour une période,
    semaine par semaine. `heures_par_semaine` peut ne contenir qu'un
    sous-ensemble des semaines 1 à 5 ; les semaines absentes du dict
    ne sont pas touchées.
    """
    periode = _obtenir_periode_ou_lever(periode_id, db_path)
    enseignant = _obtenir_enseignant_ou_lever(enseignant_id, db_path)

    try:
        verifier_periode_ouverte(periode)
        verifier_enseignant_actif(enseignant)
        saisies_validees = [
            SaisieHeures(
                enseignant_id=enseignant_id,
                periode_id=periode_id,
                numero_semaine=valider_numero_semaine(numero_semaine),
                heures_effectuees=valider_heures(valeur_heures),
            )
            for numero_semaine, valeur_heures in heures_par_semaine.items()
        ]
    except ValueError as erreur:
        raise DonneesPaieValidationError(str(erreur)) from erreur

    for saisie in saisies_validees:
        heures_repository.upsert(saisie, db_path=db_path)

    return heures_repository.lister_par_enseignant_periode(enseignant_id, periode_id, db_path=db_path)


def obtenir_heures_enseignant(
    periode_id: int, enseignant_id: int, db_path: DbPath = None
) -> Dict[int, float]:
    """
    Retourne un dict {numero_semaine: heures} complet pour les 5
    semaines (0.0 par défaut pour toute semaine non encore saisie).
    Lecture toujours possible, quel que soit le statut de la période
    ou l'état actif/inactif de l'enseignant (historique consultable).
    """
    saisies = heures_repository.lister_par_enseignant_periode(enseignant_id, periode_id, db_path=db_path)
    heures = {semaine: 0.0 for semaine in SEMAINES}
    for saisie in saisies:
        heures[saisie.numero_semaine] = saisie.heures_effectuees
    return heures


def lister_heures_periode(periode_id: int, db_path: DbPath = None) -> Dict[int, Dict[int, float]]:
    """Retourne {enseignant_id: {numero_semaine: heures}} pour tous les enseignants ayant une saisie."""
    saisies = heures_repository.lister_par_periode(periode_id, db_path=db_path)
    resultat: Dict[int, Dict[int, float]] = {}
    for saisie in saisies:
        resultat.setdefault(saisie.enseignant_id, {semaine: 0.0 for semaine in SEMAINES})
        resultat[saisie.enseignant_id][saisie.numero_semaine] = saisie.heures_effectuees
    return resultat


def total_heures(heures_par_semaine: Dict[int, float]) -> float:
    """
    Calcule le total d'heures à partir d'un dict {semaine: heures}.

    Fonction PURE, sans aucun accès base : le total n'est jamais
    stocké, toujours recalculé à partir des saisies individuelles.
    """
    return sum(heures_par_semaine.values())
