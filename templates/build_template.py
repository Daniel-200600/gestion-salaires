"""
Script de construction UNIQUE du template templates/bulletin_template.docx.

Ce script n'est PAS appelé par l'application à l'exécution : il sert à
créer (ou reconstruire volontairement) le template une seule fois. Le
service exports/word_export.py se contente ensuite de CHARGER ce
fichier existant et d'y injecter les valeurs — il ne reconstruit
jamais la mise en page à chaque génération.

Reconstruit la structure d'un bulletin de solde d'établissement scolaire
camerounais : en-tête bilingue (lignes définies dans config/settings.py),
barre de titre BULLETIN DE SOLDE / PAYSLIP, bloc
nom/statut, tableau des rubriques (gains/retenues), ligne Total, ligne
NET A PAYER avec montant en lettres, bloc signature.

Les placeholders {{...}} sont insérés comme des runs Word isolés
(un placeholder = un run entier), afin que le remplacement dans
exports/word_export.py soit fiable sans avoir à gérer des runs
fragmentés (ce piège ne concerne que les documents édités
manuellement dans Word, pas un document généré par ce script).

Le logo de l'établissement n'est pas disponible comme fichier image
dans les données de l'application : l'espace qui lui est réservé dans
l'en-tête est conservé (cellule centrale), mais reste vide plutôt que
d'inventer un graphique. Un chemin d'image pourra être ajouté plus
tard via configuration si le fichier du logo est fourni.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from config.settings import (
    ETABLISSEMENT_ENTETE_EN,
    ETABLISSEMENT_ENTETE_FR,
    LIEU_SIGNATURE,
    TITRE_SIGNATAIRE_EN,
    TITRE_SIGNATAIRE_FR,
)

CHEMIN_TEMPLATE = Path(__file__).resolve().parent / "bulletin_template.docx"

VERT_BARRE = "1F7A3D"
JAUNE_BARRE = "FFFF00"
BLANC = "FFFFFF"
NOIR = "000000"


def _ombrer_cellule(cellule, couleur_hex: str) -> None:
    """Colore le fond d'une cellule de tableau (python-docx n'a pas d'API haut niveau pour cela)."""
    tcPr = cellule._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), couleur_hex)
    tcPr.append(shd)


def _texte_cellule(
    cellule, texte: str, gras: bool = False, italique: bool = False,
    taille: int = 10, couleur: str = NOIR, centre: bool = True,
    police: str = "Times New Roman",
) -> None:
    """Remplace le contenu d'une cellule par un unique run (placeholder-safe)."""
    cellule.text = ""
    paragraphe = cellule.paragraphs[0]
    paragraphe.alignment = WD_ALIGN_PARAGRAPH.CENTER if centre else WD_ALIGN_PARAGRAPH.LEFT
    run = paragraphe.add_run(texte)
    run.bold = gras
    run.italic = italique
    run.font.size = Pt(taille)
    run.font.name = police
    run.font.color.rgb = RGBColor.from_string(couleur)


def _ajouter_ligne_entete_institution(cellule, lignes: list) -> None:
    """Écrit plusieurs lignes (texte, gras, italique) dans une cellule d'en-tête institutionnelle."""
    cellule.text = ""
    for index, (texte, gras, italique) in enumerate(lignes):
        paragraphe = cellule.paragraphs[0] if index == 0 else cellule.add_paragraph()
        paragraphe.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraphe.add_run(texte)
        run.bold = gras
        run.italic = italique
        run.font.size = Pt(8.5)
        run.font.name = "Times New Roman"


def _fusionner_ligne(table, ligne: int, col_debut: int, col_fin: int):
    return table.cell(ligne, col_debut).merge(table.cell(ligne, col_fin))


def _ajouter_bordure_page(section) -> None:
    """
    Ajoute une bordure autour de chaque page (non exposé par l'API
    haut niveau de python-docx : XML brut requis). Le modèle officiel
    présente le bulletin encadré par une bordure fine.
    """
    sectPr = section._sectPr
    pgBorders = OxmlElement("w:pgBorders")
    pgBorders.set(qn("w:offsetFrom"), "page")
    for cote in ("top", "left", "bottom", "right"):
        bordure = OxmlElement(f"w:{cote}")
        bordure.set(qn("w:val"), "single")
        bordure.set(qn("w:sz"), "12")
        bordure.set(qn("w:space"), "24")
        bordure.set(qn("w:color"), "000000")
        pgBorders.append(bordure)
    sectPr.append(pgBorders)


