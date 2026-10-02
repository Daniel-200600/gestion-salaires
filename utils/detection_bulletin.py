"""
Détection automatique des champs d'un bulletin déjà rempli.

Lorsqu'un administrateur envoie un bulletin existant (Word ou PDF, par
exemple un bulletin de l'an dernier) plutôt qu'un modèle à balises, l'application
découpe le document en segments de texte (voir exports/pdf_export.py et
exports/word_export.py), puis ce module PROPOSE, pour chaque segment,
le champ qu'il représente : nom, période, heures, montants, net...

Les propositions reposent sur les intitulés du bulletin : un nombre
situé sur la même ligne que « Taxe / Tax » et à sa droite est la taxe,
le texte à gauche de « Statut: » est le nom, etc. Elles sont toujours
présentées à l'administrateur, qui les corrige si besoin avant
d'enregistrer le modèle : rien n'est appliqué sans validation.

Module pur : aucune dépendance à Streamlit, à la base ou aux formats
de fichier. Un segment est décrit par un rectangle (x0, y0, x1, y1) :
coordonnées réelles pour un PDF, coordonnées symboliques pour un
document Word (ligne de tableau, colonne, position dans le texte).
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional

MOIS_EN = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
           "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER")
MOIS_FR = ("JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOUT",
           "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE")

MOTIF_NOMBRE = re.compile(r"^-?\d{1,3}(?:[   .,]\d{3})+(?:[.,]\d+)?$|^-?\d+(?:[.,]\d+)?$")
MOTIF_DATE = re.compile(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$")
_MOTS_NOMBRES = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand|million|mille|cent|francs?)\b", re.IGNORECASE,
)


@dataclass
class Segment:
    """Morceau de texte du document, avec sa position."""

    id: str
    texte: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int = 0

    @property
    def genre(self) -> str:
        return genre_texte(self.texte)

    @property
    def centre_y(self) -> float:
        return (self.y0 + self.y1) / 2


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def genre_texte(texte: str) -> str:
    """nombre / date / mois (mois + année) / texte."""
    t = texte.strip()
    if MOTIF_NOMBRE.match(t):
        return "nombre"
    if MOTIF_DATE.match(t):
        return "date"
    if mois_annee(t):
        return "mois"
    return "texte"


def mois_annee(texte: str) -> Optional[str]:
    """Retourne "en" ou "fr" si le texte est de la forme « JULY 2026 » / « Juillet 2026 »."""
    t = _sans_accents(texte).upper().strip()
    correspondance = re.match(r"^([A-Z]+)\s+(\d{4})$", t)
    if not correspondance:
        return None
    if correspondance.group(1) in MOIS_EN:
        return "en"
    if correspondance.group(1) in MOIS_FR:
        return "fr"
    return None


def meme_ligne(a: Segment, b: Segment) -> bool:
    if a.page != b.page:
        return False
    hauteur = min(a.y1 - a.y0, b.y1 - b.y0)
    tolerance = max(0.35 * hauteur, 0.1)
    return abs(a.centre_y - b.centre_y) <= tolerance


# Intitulés reconnus -> balises à attribuer aux nombres situés à droite
# (dans l'ordre de gauche à droite ; les derniers nombres sont retenus).
RUBRIQUES = (
    (re.compile(r"gain\s*heures?|hourly\s*wage|heures?\s*effectu", re.I),
     ("TOTAL_HEURES", "TAUX_HORAIRE", "GAIN_HEURES")),
    (re.compile(r"prime|incentive", re.I), ("PRIME_AP_PP",)),
    (re.compile(r"surveillance|invigilation|secr[ée]tariat", re.I), ("SURVEILLANCE_SECRETARIAT",)),
    (re.compile(r"indemnit|duty\s*post|allowance", re.I), ("INDEMNITE_SUGGESTION_ADMIN",)),
    (re.compile(r"^\s*taxe\b|\btax\b", re.I), ("TAXE",)),
    (re.compile(r"amicale|social\s*deduction", re.I), ("RETENUE_AMICALE",)),
    (re.compile(r"\bdette\b|\bdebt\b", re.I), ("DETTE",)),
    (re.compile(r"^\s*total\s*$", re.I), ("TOTAL_GAINS", "TOTAL_RETENUES")),
    (re.compile(r"net\s*(a|à)\s*payer|net\s*pay", re.I), ("NET_A_PAYER",)),
)
MOTIF_STATUT = re.compile(r"^\s*(statut|status)\s*:?\s*$", re.I)
MOTIF_NOM = re.compile(r"^\s*(nom(\s*(et|&)\s*pr[ée]noms?)?|name|noms?\s*:?)\s*:?\s*$", re.I)
VALEURS_STATUT = {"V": "STATUT", "P": "STATUT", "VACATAIRE": "STATUT_LIBELLE", "PERMANENT": "STATUT_LIBELLE"}


def _est_intitule(segment: Segment) -> bool:
    return any(motif.search(segment.texte) for motif, _ in RUBRIQUES) or bool(MOTIF_STATUT.match(segment.texte))


def suggerer_correspondances(segments: List[Segment]) -> Dict[str, str]:
    """
    Propose une balise pour les segments reconnus : {segment.id: "NOM_BALISE"}.
    Les segments non reconnus sont absents (texte fixe du modèle).
    """
    propositions: Dict[str, str] = {}
    pris = set()

    def _attribuer(segment: Segment, balise: str) -> None:
        if segment.id not in pris and balise not in propositions.values():
            propositions[segment.id] = balise
            pris.add(segment.id)

    # 1. Période et date
    for segment in segments:
        if segment.genre == "mois":
            _attribuer(segment, "PERIODE" if mois_annee(segment.texte) == "en" else "PERIODE_FR")
        elif segment.genre == "date":
            _attribuer(segment, "DATE")

    # 2. Rubriques : nombres à droite de l'intitulé, sur la même ligne
    for segment in segments:
        if segment.genre != "texte":
            continue
        for motif, balises in RUBRIQUES:
            if not motif.search(segment.texte):
                continue
            a_droite = sorted(
                (s for s in segments if s.id not in pris and meme_ligne(s, segment) and s.x0 >= segment.x1 - 0.5),
                key=lambda s: s.x0,
            )
            nombres = [s for s in a_droite if s.genre == "nombre"]
            if balises[0] == "TOTAL_HEURES":
                cibles = {3: balises, 2: ("TOTAL_HEURES", "GAIN_HEURES"), 1: ("GAIN_HEURES",)}
                nombres = nombres[-3:]
                balises_retenues = cibles.get(len(nombres), ())
            elif balises[0] == "TOTAL_GAINS":
                nombres = nombres[-2:]
                balises_retenues = balises[:len(nombres)]
            else:
                nombres = nombres[-1:]
                balises_retenues = balises[:len(nombres)]
            for nombre, balise in zip(nombres, balises_retenues):
                _attribuer(nombre, balise)
            if balises[0] == "NET_A_PAYER":
                for s in a_droite:
                    if s.genre == "texte" and _MOTS_NOMBRES.search(s.texte):
                        _attribuer(s, "NET_EN_LETTRES")
                        break
            break

    # 3. Statut, puis nom (texte à gauche du statut sur la même ligne, ou à droite d'un intitulé « Nom »)
    for segment in segments:
        if MOTIF_STATUT.match(segment.texte):
            suivants = sorted(
                (s for s in segments if s.id not in pris and meme_ligne(s, segment) and s.x0 >= segment.x1 - 0.5),
                key=lambda s: s.x0,
            )
            if suivants and suivants[0].texte.strip().upper() in VALEURS_STATUT:
                _attribuer(suivants[0], VALEURS_STATUT[suivants[0].texte.strip().upper()])
            precedents = sorted(
                (s for s in segments if s.id not in pris and meme_ligne(s, segment) and s.x1 <= segment.x0 + 0.5
                 and s.genre == "texte" and not _est_intitule(s) and not MOTIF_NOM.match(s.texte)),
                key=lambda s: -s.x1,
            )
            if precedents and "NOM_COMPLET" not in propositions.values():
                _attribuer(precedents[0], "NOM_COMPLET")
    if "NOM_COMPLET" not in propositions.values():
        for segment in segments:
            if MOTIF_NOM.match(segment.texte):
                suivants = sorted(
                    (s for s in segments if s.id not in pris and meme_ligne(s, segment) and s.x0 >= segment.x1 - 0.5
                     and s.genre == "texte"),
                    key=lambda s: s.x0,
                )
                if suivants:
                    _attribuer(suivants[0], "NOM_COMPLET")
                    break

    return propositions
