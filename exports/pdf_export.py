"""
Génération de bulletins à partir d'un modèle PDF.

Un modèle PDF est un bulletin mis en page (exporté d'Excel, de Word...)
dont certaines zones de texte doivent être remplacées par les valeurs
de chaque enseignant. Ces zones sont décrites par des objets ZonePdf,
obtenus de deux façons :

- modèle à balises : le PDF contient des textes {{NOM}}, {{NET_A_PAYER}}...
  (zones_depuis_balises) ;
- bulletin déjà rempli : les segments de texte sont repérés
  (segments_pdf), l'application propose les correspondances
  (utils/detection_bulletin.py), l'administrateur les valide
  (zone_depuis_segment).

À la génération, chaque zone est effacée (suppression réelle du texte
d'origine, le fond et les traits du modèle sont conservés) puis la
valeur y est réécrite, dans la même police (famille, taille, graisse,
couleur), à la même ligne de base, alignée à gauche, centrée ou à
droite sur la zone d'origine. Le reste du document (logo, couleurs,
traits, textes fixes) est rigoureusement inchangé.

Ce module ne contient aucune formule de paie : il écrit des textes déjà
préparés par services/bulletin_service.py. Aucune dépendance à Streamlit.

Bibliothèque : PyMuPDF (module ``pymupdf``).
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import pymupdf

from utils.balises_bulletin import MOTIF_BALISE, nom_canonique, normaliser_alignement, valeurs_par_nom
from utils.detection_bulletin import Segment, genre_texte, mois_annee

Contenu = Union[bytes, bytearray]

_MOTIF_JETON = re.compile(r"\{([A-Z0-9_]+)\}")


class PdfExportError(Exception):
    """Modèle PDF illisible, sans texte, ou bulletin impossible à produire."""


@dataclass
class ZonePdf:
    """Zone d'un modèle PDF remplacée à chaque génération."""

    page: int
    rect: Tuple[float, float, float, float]
    gabarit: str                  # ex. "{NOM_COMPLET}" ou "Statut: {STATUT}"
    alignement: str = "centre"    # gauche / centre / droite
    taille: float = 11.0
    famille: str = "serif"        # serif / sans
    gras: bool = True
    italique: bool = False
    couleur: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ligne_base: Optional[float] = None
    texte_origine: str = ""

    def balises(self) -> List[str]:
        return _MOTIF_JETON.findall(self.gabarit)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(donnees: dict) -> "ZonePdf":
        donnees = dict(donnees)
        donnees["rect"] = tuple(donnees["rect"])
        donnees["couleur"] = tuple(donnees.get("couleur", (0.0, 0.0, 0.0)))
        return ZonePdf(**donnees)


@dataclass
class SegmentPdf(Segment):
    """Segment de texte d'un PDF, avec la police de son premier caractère."""

    taille: float = 11.0
    famille: str = "serif"
    gras: bool = False
    italique: bool = False
    couleur: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ligne_base: float = 0.0


# ---------------------------------------------------------------------
# Ouverture et lecture
# ---------------------------------------------------------------------

def ouvrir(contenu: Contenu) -> "pymupdf.Document":
    try:
        document = pymupdf.open(stream=bytes(contenu), filetype="pdf")
    except Exception as erreur:  # noqa: BLE001 — tout échec d'ouverture = fichier invalide
        raise PdfExportError(f"Le fichier n'est pas un PDF lisible ({erreur}).") from erreur
    if document.needs_pass:
        raise PdfExportError("Ce PDF est protégé par un mot de passe : il ne peut pas servir de modèle.")
    if document.page_count == 0:
        raise PdfExportError("Ce PDF ne contient aucune page.")
    return document


def texte_pdf(contenu: Contenu) -> str:
    document = ouvrir(contenu)
    try:
        return "\n".join(page.get_text() for page in document)
    finally:
        document.close()