def construire_template() -> Path:
    document = Document()

    section = document.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(1.2)
    section.bottom_margin = Cm(1.2)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    _ajouter_bordure_page(section)

    style_normal = document.styles["Normal"]
    style_normal.font.name = "Times New Roman"
    style_normal.font.size = Pt(10)

    # -------------------------------------------------------------
    # En-tête institutionnelle bilingue (3 colonnes : FR | logo | EN)
    # -------------------------------------------------------------
    table_entete = document.add_table(rows=1, cols=3)
    table_entete.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_entete.columns[0].width = Cm(7.5)
    table_entete.columns[1].width = Cm(3.0)
    table_entete.columns[2].width = Cm(7.5)

    lignes_francais = [(texte, True, "Paix" in texte or "Peace" in texte) for texte in ETABLISSEMENT_ENTETE_FR]
    lignes_anglais = [(texte, True, "Paix" in texte or "Peace" in texte) for texte in ETABLISSEMENT_ENTETE_EN]
    _ajouter_ligne_entete_institution(table_entete.cell(0, 0), lignes_francais)
    # Cellule centrale réservée au logo : volontairement vide (cf. docstring du module).
    table_entete.cell(0, 1).text = ""
    _ajouter_ligne_entete_institution(table_entete.cell(0, 2), lignes_anglais)

    document.add_paragraph()  # espacement

    # -------------------------------------------------------------
    # Barre de titre : BULLETIN DE SOLDE / PAYSLIP | Période
    # -------------------------------------------------------------
    table_titre = document.add_table(rows=1, cols=2)
    table_titre.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_titre.columns[0].width = Cm(12.0)
    table_titre.columns[1].width = Cm(6.0)
    _texte_cellule(table_titre.cell(0, 0), "BULLETIN DE SOLDE / PAYSLIP", gras=True, taille=11, couleur=BLANC, centre=False)
    _texte_cellule(table_titre.cell(0, 1), "{{PERIODE}}", gras=True, taille=11, couleur=BLANC)
    for cellule in table_titre.rows[0].cells:
        _ombrer_cellule(cellule, VERT_BARRE)

    # -------------------------------------------------------------
    # Bloc identité : Nom Prénom | Statut
    # -------------------------------------------------------------
    table_identite = document.add_table(rows=1, cols=2)
    table_identite.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_identite.columns[0].width = Cm(12.0)
    table_identite.columns[1].width = Cm(6.0)
    cellule_nom = table_identite.cell(0, 0)
    cellule_nom.text = ""
    p_nom = cellule_nom.paragraphs[0]
    p_nom.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for jeton in ("{{NOM}}", " ", "{{PRENOM}}"):
        run = p_nom.add_run(jeton)
        run.bold = True
        run.font.size = Pt(11)
        run.font.name = "Times New Roman"
    _texte_cellule(table_identite.cell(0, 1), "Statut: {{STATUT}}", gras=True, taille=11)
    for cellule in table_identite.rows[0].cells:
        _ombrer_cellule(cellule, JAUNE_BARRE)

    document.add_paragraph()

    # -------------------------------------------------------------
    # Tableau des rubriques : S/N | DESIGNATION | GAINS | RETENUES
    # -------------------------------------------------------------
    table_rubriques = document.add_table(rows=0, cols=4)
    table_rubriques.style = "Table Grid"
    table_rubriques.alignment = WD_TABLE_ALIGNMENT.CENTER
    largeurs = [Cm(1.3), Cm(9.5), Cm(3.6), Cm(3.6)]

    def _nouvelle_ligne():
        ligne = table_rubriques.add_row()
        for cellule, largeur in zip(ligne.cells, largeurs):
            cellule.width = largeur
        return ligne

    # -- En-tête large "ELEMENTS DE RENUMERATION / SALARY RUBRICS" | "MONTANT / AMOUNT"
    ligne_bandeau = _nouvelle_ligne()
    cellule_gauche = _fusionner_ligne(table_rubriques, 0, 0, 1)
    _texte_cellule(cellule_gauche, "ELEMENTS DE RENUMERATION / SALARY RUBRICS", gras=True, taille=10, couleur=BLANC, centre=False)
    cellule_droite = _fusionner_ligne(table_rubriques, 0, 2, 3)
    _texte_cellule(cellule_droite, "MONTANT / AMOUNT", gras=True, taille=10, couleur=BLANC)
    for cellule in (cellule_gauche, cellule_droite):
        _ombrer_cellule(cellule, VERT_BARRE)

    # -- En-tête de colonnes
    _nouvelle_ligne()
    entetes_colonnes = ["S/N", "DESIGNATION", "GAINS", "RETENUES"]
    for index, texte in enumerate(entetes_colonnes):
        _texte_cellule(table_rubriques.cell(1, index), texte, gras=True, taille=9)

    # -- Lignes de rubriques (S/N, désignation, gains, retenues)
    rubriques = [
        ("1", "Gain Heures / Hourly Wage", "{{TOTAL_HEURES}}   {{TAUX_HORAIRE}}   {{GAIN_HEURES}}", ""),
        ("2", "Prime AP/PP / Incentive HOD/CM", "{{PRIME_AP_PP}}", ""),
        ("3", "Surveillance/Secretariat / Invigilation", "{{SURVEILLANCE_SECRETARIAT}}", ""),
        ("4", "Indemnite Suggestion / Duty Post Allowance", "{{INDEMNITE_SUGGESTION_ADMIN}}", ""),
        ("5", "Taxe / Tax", "", "{{TAXE_5}}"),
        ("6", "Retenue Amicale / Social Deduction", "", "{{RETENUE_AMICALE}}"),
        ("7", "Dette / Debt", "", "{{DETTE}}"),
    ]
    for sn, designation, gains, retenues in rubriques:
        _nouvelle_ligne()
        indice = table_rubriques.rows.__len__() - 1
        _texte_cellule(table_rubriques.cell(indice, 0), sn, taille=9)
        _texte_cellule(table_rubriques.cell(indice, 1), designation, taille=9, centre=False, gras=True)
        _texte_cellule(table_rubriques.cell(indice, 2), gains, taille=9)
        _texte_cellule(table_rubriques.cell(indice, 3), retenues, taille=9)

    # -- Ligne Total (agrégat déjà calculé, cf. services/bulletin_service.py)
    _nouvelle_ligne()
    indice_total = table_rubriques.rows.__len__() - 1
    cellule_label_total = _fusionner_ligne(table_rubriques, indice_total, 0, 1)
    _texte_cellule(cellule_label_total, "Total", gras=True, taille=9, couleur=BLANC, centre=False)
    _ombrer_cellule(cellule_label_total, VERT_BARRE)
    cellule_total_gains = table_rubriques.cell(indice_total, 2)
    _texte_cellule(cellule_total_gains, "{{TOTAL_GAINS}}", gras=True, taille=9, couleur=BLANC)
    _ombrer_cellule(cellule_total_gains, VERT_BARRE)
    cellule_total_retenues = table_rubriques.cell(indice_total, 3)
    _texte_cellule(cellule_total_retenues, "{{TOTAL_RETENUES}}", gras=True, taille=9, couleur=BLANC)
    _ombrer_cellule(cellule_total_retenues, VERT_BARRE)

    # -- Ligne NET A PAYER
    _nouvelle_ligne()
    indice_net = table_rubriques.rows.__len__() - 1
    cellule_label_net = _fusionner_ligne(table_rubriques, indice_net, 0, 1)
    _texte_cellule(cellule_label_net, "NET A PAYER", gras=True, taille=10, couleur=BLANC, centre=False)
    _ombrer_cellule(cellule_label_net, VERT_BARRE)
    cellule_lettres = table_rubriques.cell(indice_net, 2)
    _texte_cellule(cellule_lettres, "{{NET_EN_LETTRES}}", gras=True, taille=9, couleur=BLANC, centre=False)
    _ombrer_cellule(cellule_lettres, VERT_BARRE)
    cellule_net_numerique = table_rubriques.cell(indice_net, 3)
    _texte_cellule(cellule_net_numerique, "{{NET_A_PERÇEVOIR}}", gras=True, taille=10, couleur=BLANC)
    _ombrer_cellule(cellule_net_numerique, VERT_BARRE)

    document.add_paragraph()

    # -------------------------------------------------------------
    # Bloc date / signature
    # -------------------------------------------------------------
    p_date = document.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_date = p_date.add_run(
        f"Done at {LIEU_SIGNATURE} on the / Fait à {LIEU_SIGNATURE} le: {{{{DATE_GENERATION}}}}"
    )
    run_date.bold = True
    run_date.font.size = Pt(10)
    run_date.font.name = "Times New Roman"

    for _ in range(3):
        document.add_paragraph()

    p_signature = document.add_paragraph()
    p_signature.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_signature = p_signature.add_run(TITRE_SIGNATAIRE_FR)
    run_signature.bold = True
    run_signature.font.size = Pt(10)
    run_signature.font.name = "Times New Roman"

    p_signature_en = document.add_paragraph()
    p_signature_en.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_signature_en = p_signature_en.add_run(TITRE_SIGNATAIRE_EN)
    run_signature_en.bold = True
    run_signature_en.font.size = Pt(10)
    run_signature_en.font.name = "Times New Roman"

    document.save(CHEMIN_TEMPLATE)
    return CHEMIN_TEMPLATE


if __name__ == "__main__":
    chemin = construire_template()
    print(f"Template créé : {chemin}")
