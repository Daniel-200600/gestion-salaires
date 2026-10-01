"""
Orchestration transactionnelle de l'enregistrement groupé des données
de paie (heures, rémunérations, retenues) pour plusieurs enseignants.

Ce module ne contient AUCUNE règle métier propre : il réutilise
exclusivement les validations déjà définies dans utils/validators.py
(les mêmes que celles utilisées individuellement par
services/heures_service.py, services/remuneration_service.py et
services/retenue_service.py) et ne calcule ni ne duplique aucune
formule de salaire (gain heures, base taxable, taxe 5 %, net à
percevoir restent hors périmètre du module 04).

PRINCIPE TRANSACTIONNEL
------------------------
Une seule connexion SQLite est ouverte pour toute l'opération groupée
(cf. `enregistrer_donnees_paie_groupe`). Tous les enseignants du groupe
sont validés puis upsertés sur CETTE MÊME connexion, sans commit
intermédiaire :

    TOUT RÉUSSIT  -> un seul `conn.commit()` à la fin.
    UNE ERREUR    -> `conn.rollback()` explicite avant de relancer
                     l'exception : aucune ligne n'est modifiée, y
                     compris pour les enseignants déjà traités plus
                     tôt dans la boucle.

Ceci évite l'écueil d'une sauvegarde partielle qu'aurait provoqué un
appel séquentiel des 3 services individuels (chacun ouvrant et
validant sa propre connexion/transaction indépendamment des autres).
Les fonctions individuelles de heures_service / remuneration_service /
retenue_service restent inchangées et disponibles pour un
enregistrement enseignant par enseignant hors contexte groupé.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from database.connection import get_connection
from database.repositories import (
    enseignant_repository,
    heures_repository,
    periode_repository,
    remuneration_repository,
    retenue_repository,
)
from models.element_remuneration import ElementRemuneration
from models.enums import TypeElementRemuneration, TypeRetenue
from models.retenue import Retenue
from models.saisie_heures import SaisieHeures
from services.heures_service import DonneesPaieValidationError
from utils.validators import (
    valider_heures,
    valider_montant_fcfa,
    valider_numero_semaine,
    verifier_enseignant_actif,
    verifier_periode_ouverte,
)

DbPath = Optional[Union[str, Path]]


@dataclass
class DonneesPaieEnseignant:
    """
    Regroupe l'ensemble des données de paie à enregistrer pour un
    enseignant, dans le cadre d'un enregistrement groupé sur une
    période donnée (cf. `enregistrer_donnees_paie_groupe`).
    """

    enseignant_id: int
    heures_par_semaine: Dict[int, float] = field(default_factory=dict)
    prime_ap_pp: int = 0
    surveillance_secretariat: int = 0
    indemnite_suggestion_admin: int = 0
    retenue_amicale: int = 0
    dette: int = 0


def enregistrer_donnees_paie_groupe(
    periode_id: int,
    donnees_par_enseignant: List[DonneesPaieEnseignant],
    db_path: DbPath = None,
) -> None:
    """
    Enregistre en une SEULE TRANSACTION les données de paie (heures,
    rémunérations, retenues) de plusieurs enseignants pour une même
    période.

    Comportement garanti :
    - Si TOUT le groupe est valide : un unique commit rend l'ensemble
      des données visibles simultanément.
    - Si UNE SEULE erreur survient, à quelque étape que ce soit (donnée
      invalide, période introuvable ou non ouverte, enseignant
      introuvable ou désactivé) : rollback complet — aucun enseignant
      du groupe n'est modifié, y compris ceux déjà traités avec succès
      plus tôt dans la boucle.

    Lève DonneesPaieValidationError en cas d'échec (même exception que
    les services individuels du module 04).
    """
    if not donnees_par_enseignant:
        return

    with get_connection(db_path) as conn:
        try:
            periode = periode_repository.obtenir_par_id(periode_id, conn=conn)
            if periode is None:
                raise DonneesPaieValidationError(f"Aucune période avec l'id {periode_id}.")
            verifier_periode_ouverte(periode)

            for donnees in donnees_par_enseignant:
                _traiter_enseignant(conn, periode_id, donnees)

        except Exception as erreur:
            conn.rollback()
            if isinstance(erreur, DonneesPaieValidationError):
                raise
            raise DonneesPaieValidationError(str(erreur)) from erreur
        else:
            conn.commit()


def _traiter_enseignant(conn, periode_id: int, donnees: DonneesPaieEnseignant) -> None:
    """
    Valide puis upserte, sur la connexion `conn` de la transaction en
    cours, l'ensemble des données de paie d'UN enseignant. N'effectue
    ni commit ni rollback : entièrement à la charge de l'appelant
    (`enregistrer_donnees_paie_groupe`).
    """
    enseignant = enseignant_repository.obtenir_par_id(donnees.enseignant_id, conn=conn)
    if enseignant is None:
        raise DonneesPaieValidationError(f"Aucun enseignant avec l'id {donnees.enseignant_id}.")
    verifier_enseignant_actif(enseignant)

    # --- Heures ---
    for numero_semaine, valeur_heures in donnees.heures_par_semaine.items():
        saisie = SaisieHeures(
            enseignant_id=donnees.enseignant_id,
            periode_id=periode_id,
            numero_semaine=valider_numero_semaine(numero_semaine),
            heures_effectuees=valider_heures(valeur_heures),
        )
        heures_repository.upsert(saisie, conn=conn)

    # --- Rémunérations ---
    montants_remuneration = {
        TypeElementRemuneration.PRIME_AP_PP: valider_montant_fcfa(
            donnees.prime_ap_pp, "montant de la prime AP/PP"
        ),
        TypeElementRemuneration.SURVEILLANCE_SECRETARIAT: valider_montant_fcfa(
            donnees.surveillance_secretariat, "montant de surveillance/secrétariat"
        ),
        TypeElementRemuneration.INDEMNITE_SUGGESTION_ADMIN: valider_montant_fcfa(
            donnees.indemnite_suggestion_admin, "montant de l'indemnité suggestion/admin"
        ),
    }
    for type_element, montant in montants_remuneration.items():
        remuneration_repository.upsert(
            ElementRemuneration(
                enseignant_id=donnees.enseignant_id,
                periode_id=periode_id,
                type_element=type_element,
                montant=montant,
            ),
            conn=conn,
        )

    # --- Retenues ---
    montants_retenue = {
        TypeRetenue.RETENUE_AMICALE: valider_montant_fcfa(
            donnees.retenue_amicale, "montant de la retenue amicale"
        ),
        TypeRetenue.DETTE: valider_montant_fcfa(donnees.dette, "montant de la dette"),
    }
    for type_retenue, montant in montants_retenue.items():
        retenue_repository.upsert(
            Retenue(
                enseignant_id=donnees.enseignant_id,
                periode_id=periode_id,
                type_retenue=type_retenue,
                montant=montant,
            ),
            conn=conn,
        )