def _famille(nom_police: str) -> str:
    nom = (nom_police or "").lower()
    if any(m in nom for m in ("times", "serif", "roman", "georgia", "garamond", "cambria", "book")) and "sans" not in nom:
        return "serif"
    return "sans"


def _couleur(entier: int) -> Tuple[float, float, float]:
    return (((entier >> 16) & 255) / 255, ((entier >> 8) & 255) / 255, (entier & 255) / 255)


def _style_span(span: dict) -> dict:
    nom = span.get("font", "")
    drapeaux = span.get("flags", 0)
    return {
        "taille": round(float(span.get("size", 11.0)), 2),
        "famille": _famille(nom),
        "gras": bool(drapeaux & 16) or "bold" in nom.lower(),
        "italique": bool(drapeaux & 2) or "italic" in nom.lower() or "oblique" in nom.lower(),
        "couleur": _couleur(span.get("color", 0)),
        "ligne_base": round(float(span.get("origin", (0, 0))[1]), 2),
    }


def _mots_page(page) -> List[dict]:
    """Mots de la page (caractères regroupés), avec position, style et identifiant de ligne."""
    mots = []
    brut = page.get_text("rawdict")
    for numero_bloc, bloc in enumerate(brut.get("blocks", [])):
        for numero_ligne, ligne in enumerate(bloc.get("lines", [])):
            for span in ligne.get("spans", []):
                style = _style_span(span)
                courant = None
                for caractere in span.get("chars", []):
                    c = caractere["c"]
                    x0, y0, x1, y1 = caractere["bbox"]
                    if c.isspace():
                        if courant:
                            mots.append(courant)
                        courant = None
                        continue
                    if courant is None:
                        courant = {"texte": c, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                   "ligne": (numero_bloc, numero_ligne), **style}
                    else:
                        courant["texte"] += c
                        courant["x1"] = max(courant["x1"], x1)
                        courant["y0"] = min(courant["y0"], y0)
                        courant["y1"] = max(courant["y1"], y1)
                if courant:
                    mots.append(courant)
    return mots


def _fusionnables(a: dict, b: dict) -> bool:
    """Deux mots consécutifs d'une même ligne appartiennent-ils au même segment ?"""
    if a["ligne"] != b["ligne"]:
        return False
    ecart = b["x0"] - a["x1"]
    if ecart > max(a["taille"], b["taille"]) * 1.2:
        return False
    genre_a, genre_b = genre_texte(a["texte"]), genre_texte(b["texte"])
    if a["texte"].endswith(":"):
        return False
    if genre_a == "nombre" and genre_b == "nombre":
        # « 20 400 » (séparateur de milliers) : le second groupe fait 3 chiffres
        return bool(re.fullmatch(r"\d{3}([.,]\d+)?", b["texte"]))
    if genre_a == "nombre" or genre_b == "nombre":
        # « JULY 2026 » : mois suivi de l'année
        return genre_a != "nombre" and bool(mois_annee(f"{a['texte']} {b['texte']}"))
    return True


def segments_pdf(contenu: Contenu) -> List[SegmentPdf]:
    """Découpe le PDF en segments (groupes de mots, nombres isolés, mois + année)."""
    document = ouvrir(contenu)
    segments: List[SegmentPdf] = []
    try:
        for numero_page, page in enumerate(document):
            groupes: List[List[dict]] = []
            for mot in _mots_page(page):
                if groupes and _fusionnables(groupes[-1][-1], mot):
                    groupes[-1].append(mot)
                else:
                    groupes.append([mot])
            for groupe in groupes:
                premier = groupe[0]
                segments.append(SegmentPdf(
                    id=f"p{numero_page}-s{len(segments)}",
                    texte=" ".join(m["texte"] for m in groupe),
                    x0=min(m["x0"] for m in groupe), y0=min(m["y0"] for m in groupe),
                    x1=max(m["x1"] for m in groupe), y1=max(m["y1"] for m in groupe),
                    page=numero_page,
                    taille=premier["taille"], famille=premier["famille"], gras=premier["gras"],
                    italique=premier["italique"], couleur=premier["couleur"], ligne_base=premier["ligne_base"],
                ))
    finally:
        document.close()
    if not segments:
        raise PdfExportError(
            "Ce PDF ne contient pas de texte exploitable (document numérisé ou image). "
            "Exportez le bulletin en PDF depuis Excel ou Word plutôt que de le scanner."
        )
    return segments


