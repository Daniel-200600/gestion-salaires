"""
Balises des modèles de bulletin de solde.

Un modèle de bulletin (Word .docx ou PDF) contient des balises de la
forme ``{{NOM}}``, remplacées à la génération par les valeurs déjà
calculées par le moteur de paie (services/paie_service.py). Ce module
ne calcule rien : il décrit les balises reconnues et sait les repérer
dans un texte.

Syntaxe
-------
``{{NOM}}``            valeur écrite à l'emplacement de la balise
``{{NOM|centre}}``     (modèles PDF) valeur centrée sur l'emplacement
``{{NOM|droite}}``     (modèles PDF) valeur alignée à droite
``{{NOM|gauche}}``     (modèles PDF) valeur alignée à gauche (défaut)

Dans un modèle Word, l'alignement est celui du paragraphe : l'option
éventuelle est simplement ignorée.

Aucune dépendance à Streamlit ni à la base de données.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Espaces tolérés autour du nom et de l'option ; le nom accepte les
# lettres accentuées (balise historique NET_A_PERÇEVOIR).
MOTIF_BALISE = re.compile(r"\{\{\s*([A-Za-z0-9_À-ÿ]+)\s*(?:\|\s*([A-Za-zé]+)\s*)?\}\}")

ALIGNEMENTS = ("gauche", "centre", "droite")
_ALIAS_ALIGNEMENT = {"g": "gauche", "gauche": "gauche", "left": "gauche",
                     "c": "centre", "centre": "centre", "center": "centre", "centré": "centre",
                     "d": "droite", "droite": "droite", "right": "droite"}


@dataclass(frozen=True)
class Balise:
    nom: str
    libelle: str
    exemple: str
    categorie: str


BALISES: Tuple[Balise, ...] = (
    Balise("NOM", "Nom de l'enseignant (majuscules)", "NOM", "Identité"),
    Balise("PRENOM", "Prénom(s) de l'enseignant (majuscules)", "PRENOMS", "Identité"),
    Balise("NOM_COMPLET", "Nom et prénom(s) (majuscules)", "NOM PRENOMS", "Identité"),
    Balise("STATUT", "Statut abrégé (V ou P)", "V", "Identité"),
    Balise("STATUT_LIBELLE", "Statut en toutes lettres", "Vacataire", "Identité"),
    Balise("PERIODE", "Mois et année en anglais, majuscules (comme le modèle officiel)", "JULY 2026", "Période"),
    Balise("PERIODE_FR", "Mois et année en français, majuscules", "JUILLET 2026", "Période"),
    Balise("DATE", "Date de génération du bulletin (jj/mm/aaaa)", "31/07/2026", "Période"),
    Balise("TOTAL_HEURES", "Nombre total d'heures", "10", "Heures"),
    Balise("SEMAINE_1", "Heures de la semaine 1", "4", "Heures"),
    Balise("SEMAINE_2", "Heures de la semaine 2", "3", "Heures"),
    Balise("SEMAINE_3", "Heures de la semaine 3", "3", "Heures"),
    Balise("SEMAINE_4", "Heures de la semaine 4", "0", "Heures"),
    Balise("SEMAINE_5", "Heures de la semaine 5", "0", "Heures"),
    Balise("TAUX_HORAIRE", "Taux horaire (FCFA)", "1800", "Heures"),
    Balise("GAIN_HEURES", "Gain heures (FCFA)", "18000", "Gains"),
    Balise("PRIME_AP_PP", "Prime AP/PP (FCFA)", "0", "Gains"),
    Balise("SURVEILLANCE_SECRETARIAT", "Surveillance / secrétariat (FCFA)", "0", "Gains"),
    Balise("INDEMNITE_SUGGESTION_ADMIN", "Indemnité de sujétion (FCFA)", "0", "Gains"),
    Balise("TOTAL_GAINS", "Total des gains = base taxable (FCFA)", "18000", "Gains"),
    Balise("TAXE", "Taxe (FCFA)", "990", "Retenues"),
    Balise("TAXE_TAUX", "Taux de taxe appliqué", "5,5 %", "Retenues"),
    Balise("RETENUE_AMICALE", "Retenue amicale (FCFA)", "0", "Retenues"),
    Balise("DETTE", "Dette (FCFA)", "0", "Retenues"),
    Balise("TOTAL_RETENUES", "Total des retenues (FCFA)", "990", "Retenues"),
    Balise("NET_A_PAYER", "Net à payer (FCFA)", "17010", "Net"),
    Balise("NET_EN_LETTRES", "Net à payer en toutes lettres (anglais)", "Seventeen Thousand Ten", "Net"),
)

# Noms historiques (modèle Word d'origine), toujours acceptés.
ALIAS: Dict[str, str] = {
    "TAXE_5": "TAXE",
    "NET_A_PERÇEVOIR": "NET_A_PAYER",
    "NET_A_PERCEVOIR": "NET_A_PAYER",
    "DATE_GENERATION": "DATE",
    "BASE_TAXABLE": "TOTAL_GAINS",
}

NOMS_BALISES = tuple(b.nom for b in BALISES)
_NOMS_RECONNUS = set(NOMS_BALISES) | set(ALIAS)

# Un modèle doit au minimum identifier l'enseignant et indiquer le net.
BALISES_OBLIGATOIRES: Tuple[Tuple[str, ...], ...] = (
    ("NOM", "NOM_COMPLET"),
    ("NET_A_PAYER",),
)
# Absentes, elles ne bloquent pas l'import mais sont signalées.
BALISES_RECOMMANDEES: Tuple[str, ...] = (
    "PERIODE", "STATUT", "GAIN_HEURES", "TAXE", "TOTAL_GAINS", "TOTAL_RETENUES",
)


@dataclass(frozen=True)
class OccurrenceBalise:
    texte: str          # texte exact trouvé, ex. "{{NOM|centre}}"
    nom: str            # nom tel qu'écrit, en majuscules, ex. "NOM"
    nom_canonique: str  # nom après résolution des alias ("" si inconnu)
    alignement: str     # "gauche" / "centre" / "droite"
    debut: int
    fin: int


def nom_canonique(nom: str) -> str:
    """Résout un alias ; retourne "" si la balise est inconnue."""
    nom = nom.upper()
    if nom in ALIAS:
        return ALIAS[nom]
    return nom if nom in NOMS_BALISES else ""


def normaliser_alignement(option: Optional[str]) -> str:
    if not option:
        return "gauche"
    return _ALIAS_ALIGNEMENT.get(option.strip().lower(), "")


def trouver_balises(texte: str) -> List[OccurrenceBalise]:
    """Toutes les balises présentes dans `texte`, dans l'ordre."""
    occurrences = []
    for correspondance in MOTIF_BALISE.finditer(texte or ""):
        nom = correspondance.group(1).upper()
        occurrences.append(OccurrenceBalise(
            texte=correspondance.group(0), nom=nom, nom_canonique=nom_canonique(nom),
            alignement=normaliser_alignement(correspondance.group(2)),
            debut=correspondance.start(), fin=correspondance.end(),
        ))
    return occurrences


