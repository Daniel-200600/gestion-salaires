"""
Fonctions de formatage pour l'affichage (aucune logique métier ici).

Traduit les valeurs internes de la base (M/F, V/P) vers des libellés
lisibles pour l'interface, et inversement. La base de données continue
d'utiliser exclusivement 'M'/'F' et 'V'/'P'.
"""

import calendar
import re
from datetime import date

from models.enums import Sexe, StatutEnseignant, StatutPeriode

LIBELLES_SEXE = {
    Sexe.HOMME: "Masculin",
    Sexe.FEMME: "Féminin",
}

LIBELLES_STATUT = {
    StatutEnseignant.VACATAIRE: "Vacataire",
    StatutEnseignant.PERMANENT: "Permanent",
}

LIBELLES_STATUT_PERIODE = {
    StatutPeriode.BROUILLON: "Brouillon",
    StatutPeriode.OUVERTE: "Ouverte",
    StatutPeriode.VALIDEE: "Validée",
    StatutPeriode.CLOTUREE: "Clôturée",
}

NOMS_MOIS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

_SEXE_DEPUIS_LIBELLE = {libelle: sexe for sexe, libelle in LIBELLES_SEXE.items()}
_STATUT_DEPUIS_LIBELLE = {libelle: statut for statut, libelle in LIBELLES_STATUT.items()}

# Listes ordonnées, pratiques pour peupler des st.selectbox
OPTIONS_SEXE = list(LIBELLES_SEXE.values())
OPTIONS_STATUT = list(LIBELLES_STATUT.values())


def libelle_sexe(sexe: Sexe) -> str:
    return LIBELLES_SEXE[sexe]


def libelle_statut(statut: StatutEnseignant) -> str:
    return LIBELLES_STATUT[statut]


def libelle_actif(actif: bool) -> str:
    return "Actif" if actif else "Inactif"


def libelle_statut_periode(statut: StatutPeriode) -> str:
    return LIBELLES_STATUT_PERIODE[statut]


def nom_mois(mois: int) -> str:
    """Retourne le nom du mois en français (1 = Janvier, ..., 12 = Décembre)."""
    if not isinstance(mois, int) or not 1 <= mois <= 12:
        raise ValueError("Le mois doit être un entier compris entre 1 et 12.")
    return NOMS_MOIS[mois - 1]


NOMS_MOIS_ANGLAIS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def libelle_periode_anglais(mois: int, annee: int) -> str:
    """Libellé de période du bulletin officiel (bilingue) : 7, 2026 -> « JULY 2026 »."""
    if not isinstance(mois, int) or not 1 <= mois <= 12:
        raise ValueError("Le mois doit être un entier compris entre 1 et 12.")
    return f"{NOMS_MOIS_ANGLAIS[mois - 1].upper()} {annee}"


def sexe_depuis_libelle(libelle: str) -> Sexe:
    return _SEXE_DEPUIS_LIBELLE[libelle]


def statut_depuis_libelle(libelle: str) -> StatutEnseignant:
    return _STATUT_DEPUIS_LIBELLE[libelle]


def formater_fcfa(montant: int) -> str:
    """Formate un montant entier FCFA avec séparateur de milliers (ex: 150 000 FCFA)."""
    return f"{montant:,.0f} FCFA".replace(",", " ")


def dates_periode(mois: int, annee: int) -> "tuple[date, date]":
    """
    Calcule les dates de début et de fin d'une période mensuelle.

    Ces dates ne sont stockées nulle part (models.PeriodePaie n'a que
    mois/annee) : elles sont dérivées à la demande, pour l'affichage
    (page de génération comptable, en-tête du fichier Excel).
    """
    dernier_jour = calendar.monthrange(annee, mois)[1]
    return date(annee, mois, 1), date(annee, mois, dernier_jour)


_CARACTERES_INTERDITS_WINDOWS = re.compile(r'[<>:"/\\|?*]')


def nettoyer_nom_fichier(valeur: str) -> str:
    """
    Nettoie une chaîne pour en faire un nom de fichier valide sous
    Windows : remplace les caractères interdits (< > : " / \\ | ? *)
    par des underscores, remplace les espaces par des underscores, et
    retire les points/espaces de fin (également interdits en fin de
    nom sous Windows).
    """
    nettoye = _CARACTERES_INTERDITS_WINDOWS.sub("_", valeur)
    nettoye = nettoye.replace(" ", "_")
    nettoye = nettoye.rstrip(" .")
    return nettoye or "sans_nom"


def formater_taux_taxe(taux) -> str:
    """Taux de taxe (fraction) en pourcentage lisible : Decimal("0.055") -> « 5,5 % »."""
    from decimal import Decimal

    pourcentage = (Decimal(str(taux)) * 100).normalize()
    texte = format(pourcentage, "f")
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return f"{texte.replace('.', ',')} %"
