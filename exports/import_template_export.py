"""
Générateur des modèles Excel téléchargeables pour l'importation
massive (module 15, section 9). Pure présentation : aucune formule de
paie, aucune logique métier — uniquement des exemples illustratifs.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from models.enums import TypeImport

POLICE_ENTETE = Font(name="Arial", size=10, bold=True, color="FFFFFF")
REMPLISSAGE_ENTETE = PatternFill("solid", fgColor="2F5496")

MODELES: dict = {
    TypeImport.ENSEIGNANTS: {
        "colonnes": ["Nom", "Prenom", "Sexe", "Statut", "Taux_Horaire"],
        "exemples": [
            ["Kamgang", "Jean Paul", "M", "P", 2000],
            ["Ngono", "Marie", "F", "V", 1500],
        ],
        "instructions": [
            "Sexe : M (Masculin) ou F (Féminin).",
            "Statut : P (Permanent) ou V (Vacataire).",
            "Taux_Horaire : nombre entier en FCFA, sans décimales.",
        ],
    },
    TypeImport.HEURES: {
        "colonnes": ["Nom", "Prenom", "Semaine_1", "Semaine_2", "Semaine_3", "Semaine_4", "Semaine_5"],
        "exemples": [["Kamgang", "Jean Paul", 20, 20, 20, 20, 20]],
        "instructions": [
            "Nom/Prenom doivent correspondre exactement à un enseignant déjà existant.",
            "Chaque colonne Semaine_N est optionnelle ; laisser vide si aucune heure.",
            "L'import n'est possible que pour une période au statut OUVERTE.",
        ],
    },
    TypeImport.REMUNERATIONS: {
        "colonnes": ["Nom", "Prenom", "Prime_AP_PP", "Surveillance_Secretariat", "Indemnite_Suggestion_Admin"],
        "exemples": [["Kamgang", "Jean Paul", 20000, 10000, 5000]],
        "instructions": [
            "Montants en FCFA entiers, sans décimales, jamais négatifs.",
            "L'import n'est possible que pour une période au statut OUVERTE.",
        ],
    },
    TypeImport.RETENUES: {
        "colonnes": ["Nom", "Prenom", "Retenue_Amicale", "Dette"],
        "exemples": [["Kamgang", "Jean Paul", 5000, 10000]],
        "instructions": [
            "Montants en FCFA entiers, sans décimales, jamais négatifs.",
            "L'import n'est possible que pour une période au statut OUVERTE.",
        ],
    },
}


def generer_classeur_modele(type_import: TypeImport) -> Workbook:
    """Construit le classeur modèle (colonnes + exemple + feuille Instructions) pour un type d'import donné."""
    modele = MODELES[type_import]
    classeur = Workbook()

    feuille = classeur.active
    feuille.title = "Donnees"
    for index, nom_colonne in enumerate(modele["colonnes"], start=1):
        cellule = feuille.cell(row=1, column=index, value=nom_colonne)
        cellule.font = POLICE_ENTETE
        cellule.fill = REMPLISSAGE_ENTETE
        feuille.column_dimensions[get_column_letter(index)].width = 20

    for ligne_index, exemple in enumerate(modele["exemples"], start=2):
        for colonne_index, valeur in enumerate(exemple, start=1):
            feuille.cell(row=ligne_index, column=colonne_index, value=valeur)

    feuille_instructions = classeur.create_sheet("Instructions")
    feuille_instructions.cell(row=1, column=1, value="Instructions de remplissage").font = Font(bold=True, size=12)
    for i, ligne_instruction in enumerate(modele["instructions"], start=3):
        feuille_instructions.cell(row=i, column=1, value=f"• {ligne_instruction}")
    feuille_instructions.column_dimensions["A"].width = 90

    return classeur


def generer_fichier_modele(type_import: TypeImport, dossier: Path) -> Path:
    """Génère le fichier modèle sur disque : template_import_{type}.xlsx."""
    dossier.mkdir(parents=True, exist_ok=True)
    classeur = generer_classeur_modele(type_import)
    chemin = dossier / f"template_import_{type_import.value}.xlsx"
    classeur.save(chemin)
    return chemin


def generer_modele_csv(type_import: TypeImport) -> str:
    """Génère le contenu CSV du modèle (en-têtes + exemple), sous forme de texte prêt à télécharger."""
    modele = MODELES[type_import]
    lignes = [",".join(modele["colonnes"])]
    for exemple in modele["exemples"]:
        lignes.append(",".join(str(v) for v in exemple))
    return "\n".join(lignes)
