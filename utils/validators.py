"""
Validation des données de saisie liées aux enseignants.

Centralise ici toute règle de validation afin qu'elle ne soit jamais
dupliquée entre la page Streamlit et le service. Ce module ne dépend
ni de Streamlit ni de la base de données.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

from models.enums import Sexe, StatutEnseignant, StatutPeriode


class EnseignantValidationError(Exception):
    """Levée quand une donnée saisie pour un enseignant est invalide."""


def nettoyer_texte(valeur: Optional[str]) -> str:
    """Supprime les espaces en début/fin et réduit les espaces multiples à un seul."""
    if valeur is None:
        return ""
    return re.sub(r"\s+", " ", valeur.strip())


def valider_nom_ou_prenom(valeur: Optional[str], nom_champ: str) -> str:
    """Valide et nettoie un nom ou un prénom. Lève une erreur si vide après nettoyage."""
    nettoye = nettoyer_texte(valeur)
    if not nettoye:
        raise EnseignantValidationError(f"Le champ '{nom_champ}' ne peut pas être vide.")
    return nettoye


def valider_sexe(valeur: Union[str, Sexe]) -> Sexe:
    """Valide le sexe. Accepte directement un Sexe ou une chaîne ('M'/'F')."""
    if isinstance(valeur, Sexe):
        return valeur
    try:
        return Sexe(str(valeur).strip().upper())
    except (ValueError, AttributeError):
        raise EnseignantValidationError("Le sexe est invalide : valeurs autorisées 'M' ou 'F'.")


def valider_statut(valeur: Union[str, StatutEnseignant]) -> StatutEnseignant:
    """Valide le statut. Accepte directement un StatutEnseignant ou une chaîne ('V'/'P')."""
    if isinstance(valeur, StatutEnseignant):
        return valeur
    try:
        return StatutEnseignant(str(valeur).strip().upper())
    except (ValueError, AttributeError):
        raise EnseignantValidationError("Le statut est invalide : valeurs autorisées 'V' ou 'P'.")


def valider_taux_horaire(valeur) -> int:
    """
    Valide le taux horaire et le retourne en entier FCFA.

    Utilise Decimal (jamais float directement) pour détecter de façon
    fiable toute partie fractionnaire, conformément à la stratégie
    monétaire retenue pour l'application (cf. database/schema.sql).
    """
    if valeur is None or valeur == "":
        raise EnseignantValidationError("Le taux horaire est obligatoire.")
    try:
        valeur_decimale = Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        raise EnseignantValidationError("Le taux horaire doit être un nombre.")
    if valeur_decimale < 0:
        raise EnseignantValidationError("Le taux horaire ne peut pas être négatif.")
    if valeur_decimale != valeur_decimale.to_integral_value():
        raise EnseignantValidationError(
            "Le taux horaire doit être un nombre entier de FCFA (pas de décimales)."
        )
    return int(valeur_decimale)


def nettoyer_champ_optionnel(valeur: Optional[str]) -> Optional[str]:
    """Nettoie un champ facultatif (email, téléphone, adresse) ; renvoie None si vide."""
    nettoye = nettoyer_texte(valeur)
    return nettoye if nettoye else None


def valider_montant_fcfa(valeur, nom_champ: str = "montant") -> int:
    """
    Valide un montant en FCFA entiers (>= 0, sans décimales) et le
    retourne en int.

    Fonction générique réutilisée par tout champ monétaire de
    l'application (taux horaire, primes, indemnités, retenues), avec
    Decimal (jamais float) pour détecter fiablement toute partie
    fractionnaire. Lève un ValueError générique plutôt qu'une exception
    métier spécifique : chaque service appelant la capture et la
    retraduit dans son propre type d'exception (ex: RemunerationValidationError).
    """
    if valeur is None or valeur == "":
        raise ValueError(f"Le champ '{nom_champ}' est obligatoire.")
    try:
        valeur_decimale = Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Le champ '{nom_champ}' doit être un nombre.")
    if valeur_decimale < 0:
        raise ValueError(f"Le champ '{nom_champ}' ne peut pas être négatif.")
    if valeur_decimale != valeur_decimale.to_integral_value():
        raise ValueError(f"Le champ '{nom_champ}' doit être un nombre entier de FCFA (pas de décimales).")
    return int(valeur_decimale)


def valider_heures(valeur, nom_champ: str = "heures effectuées") -> float:
    """
    Valide un nombre d'heures effectuées : numérique, >= 0, décimales
    autorisées (contrairement aux montants monétaires). Lève un
    ValueError générique ; le service appelant le retraduit dans son
    propre type d'exception.
    """
    if valeur is None or valeur == "":
        raise ValueError(f"Le champ '{nom_champ}' est obligatoire.")
    try:
        heures = float(valeur)
    except (TypeError, ValueError):
        raise ValueError(f"Le champ '{nom_champ}' doit être un nombre.")
    if heures < 0:
        raise ValueError(f"Le champ '{nom_champ}' ne peut pas être négatif.")
    return heures


def valider_numero_semaine(valeur) -> int:
    """Valide un numéro de semaine de saisie : entier compris entre 1 et 5."""
    try:
        semaine = int(valeur)
    except (TypeError, ValueError):
        raise ValueError("Le numéro de semaine doit être un entier.")
    if not (1 <= semaine <= 5):
        raise ValueError("Le numéro de semaine doit être compris entre 1 et 5.")
    return semaine


def verifier_periode_ouverte(periode) -> None:
    """
    Lève un ValueError si la période n'est pas au statut OUVERTE.

    Utilisé avant toute écriture de données de paie (heures,
    rémunérations, retenues) : la lecture, elle, reste toujours
    possible quel que soit le statut (import différé pour éviter tout
    risque de cycle avec models.enums).
    """
    if periode.statut != StatutPeriode.OUVERTE:
        raise ValueError(
            "Impossible de saisir des données de paie : la période est au statut "
            f"'{periode.statut.value}' (seule une période 'ouverte' accepte la saisie)."
        )


def message_fiche_incomplete(enseignant) -> str:
    manquants = ", ".join(enseignant.champs_manquants)
    return (f"La fiche de {enseignant.nom} {enseignant.prenom}".rstrip() + f" est incomplète (à renseigner : {manquants}). "
            "Complétez-la dans Gestion › Enseignants avant de saisir ou de calculer sa paie.")


def verifier_enseignant_payable(enseignant) -> None:
    """
    Lève un ValueError si l'enseignant ne peut pas recevoir de données de
    paie : désactivé, ou fiche incomplète (sexe, statut ou taux horaire
    manquant, cas d'un enseignant importé depuis une liste existante).
    """
    verifier_enseignant_actif(enseignant)
    if not enseignant.est_complet:
        raise ValueError(message_fiche_incomplete(enseignant))


def verifier_enseignant_actif(enseignant) -> None:
    """
    Lève un ValueError si l'enseignant est désactivé.

    Une nouvelle saisie (ou une modification) de données de paie n'est
    jamais proposée pour un enseignant désactivé ; ses données déjà
    enregistrées restent en revanche toujours consultables (aucune
    vérification équivalente sur les fonctions de lecture).
    """
    if not enseignant.actif:
        raise ValueError(
            "Impossible d'enregistrer des données de paie pour un enseignant désactivé."
        )
