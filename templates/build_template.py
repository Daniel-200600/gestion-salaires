"""
Construction des modèles de bulletin STANDARD.

Script exécuté une seule fois par le développeur (jamais par
l'application à l'exécution) : il produit

- templates/bulletin_template.docx : modèle Word standard ;
- templates/bulletin_modele_standard.pdf (+ .json) : le même bulletin
  en PDF, obtenu en convertissant par LibreOffice le bulletin rempli
  avec les valeurs d'exemple ; les zones à remplacer sont décrites dans
  le fichier .json (``python templates/build_template.py --pdf``,
  LibreOffice requis sur le poste du développeur seulement).

La mise en page reproduit exactement le bulletin officiel fourni par
l'établissement : mêmes positions de colonnes,
mêmes hauteurs de lignes, mêmes couleurs (vert #00B050, jaune #FFFF00),
mêmes polices (Times New Roman gras 11, en-tête 7 et 9 points,
signature Arial gras), logo de l'établissement au centre de l'en-tête,
mois en anglais, montants sans séparateur de milliers, montant net en
lettres (anglais), zone « Fait à Yaoundé le : » laissée vierge pour la
date et la signature manuscrites.

Toutes les dimensions ci-dessous sont relevées sur le PDF officiel, en
points typographiques (1 pt = 1/72 pouce).

Les balises {{...}} sont écrites chacune dans un run isolé : le
remplacement de exports/word_export.py conserve ainsi la mise en forme.
Les balises utilisées par le modèle Word sont les balises historiques
de l'application (compatibilité avec les tests et les valeurs
préparées par services/bulletin_service.py).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from config.settings import (
    ETABLISSEMENT_ENTETE_EN,
    ETABLISSEMENT_ENTETE_FR,
    LIEU_SIGNATURE,
    LOGO_ETABLISSEMENT_PATH,
    MODELES_ETABLISSEMENT_DIR,
    TITRE_SIGNATAIRE_EN,
    TITRE_SIGNATAIRE_FR,
)

DOSSIER = Path(__file__).resolve().parent
CHEMIN_TEMPLATE = DOSSIER / "bulletin_template.docx"
CHEMIN_MODELE_PDF = DOSSIER / "bulletin_modele_standard.pdf"
CHEMIN_ZONES_PDF = DOSSIER / "bulletin_modele_standard.json"

# Par défaut : modèles NEUTRES livrés avec le dépôt (en-tête de
# config/settings.py, sans logo). Avec --etablissement : en-tête et logo
# lus dans config/etablissement_local.py (fichier local, exclu de Git) et
# modèles écrits dans data/modeles_etablissement/, utilisés en priorité
# par l'application (config.settings.chemin_modele_standard).
ENTETE_FR, ENTETE_EN, LOGO = ETABLISSEMENT_ENTETE_FR, ETABLISSEMENT_ENTETE_EN, None


def utiliser_version_etablissement() -> None:
    global ENTETE_FR, ENTETE_EN, LOGO, CHEMIN_TEMPLATE, CHEMIN_MODELE_PDF, CHEMIN_ZONES_PDF
    try:
        from config import etablissement_local as local
    except ImportError as erreur:
        raise RuntimeError(
            "config/etablissement_local.py est introuvable : copiez config/etablissement_local.example.py "
            "et renseignez l'en-tête de l'établissement."
        ) from erreur
    ENTETE_FR, ENTETE_EN = local.ETABLISSEMENT_ENTETE_FR, local.ETABLISSEMENT_ENTETE_EN
    LOGO = Path(getattr(local, "LOGO_ETABLISSEMENT_PATH", LOGO_ETABLISSEMENT_PATH))
    MODELES_ETABLISSEMENT_DIR.mkdir(parents=True, exist_ok=True)
    CHEMIN_TEMPLATE = MODELES_ETABLISSEMENT_DIR / CHEMIN_TEMPLATE.name
    CHEMIN_MODELE_PDF = MODELES_ETABLISSEMENT_DIR / CHEMIN_MODELE_PDF.name
    CHEMIN_ZONES_PDF = MODELES_ETABLISSEMENT_DIR / CHEMIN_ZONES_PDF.name

# Champs remplis par le modèle PDF standard (identiques à ceux du modèle Word).
BALISES_MODELE_PDF_STANDARD = (
    "PERIODE", "NOM_COMPLET", "STATUT", "TOTAL_HEURES", "TAUX_HORAIRE", "GAIN_HEURES", "PRIME_AP_PP",
    "SURVEILLANCE_SECRETARIAT", "INDEMNITE_SUGGESTION_ADMIN", "TAXE", "RETENUE_AMICALE", "DETTE",
    "TOTAL_GAINS", "TOTAL_RETENUES", "NET_EN_LETTRES", "NET_A_PAYER",
)

VERT = "00B050"
JAUNE = "FFFF00"
NOIR = "000000"
POLICE = "Times New Roman"
POLICE_SIGNATURE = "Arial"

# Largeurs des 7 colonnes de la grille (pt), relevées sur le modèle :
# S/N | désignation (début) | désignation | heures | taux / GAINS | gains | RETENUES
LARGEURS = [47.1, 44.9, 185.9, 52.2, 52.1, 52.3, 93.8]
TRAIT_EPAIS = 12  # huitièmes de point (1,5 pt)
TRAIT_FIN = 6


# ---------------------------------------------------------------------
# Balises selon la variante
# ---------------------------------------------------------------------

def _balises(variante: str) -> dict:
    """
    Variante "word"    : balises historiques (un run par balise).
    Variante "exemple" : bulletin rempli avec les valeurs d'exemple
    (utils/balises_bulletin.py) ; sert de base au modèle PDF standard, dont les zones
    à remplacer sont repérées par la même détection automatique que
    pour un bulletin importé par l'administrateur.
    """
    if variante == "word":
        return {
            "PERIODE": ["{{PERIODE}}"], "NOM": ["{{NOM}}", " ", "{{PRENOM}}"], "STATUT": ["Statut: ", "{{STATUT}}"],
            "TOTAL_HEURES": "{{TOTAL_HEURES}}", "TAUX_HORAIRE": "{{TAUX_HORAIRE}}", "GAIN_HEURES": "{{GAIN_HEURES}}",
            "PRIME_AP_PP": "{{PRIME_AP_PP}}", "SURVEILLANCE_SECRETARIAT": "{{SURVEILLANCE_SECRETARIAT}}",
            "INDEMNITE_SUGGESTION_ADMIN": "{{INDEMNITE_SUGGESTION_ADMIN}}", "TAXE": "{{TAXE_5}}",
            "RETENUE_AMICALE": "{{RETENUE_AMICALE}}", "DETTE": "{{DETTE}}", "TOTAL_GAINS": "{{TOTAL_GAINS}}",
            "TOTAL_RETENUES": "{{TOTAL_RETENUES}}", "NET_EN_LETTRES": "{{NET_EN_LETTRES}}",
            "NET_A_PAYER": "{{NET_A_PERÇEVOIR}}",
        }
    if variante == "exemple":
        from utils.balises_bulletin import valeurs_exemple
        v = valeurs_exemple()
        return {
            "PERIODE": [v["PERIODE"]], "NOM": [v["NOM_COMPLET"]], "STATUT": [f"Statut: {v['STATUT']}"],
            **{cle: v[cle] for cle in ("TOTAL_HEURES", "TAUX_HORAIRE", "GAIN_HEURES", "PRIME_AP_PP",
                                       "SURVEILLANCE_SECRETARIAT", "INDEMNITE_SUGGESTION_ADMIN", "TAXE",
                                       "RETENUE_AMICALE", "DETTE", "TOTAL_GAINS", "TOTAL_RETENUES",
                                       "NET_EN_LETTRES", "NET_A_PAYER")},
        }
    raise ValueError(f"Variante inconnue : {variante}")


# ---------------------------------------------------------------------
# Aides XML (python-docx n'expose pas ces réglages)
# ---------------------------------------------------------------------

def _sous_element(parent, balise: str):
    element = parent.find(qn(balise))
    if element is None:
        element = OxmlElement(balise)
        parent.append(element)
    return element


def _ombrer(cellule, couleur: str) -> None:
    tcPr = cellule._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), couleur)
    tcPr.append(shd)


def _bordures_cellule(cellule, **cotes) -> None:
    """cotes : top/bottom/left/right = taille en huitièmes de point, ou 0 pour aucun trait."""
    tcPr = cellule._tc.get_or_add_tcPr()
    borders = _sous_element(tcPr, "w:tcBorders")
    for cote, taille in cotes.items():
        element = borders.find(qn(f"w:{cote}"))
        if element is None:
            element = OxmlElement(f"w:{cote}")
            borders.append(element)
        if taille:
            element.set(qn("w:val"), "single")
            element.set(qn("w:sz"), str(taille))
            element.set(qn("w:space"), "0")
            element.set(qn("w:color"), NOIR)
        else:
            element.set(qn("w:val"), "nil")


def _bordures_tableau(table, exterieur: int) -> None:
    tblPr = table._tbl.tblPr
    borders = _sous_element(tblPr, "w:tblBorders")
    for cote in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{cote}")
        if exterieur and cote in ("top", "left", "bottom", "right"):
            element.set(qn("w:val"), "single")
            element.set(qn("w:sz"), str(exterieur))
            element.set(qn("w:space"), "0")
            element.set(qn("w:color"), NOIR)
        else:
            element.set(qn("w:val"), "nil")
        borders.append(element)


def _grille_fixe(table, largeurs_pt) -> None:
    """Largeurs de colonnes exactes et disposition fixe (Word ne redimensionne pas)."""
    tblPr = table._tbl.tblPr
    layout = _sous_element(tblPr, "w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    largeur_totale = _sous_element(tblPr, "w:tblW")
    largeur_totale.set(qn("w:w"), str(int(round(sum(largeurs_pt) * 20))))
    largeur_totale.set(qn("w:type"), "dxa")
    marges = _sous_element(tblPr, "w:tblCellMar")
    for cote, valeur in (("top", 0), ("bottom", 0), ("left", 20), ("right", 20)):
        element = OxmlElement(f"w:{cote}")
        element.set(qn("w:w"), str(valeur))
        element.set(qn("w:type"), "dxa")
        marges.append(element)
    grille = table._tbl.tblGrid
    for colonne, largeur in zip(grille.findall(qn("w:gridCol")), largeurs_pt):
        colonne.set(qn("w:w"), str(int(round(largeur * 20))))
    for ligne in table.rows:
        for cellule, largeur in zip(ligne.cells, largeurs_pt):
            cellule.width = Pt(largeur)


def _hauteur(ligne, hauteur_pt: float, exacte: bool = True) -> None:
    trPr = ligne._tr.get_or_add_trPr()
    element = OxmlElement("w:trHeight")
    element.set(qn("w:val"), str(int(round(hauteur_pt * 20))))
    element.set(qn("w:hRule"), "exact" if exacte else "atLeast")
    trPr.append(element)


def _fusion(table, ligne: int, debut: int, fin: int):
    return table.cell(ligne, debut) if debut == fin else table.cell(ligne, debut).merge(table.cell(ligne, fin))


def _paragraphe_compact(paragraphe, alignement=WD_ALIGN_PARAGRAPH.CENTER) -> None:
    paragraphe.alignment = alignement
    format_ = paragraphe.paragraph_format
    format_.space_before = Pt(0)
    format_.space_after = Pt(0)
    format_.line_spacing_rule = WD_LINE_SPACING.SINGLE


def _ecrire(cellule, morceaux, taille: float = 11, gras: bool = True, italique: bool = False,
            alignement=WD_ALIGN_PARAGRAPH.CENTER, vertical=WD_CELL_VERTICAL_ALIGNMENT.CENTER,
            police: str = POLICE, retrait_gauche: float = 0, retrait_droit: float = 0) -> None:
    """Écrit un paragraphe dans la cellule ; chaque morceau (texte ou balise) est un run distinct."""
    if isinstance(morceaux, str):
        morceaux = [morceaux]
    cellule.text = ""
    cellule.vertical_alignment = vertical
    paragraphe = cellule.paragraphs[0]
    _paragraphe_compact(paragraphe, alignement)
    if retrait_gauche:
        paragraphe.paragraph_format.left_indent = Pt(retrait_gauche)
    if retrait_droit:
        paragraphe.paragraph_format.right_indent = Pt(retrait_droit)
    for morceau in morceaux:
        run = paragraphe.add_run(morceau)
        run.bold = gras
        run.italic = italique
        run.font.size = Pt(taille)
        run.font.name = police
        run._element.rPr.rFonts.set(qn("w:eastAsia"), police)
        run.font.color.rgb = RGBColor.from_string(NOIR)


# ---------------------------------------------------------------------
# En-tête institutionnel (tableau imbriqué : FR | logo | EN)
# ---------------------------------------------------------------------

def _texte_entete(cellule, lignes, retrait_gauche: float, retrait_droit: float) -> None:
    cellule.text = ""
    cellule.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    for index, (texte, taille, italique) in enumerate(lignes):
        paragraphe = cellule.paragraphs[0] if index == 0 else cellule.add_paragraph()
        _paragraphe_compact(paragraphe)
        paragraphe.paragraph_format.left_indent = Pt(retrait_gauche)
        paragraphe.paragraph_format.right_indent = Pt(retrait_droit)
        if index == 0:
            paragraphe.paragraph_format.space_before = Pt(7)
        run = paragraphe.add_run(texte)
        run.bold = True
        run.italic = italique
        run.font.size = Pt(taille)
        run.font.name = POLICE


def _lignes_entete(textes, francais: bool):
    lignes = []
    for texte in textes:
        devise = "Paix" in texte or "Peace" in texte
        grande = francais and (devise or texte.startswith("REGION"))
        lignes.append((texte, 9 if grande else 7, devise))
    return lignes


def _entete(cellule) -> None:
    cellule.text = ""
    _paragraphe_compact(cellule.paragraphs[0])
    cellule.paragraphs[0].paragraph_format.line_spacing = Pt(1)
    imbrique = cellule.add_table(rows=1, cols=3)
    largeurs = [212.1, 110.0, 206.2]
    _bordures_tableau(imbrique, exterieur=0)
    _grille_fixe(imbrique, largeurs)
    _texte_entete(imbrique.cell(0, 0), _lignes_entete(ENTETE_FR, True), 16, 16)
    _texte_entete(imbrique.cell(0, 2), _lignes_entete(ENTETE_EN, False), 25, 26)
    cellule_logo = imbrique.cell(0, 1)
    cellule_logo.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    paragraphe = cellule_logo.paragraphs[0]
    _paragraphe_compact(paragraphe)
    if LOGO is not None and LOGO.exists():
        paragraphe.add_run().add_picture(str(LOGO), width=Pt(101.5), height=Pt(73.8))


# ---------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------

def construire_document(variante: str = "word") -> Document:
    b = _balises(variante)
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Pt(89.7)
    section.bottom_margin = Cm(1.0)
    marge = (Cm(21.0).pt - sum(LARGEURS)) / 2
    section.left_margin = Pt(marge)
    section.right_margin = Pt(marge)

    normal = document.styles["Normal"]
    normal.font.name = POLICE
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)

    # Le document ne contient qu'un tableau : on retire le paragraphe vide initial
    # après coup (Word impose un paragraphe final, réduit à 1 pt).
    table = document.add_table(rows=19, cols=7)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _bordures_tableau(table, exterieur=TRAIT_EPAIS)
    _grille_fixe(table, LARGEURS)

    # 0. En-tête institutionnel ---------------------------------------
    _hauteur(table.rows[0], 80.2)
    c = _fusion(table, 0, 0, 6)
    _entete(c)
    _bordures_cellule(c, bottom=TRAIT_EPAIS)

    # 1. BULLETIN DE SOLDE / PAYSLIP | mois -----------------------------
    _hauteur(table.rows[1], 14.4)
    _fusionner_ligne_en_deux(table, 1, 4)
    gauche, droite = table.cell(1, 0), table.cell(1, 4)
    _ecrire(gauche, "BULLETIN DE SOLDE / PAYSLIP")
    _ecrire(droite, b["PERIODE"])
    for cellule in (gauche, droite):
        _ombrer(cellule, VERT)
        _bordures_cellule(cellule, top=TRAIT_EPAIS, bottom=TRAIT_EPAIS)
    _bordures_cellule(gauche, right=TRAIT_EPAIS)
    _bordures_cellule(droite, left=TRAIT_EPAIS)

    # 2. Nom | Statut (jaune) ------------------------------------------
    _hauteur(table.rows[2], 33.3)
    _fusionner_ligne_en_deux(table, 2, 3)
    gauche, droite = table.cell(2, 0), table.cell(2, 3)
    _ecrire(gauche, b["NOM"])
    _ecrire(droite, b["STATUT"])
    for cellule in (gauche, droite):
        _ombrer(cellule, JAUNE)
        _bordures_cellule(cellule, top=TRAIT_EPAIS, bottom=TRAIT_EPAIS)
    _bordures_cellule(gauche, right=TRAIT_EPAIS)
    _bordures_cellule(droite, left=TRAIT_EPAIS)

    # 3. Bande jaune vide ---------------------------------------------
    _hauteur(table.rows[3], 14.4)
    c = _fusion(table, 3, 0, 6)
    _ecrire(c, "")
    _ombrer(c, JAUNE)
    _bordures_cellule(c, top=TRAIT_EPAIS, bottom=TRAIT_EPAIS)

    # 4. ELEMENTS DE RENUMERATION / SALARY RUBRICS | MONTANT / AMOUNT ----
    _hauteur(table.rows[4], 14.4)
    _fusionner_ligne_en_deux(table, 4, 4)
    gauche, droite = table.cell(4, 0), table.cell(4, 4)
    _ecrire(gauche, "ELEMENTS DE RENUMERATION / SALARY RUBRICS")
    _ecrire(droite, "MONTANT / AMOUNT")
    for cellule in (gauche, droite):
        _ombrer(cellule, VERT)
        _bordures_cellule(cellule, top=TRAIT_EPAIS, bottom=TRAIT_EPAIS)
    _bordures_cellule(gauche, right=TRAIT_EPAIS)
    _bordures_cellule(droite, left=TRAIT_EPAIS)

    # 5. En-têtes de colonnes -------------------------------------------
    _hauteur(table.rows[5], 14.1)
    _ecrire(table.cell(5, 0), "S/N")
    designation = _fusion(table, 5, 1, 3)
    _ecrire(designation, "DESIGNATION", alignement=WD_ALIGN_PARAGRAPH.LEFT, retrait_gauche=139.0)
    _ecrire(table.cell(5, 4), "GAINS")
    _ecrire(table.cell(5, 5), "")
    _ecrire(table.cell(5, 6), "RETENUES")
    for index in range(7):
        _bordures_cellule(table.cell(5, index), top=TRAIT_EPAIS, bottom=TRAIT_FIN)

    # 6-12. Rubriques ---------------------------------------------------
    rubriques = [
        ("1", "Gain Heures / Hourly Wage", {3: b["TOTAL_HEURES"], 4: b["TAUX_HORAIRE"], 5: b["GAIN_HEURES"]}, 4.0),
        ("2", "Prime AP/PP / Incentive HOD/CM", {5: b["PRIME_AP_PP"]}, 0),
        ("3", "Surveillance/Secretariat / Invigilation", {5: b["SURVEILLANCE_SECRETARIAT"]}, 0),
        ("4", "Indemnite Suggestion / Duty Post Allowance", {5: b["INDEMNITE_SUGGESTION_ADMIN"]}, 0),
        ("5", "Taxe / Tax", {6: b["TAXE"]}, 0),
        ("6", "Retenue Amicale / Social Deduction", {6: b["RETENUE_AMICALE"]}, 0),
        ("7", "Dette / Debt", {6: b["DETTE"]}, 0),
    ]
    haut = WD_CELL_VERTICAL_ALIGNMENT.TOP
    for decalage, (numero, libelle, montants, retrait) in enumerate(rubriques):
        indice = 6 + decalage
        _hauteur(table.rows[indice], 27.3)
        _ecrire(table.cell(indice, 0), numero, vertical=haut)
        cellule_libelle = _fusion(table, indice, 1, 2)
        _ecrire(cellule_libelle, libelle, alignement=WD_ALIGN_PARAGRAPH.LEFT, vertical=haut, retrait_gauche=retrait)
        for colonne in range(3, 7):
            _ecrire(table.cell(indice, colonne), montants.get(colonne, ""), vertical=haut)

    # 13. Total ----------------------------------------------------------
    _hauteur(table.rows[13], 14.4)
    etiquette = _fusion(table, 13, 0, 1)
    vide = _fusion(table, 13, 2, 3)
    total_gains = _fusion(table, 13, 4, 5)
    total_retenues = table.cell(13, 6)
    _ecrire(etiquette, "Total")
    _ecrire(vide, "")
    _ecrire(total_gains, b["TOTAL_GAINS"])
    _ecrire(total_retenues, b["TOTAL_RETENUES"])
    for cellule in (etiquette, vide, total_gains, total_retenues):
        _ombrer(cellule, VERT)
        _bordures_cellule(cellule, top=TRAIT_EPAIS, bottom=TRAIT_EPAIS)
    _bordures_cellule(vide, right=TRAIT_EPAIS)
    _bordures_cellule(total_gains, left=TRAIT_EPAIS, right=TRAIT_EPAIS)
    _bordures_cellule(total_retenues, left=TRAIT_EPAIS)

    # 14. NET A PAYER ----------------------------------------------------
    _hauteur(table.rows[14], 14.4)
    etiquette = _fusion(table, 14, 0, 1)
    lettres = _fusion(table, 14, 2, 4)
    montant = _fusion(table, 14, 5, 6)
    _ecrire(etiquette, "NET A PAYER")
    _ecrire(lettres, b["NET_EN_LETTRES"], taille=10)
    _ecrire(montant, b["NET_A_PAYER"])
    for cellule in (etiquette, lettres, montant):
        _ombrer(cellule, VERT)
        _bordures_cellule(cellule, top=TRAIT_EPAIS, bottom=TRAIT_EPAIS)
    _bordures_cellule(etiquette, right=TRAIT_EPAIS)
    _bordures_cellule(lettres, left=TRAIT_EPAIS, right=TRAIT_EPAIS)
    _bordures_cellule(montant, left=TRAIT_EPAIS)

    # 15. Fait à ... le : (vierge : date et signature manuscrites) -------
    _hauteur(table.rows[15], 14.0)
    _ecrire(table.cell(15, 0), "")
    cellule_lieu = _fusion(table, 15, 1, 6)
    _ecrire(cellule_lieu, f"Done at {LIEU_SIGNATURE} on the / Fait à {LIEU_SIGNATURE} le:",
            vertical=WD_CELL_VERTICAL_ALIGNMENT.TOP)
    _bordures_cellule(table.cell(15, 0), top=TRAIT_EPAIS)
    _bordures_cellule(cellule_lieu, top=TRAIT_EPAIS)

    # 16. Espace de signature ---------------------------------------------
    _hauteur(table.rows[16], 54.8)
    _ecrire(_fusion(table, 16, 0, 6), "")

    # 17. Titre du signataire ----------------------------------------------
    _hauteur(table.rows[17], 13.8)
    _ecrire(_fusion(table, 17, 0, 6), TITRE_SIGNATAIRE_FR + TITRE_SIGNATAIRE_EN,
            alignement=WD_ALIGN_PARAGRAPH.RIGHT, police=POLICE_SIGNATURE, retrait_droit=34.0)

    # 18. Marge basse du cadre ---------------------------------------------
    _hauteur(table.rows[18], 14.5)
    _ecrire(_fusion(table, 18, 0, 6), "")

    # Paragraphe final imposé par Word : réduit au minimum.
    dernier = document.paragraphs[-1] if document.paragraphs else document.add_paragraph()
    _paragraphe_compact(dernier)
    dernier.paragraph_format.line_spacing = Pt(1)
    return document


def _fusionner_ligne_en_deux(table, ligne: int, colonne_coupure: int) -> None:
    """Fusionne une ligne en deux cellules : [0 .. coupure-1] et [coupure .. 6]."""
    _fusion(table, ligne, 0, colonne_coupure - 1)
    _fusion(table, ligne, colonne_coupure, 6)


def construire_template() -> Path:
    """Construit templates/bulletin_template.docx (modèle Word standard)."""
    construire_document("word").save(CHEMIN_TEMPLATE)
    return CHEMIN_TEMPLATE


def construire_modele_pdf() -> Path:
    """
    Construit templates/bulletin_modele_standard.pdf et sa description
    templates/bulletin_modele_standard.json.

    Le PDF est le bulletin standard rempli avec les valeurs du bulletin
    officiel (variante « exemple »), converti par LibreOffice. Les zones
    à remplacer sont repérées par la détection automatique utilisée pour
    les bulletins importés (utils/detection_bulletin.py) ; toutes les
    balises attendues doivent être trouvées, sinon la construction échoue.

    Réservé au développeur : LibreOffice n'est pas requis sur le poste
    de l'établissement, les deux fichiers produits sont livrés avec
    l'application.
    """
    import json

    from exports import pdf_export
    from utils.detection_bulletin import suggerer_correspondances

    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable is None:
        candidat = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LibreOffice" / "program" / "soffice.exe"
        executable = str(candidat) if candidat.exists() else None
    if executable is None:
        raise RuntimeError("LibreOffice est nécessaire pour construire le modèle PDF standard.")
    with tempfile.TemporaryDirectory() as dossier:
        source = Path(dossier) / "bulletin_modele_standard.docx"
        construire_document("exemple").save(source)
        subprocess.run(
            [executable, "--headless", "--convert-to", "pdf", "--outdir", dossier, str(source)],
            check=True, capture_output=True, timeout=180,
        )
        contenu = (Path(dossier) / "bulletin_modele_standard.pdf").read_bytes()

    segments = pdf_export.segments_pdf(contenu)
    propositions = suggerer_correspondances(segments)
    attendues = set(BALISES_MODELE_PDF_STANDARD)
    trouvees = set(propositions.values())
    if trouvees != attendues:
        raise RuntimeError(f"Détection incomplète du modèle standard : manquent {sorted(attendues - trouvees)}")
    zones = [pdf_export.zone_depuis_segment(s, propositions[s.id]).to_dict() for s in segments if s.id in propositions]
    CHEMIN_MODELE_PDF.write_bytes(contenu)
    CHEMIN_ZONES_PDF.write_text(json.dumps(zones, ensure_ascii=False, indent=1), encoding="utf-8")
    return CHEMIN_MODELE_PDF


if __name__ == "__main__":
    if "--etablissement" in sys.argv:
        utiliser_version_etablissement()
    print(f"Modèle Word créé : {construire_template()}")
    if "--pdf" in sys.argv:
        print(f"Modèle PDF créé : {construire_modele_pdf()}")