def contient_balise_residuelle(texte: str) -> bool:
    return "{{" in (texte or "") and "}}" in (texte or "")


def remplacer_balises(texte: str, valeurs: Dict[str, str]) -> str:
    """
    Remplace chaque balise dont le NOM ÉCRIT figure dans `valeurs`
    (clés "NOM" ou "{{NOM}}", insensible à l'option d'alignement).
    Une balise absente de `valeurs` est laissée telle quelle, afin que
    le contrôle final la détecte (jamais de champ vide silencieux).
    """
    table = valeurs_par_nom(valeurs)

    def _remplacement(correspondance: "re.Match") -> str:
        nom = correspondance.group(1).upper()
        return table[nom] if nom in table else correspondance.group(0)

    return MOTIF_BALISE.sub(_remplacement, texte or "")


def valeurs_par_nom(valeurs: Dict[str, str]) -> Dict[str, str]:
    """{"{{NOM}}": "X"} ou {"NOM": "X"} -> {"NOM": "X"}."""
    table = {}
    for cle, valeur in valeurs.items():
        nom = cle.strip()
        if nom.startswith("{{") and nom.endswith("}}"):
            nom = nom[2:-2].strip()
        table[nom.upper()] = str(valeur)
    return table


def controler_balises(noms: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """
    Contrôle la liste des balises trouvées dans un modèle.
    Retourne (inconnues, obligatoires_manquantes, recommandees_manquantes).
    """
    inconnues = sorted({n for n in noms if n.upper() not in _NOMS_RECONNUS})
    canoniques = {nom_canonique(n) for n in noms} - {""}
    manquantes = [" ou ".join(groupe) for groupe in BALISES_OBLIGATOIRES if not canoniques & set(groupe)]
    recommandees = [n for n in BALISES_RECOMMANDEES if n not in canoniques]
    return inconnues, manquantes, recommandees


def valeurs_exemple() -> Dict[str, str]:
    """
    Valeurs d'exemple pour les aperçus et le modèle PDF standard : un
    exemple fictif (10 h × 1 800 FCFA, taxe 5,5 %),
    avec un nom générique — aucune donnée personnelle réelle.
    """
    valeurs = {b.nom: b.exemple for b in BALISES}
    for alias, cible in ALIAS.items():
        valeurs[alias] = valeurs[cible]
    return valeurs