def zone_depuis_segment(segment: SegmentPdf, balise: str, alignement: str = "centre") -> ZonePdf:
    return ZonePdf(
        page=segment.page, rect=(segment.x0, segment.y0, segment.x1, segment.y1), gabarit="{" + balise + "}",
        alignement=alignement, taille=segment.taille, famille=segment.famille, gras=segment.gras,
        italique=segment.italique, couleur=segment.couleur, ligne_base=segment.ligne_base,
        texte_origine=segment.texte,
    )


# ---------------------------------------------------------------------
# Modèle à balises
# ---------------------------------------------------------------------

@dataclass
class AnalyseBalisesPdf:
    zones: List[ZonePdf] = field(default_factory=list)
    balises: List[str] = field(default_factory=list)   # noms tels qu'écrits
    erreurs: List[str] = field(default_factory=list)


def zones_depuis_balises(contenu: Contenu) -> AnalyseBalisesPdf:
    """
    Repère les lignes contenant des balises {{...}}. Chaque ligne devient
    une zone ; le texte fixe éventuel de la ligne est conservé dans le
    gabarit (ex. « Statut: {{STATUT|centre}} » -> « Statut: {STATUT} »).
    """
    resultat = AnalyseBalisesPdf()
    document = ouvrir(contenu)
    try:
        for numero_page, page in enumerate(document):
            for bloc in page.get_text("dict").get("blocks", []):
                for ligne in bloc.get("lines", []):
                    spans = [s for s in ligne.get("spans", []) if s.get("text", "").strip()]
                    texte = "".join(s["text"] for s in ligne.get("spans", []))
                    if "{{" not in texte and "}}" not in texte:
                        continue
                    correspondances = list(MOTIF_BALISE.finditer(texte))
                    reste = MOTIF_BALISE.sub("", texte)
                    if "{{" in reste or "}}" in reste:
                        resultat.erreurs.append(
                            f"Page {numero_page + 1} : balise incomplète ou coupée sur plusieurs lignes "
                            f"(« {texte.strip()} »). Élargissez la case ou réduisez la taille du texte de la balise."
                        )
                        continue
                    alignement = "gauche"
                    for correspondance in correspondances:
                        nom = correspondance.group(1).upper()
                        if nom not in resultat.balises:
                            resultat.balises.append(nom)
                        option = correspondance.group(2)
                        if option:
                            normalise = normaliser_alignement(option)
                            if not normalise:
                                resultat.erreurs.append(
                                    f"Option d'alignement inconnue « {option} » dans {correspondance.group(0)} "
                                    "(utilisez gauche, centre ou droite)."
                                )
                            else:
                                alignement = normalise

                    def _jeton(m: "re.Match") -> str:
                        canonique = nom_canonique(m.group(1)) or m.group(1).upper()
                        return "{" + canonique + "}"

                    gabarit = MOTIF_BALISE.sub(_jeton, texte).strip()
                    x0 = min(s["bbox"][0] for s in spans)
                    y0 = min(s["bbox"][1] for s in spans)
                    x1 = max(s["bbox"][2] for s in spans)
                    y1 = max(s["bbox"][3] for s in spans)
                    premier = next(s for s in spans if "{{" in s["text"] or "}}" in s["text"]) if spans else None
                    style = _style_span(premier or spans[0])
                    resultat.zones.append(ZonePdf(
                        page=numero_page, rect=(x0, y0, x1, y1), gabarit=gabarit, alignement=alignement,
                        texte_origine=texte.strip(), **style,
                    ))
    finally:
        document.close()
    return resultat


# ---------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------

_POLICES = {
    ("serif", False, False): "Times-Roman", ("serif", True, False): "Times-Bold",
    ("serif", False, True): "Times-Italic", ("serif", True, True): "Times-BoldItalic",
    ("sans", False, False): "Helvetica", ("sans", True, False): "Helvetica-Bold",
    ("sans", False, True): "Helvetica-Oblique", ("sans", True, True): "Helvetica-BoldOblique",
}


def texte_zone(zone: ZonePdf, valeurs: Dict[str, str]) -> str:
    """Texte final d'une zone. Lève PdfExportError si une valeur manque."""
    table = valeurs_par_nom(valeurs)

    def _valeur(m: "re.Match") -> str:
        nom = m.group(1)
        if nom not in table:
            raise PdfExportError(f"Valeur manquante pour la balise {nom}.")
        return table[nom]

    return _MOTIF_JETON.sub(_valeur, zone.gabarit)


def _effacer(document, zones: List[ZonePdf]) -> Dict[int, List[int]]:
    """Efface réellement le texte d'origine de chaque zone (fond, traits et images conservés)."""
    par_page: Dict[int, List[int]] = {}
    for index, zone in enumerate(zones):
        if zone.page >= document.page_count:
            raise PdfExportError("Le modèle PDF a changé : une zone fait référence à une page absente.")
        par_page.setdefault(zone.page, []).append(index)
    for numero_page, indices in par_page.items():
        page = document[numero_page]
        for index in indices:
            x0, y0, x1, y1 = zones[index].rect
            # Légèrement réduit pour ne jamais toucher un caractère voisin.
            page.add_redact_annot(pymupdf.Rect(x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3), fill=False)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
    return par_page


def effacer_zones(contenu_modele: Contenu, zones: List[ZonePdf]) -> bytes:
    """
    Modèle « nettoyé » : les valeurs d'origine (nom, montants...) du
    bulletin envoyé sont effacées avant l'enregistrement du modèle, qui
    ne conserve ainsi aucune donnée personnelle de l'enseignant d'origine.
    """
    document = ouvrir(contenu_modele)
    try:
        _effacer(document, zones)
        return document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()


def generer_pdf(contenu_modele: Contenu, zones: List[ZonePdf], valeurs: Dict[str, str]) -> bytes:
    """Produit le bulletin PDF : zones effacées puis réécrites avec les valeurs."""
    if not zones:
        raise PdfExportError("Le modèle PDF ne définit aucune zone à remplir.")
    textes = [texte_zone(zone, valeurs) for zone in zones]
    document = ouvrir(contenu_modele)
    try:
        for numero_page, indices in _effacer(document, zones).items():
            page = document[numero_page]
            for index in indices:
                _ecrire_zone(page, zones[index], textes[index])
        return document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()


def _ecrire_zone(page, zone: ZonePdf, texte: str) -> None:
    if not texte:
        return
    police = _POLICES[(zone.famille if zone.famille in ("serif", "sans") else "sans", zone.gras, zone.italique)]
    x0, y0, x1, y1 = zone.rect
    largeur = pymupdf.get_text_length(texte, fontname=police, fontsize=zone.taille)
    if zone.alignement == "centre":
        x = (x0 + x1) / 2 - largeur / 2
    elif zone.alignement == "droite":
        x = x1 - largeur
    else:
        x = x0
    ligne_base = zone.ligne_base if zone.ligne_base else y1 - zone.taille * 0.22
    page.insert_text((x, ligne_base), texte, fontname=police, fontsize=zone.taille, color=zone.couleur)


def apercu_png(contenu_pdf: Contenu, zoom: float = 1.6) -> bytes:
    """Image PNG de la première page (aperçu dans l'interface)."""
    document = ouvrir(contenu_pdf)
    try:
        return document[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
    finally:
        document.close()
