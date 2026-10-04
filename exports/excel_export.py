"""
Générateur du fichier Excel comptable (module 06).

Reçoit un EtatComptablePeriode DÉJÀ préparé par
services/comptabilite_service.py (lui-même dérivé des résultats de
services/paie_service.py) : ce module ne contient et ne doit JAMAIS
contenir de formule de paie (gain heures, taxe, net à percevoir).
Il se limite à la mise en forme et à l'écriture du classeur — pure
présentation d'une donnée déjà calculée.

Ce module ne dépend pas de Streamlit.
"""

from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from exports.logo_excel import ajouter_logo
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from config.settings import DATA_DIR
from services.comptabilite_service import EtatComptablePeriode
from utils.formatters import dates_periode, formater_taxe_periode, libelle_sexe, libelle_statut, libelle_statut_periode, nettoyer_nom_fichier

EXPORT_DIR = DATA_DIR / "exports"

# ---------------------------------------------------------------------
# Styles partagés (sobres, professionnels)
# ---------------------------------------------------------------------

POLICE_TITRE = Font(name="Arial", size=14, bold=True, color="1F1F1F")
POLICE_SOUS_TITRE = Font(name="Arial", size=11, bold=True, color="1F1F1F")
POLICE_INFO = Font(name="Arial", size=10, color="404040")
POLICE_ENTETE_COLONNE = Font(name="Arial", size=10, bold=True, color="FFFFFF")
POLICE_NORMALE = Font(name="Arial", size=10)
POLICE_TOTAL = Font(name="Arial", size=10, bold=True)

REMPLISSAGE_ENTETE = PatternFill("solid", fgColor="2F5496")
REMPLISSAGE_TOTAL = PatternFill("solid", fgColor="D9E1F2")

BORDURE_FINE = Border(
    left=Side(style="thin", color="B7B7B7"),
    right=Side(style="thin", color="B7B7B7"),
    top=Side(style="thin", color="B7B7B7"),
    bottom=Side(style="thin", color="B7B7B7"),
)

ALIGNEMENT_CENTRE = Alignment(horizontal="center", vertical="center")
ALIGNEMENT_GAUCHE = Alignment(horizontal="left", vertical="center")
ALIGNEMENT_DROITE = Alignment(horizontal="right", vertical="center")

# Format numérique personnalisé : la valeur reste un nombre exploitable
# par Excel (tri, somme, etc.), "FCFA" n'est qu'un affichage.
FORMAT_FCFA = '#,##0 "FCFA"'
FORMAT_HEURES = "0.0"

COLONNES_ETAT_COMPTABLE = [
    "N°", "Nom", "Prénom", "Sexe", "Statut", "Total heures", "Taux horaire",
    "Gain par heures", "Prime AP/PP", "Surveillance/Secrétariat",
    "Indemnité suggestion/admin", "Base taxable", "Taxe",
    "Retenue amicale", "Dette", "Net à percevoir",
]
COLONNES_MONETAIRES_ETAT = {7, 8, 9, 10, 11, 12, 13, 14, 15}  # index 0-based dans COLONNES_ETAT_COMPTABLE
COLONNE_HEURES_ETAT = 5

COLONNES_DETAIL_HEURES = [
    "N°", "Nom", "Prénom", "Statut", "Semaine 1", "Semaine 2", "Semaine 3",
    "Semaine 4", "Semaine 5", "Total heures",
]


def _ecrire_titre_entete(feuille: Worksheet, etat: EtatComptablePeriode, etablissement: str, nb_colonnes: int) -> int:
    """
    Écrit le bloc d'en-tête professionnel (titre, établissement,
    période, dates, date de génération, nombre d'enseignants) et
    retourne le numéro de la première ligne libre après l'en-tête.
    """
    date_debut, date_fin = dates_periode(etat.periode.mois, etat.periode.annee)

    lignes = [
        ("GESTION DES SALAIRES", POLICE_TITRE),
        ("ÉTAT COMPTABLE DES RÉMUNÉRATIONS", POLICE_SOUS_TITRE),
        (f"Établissement : {etablissement}", POLICE_INFO),
        (f"Période : {etat.periode.libelle}", POLICE_INFO),
        (f"Statut de la période : {libelle_statut_periode(etat.periode.statut)}", POLICE_INFO),
        (f"Du : {date_debut.strftime('%d/%m/%Y')}    Au : {date_fin.strftime('%d/%m/%Y')}", POLICE_INFO),
        (f"Date de génération : {etat.date_generation}", POLICE_INFO),
        (f"Nombre d'enseignants : {len(etat.resultats)}", POLICE_INFO),
    ]

    ligne = 1
    for texte, police in lignes:
        cellule = feuille.cell(row=ligne, column=1, value=texte)
        cellule.font = police
        feuille.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=nb_colonnes)
        ligne += 1

    if etat.periode.statut.value == "ouverte":
        avertissement = feuille.cell(
            row=ligne, column=1,
            value="ATTENTION — État PROVISOIRE : la période est encore ouverte, les données peuvent évoluer.",
        )
        avertissement.font = Font(name="Arial", size=10, bold=True, color="9C5700")
        feuille.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=nb_colonnes)
        ligne += 1

    if etat.erreurs:
        avertissement = feuille.cell(
            row=ligne, column=1,
            value=f"ATTENTION — {len(etat.erreurs)} enseignant(s) n'ont pas pu être calculé(s) et n'apparaissent pas ci-dessous.",
        )
        avertissement.font = Font(name="Arial", size=10, bold=True, color="C00000")
        feuille.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=nb_colonnes)
        ligne += 1

    return ligne + 1  # une ligne vide de séparation


def _ecrire_entete_colonnes(feuille: Worksheet, ligne: int, colonnes: list) -> None:
    for index, nom_colonne in enumerate(colonnes, start=1):
        cellule = feuille.cell(row=ligne, column=index, value=nom_colonne)
        cellule.font = POLICE_ENTETE_COLONNE
        cellule.fill = REMPLISSAGE_ENTETE
        cellule.alignment = ALIGNEMENT_CENTRE
        cellule.border = BORDURE_FINE


def _construire_feuille_etat_comptable(feuille: Worksheet, etat: EtatComptablePeriode, etablissement: str) -> None:
    nb_colonnes = len(COLONNES_ETAT_COMPTABLE)
    ligne_entete = _ecrire_titre_entete(feuille, etat, etablissement, nb_colonnes)
    _ecrire_entete_colonnes(feuille, ligne_entete, COLONNES_ETAT_COMPTABLE)

    ligne_donnees_debut = ligne_entete + 1
    ligne = ligne_donnees_debut
    for numero, resultat in enumerate(etat.resultats, start=1):
        valeurs = [
            numero, resultat.nom, resultat.prenom, libelle_sexe(resultat.sexe), libelle_statut(resultat.statut),
            resultat.total_heures, resultat.taux_horaire, resultat.gain_heures, resultat.prime_ap_pp,
            resultat.surveillance_secretariat, resultat.indemnite_suggestion_admin, resultat.base_taxable,
            resultat.taxe_5, resultat.retenue_amicale, resultat.dette, resultat.net_a_percevoir,
        ]
        for index, valeur in enumerate(valeurs):
            cellule = feuille.cell(row=ligne, column=index + 1, value=valeur)
            cellule.font = POLICE_NORMALE
            cellule.border = BORDURE_FINE
            if index == 0:
                cellule.alignment = ALIGNEMENT_CENTRE
            elif index in (1, 2, 3, 4):
                cellule.alignment = ALIGNEMENT_GAUCHE
            elif index == COLONNE_HEURES_ETAT:
                cellule.number_format = FORMAT_HEURES
                cellule.alignment = ALIGNEMENT_DROITE
            elif index in COLONNES_MONETAIRES_ETAT:
                cellule.number_format = FORMAT_FCFA
                cellule.alignment = ALIGNEMENT_DROITE
        ligne += 1

    # --- Ligne TOTAL GÉNÉRAL (valeurs déjà agrégées par paie_service.calculer_totaux_groupe) ---
    ligne_total = ligne
    totaux = etat.totaux
    valeurs_totaux = [
        None, "TOTAL GÉNÉRAL", None, None, None,
        totaux.total_heures, None, totaux.total_gain_heures, totaux.total_prime_ap_pp,
        totaux.total_surveillance_secretariat, totaux.total_indemnite_suggestion_admin, None,
        totaux.total_taxe, totaux.total_retenue_amicale, totaux.total_dette, totaux.total_net_a_percevoir,
    ]
    for index, valeur in enumerate(valeurs_totaux):
        cellule = feuille.cell(row=ligne_total, column=index + 1, value=valeur)
        cellule.font = POLICE_TOTAL
        cellule.fill = REMPLISSAGE_TOTAL
        cellule.border = BORDURE_FINE
        if index == COLONNE_HEURES_ETAT:
            cellule.number_format = FORMAT_HEURES
            cellule.alignment = ALIGNEMENT_DROITE
        elif index in COLONNES_MONETAIRES_ETAT:
            cellule.number_format = FORMAT_FCFA
            cellule.alignment = ALIGNEMENT_DROITE
    feuille.merge_cells(start_row=ligne_total, start_column=2, end_row=ligne_total, end_column=5)

    # --- Mise en forme générale de la feuille ---
    feuille.freeze_panes = feuille.cell(row=ligne_donnees_debut, column=1)
    feuille.auto_filter.ref = (
        f"A{ligne_entete}:{get_column_letter(nb_colonnes)}{ligne_total}"
    )
    largeurs = [5, 16, 16, 10, 12, 12, 12, 14, 12, 20, 20, 14, 12, 14, 12, 16]
    for index, largeur in enumerate(largeurs, start=1):
        feuille.column_dimensions[get_column_letter(index)].width = largeur


def _construire_feuille_synthese(feuille: Worksheet, etat: EtatComptablePeriode, etablissement: str) -> None:
    date_debut, date_fin = dates_periode(etat.periode.mois, etat.periode.annee)
    totaux = etat.totaux

    lignes = [
        ("SYNTHÈSE COMPTABLE", POLICE_TITRE),
        (f"Établissement : {etablissement}", POLICE_INFO),
        (f"Période : {etat.periode.libelle} (du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')})", POLICE_INFO),
        (f"Date de génération : {etat.date_generation}", POLICE_INFO),
        ("", None),
    ]
    ligne = 1
    for texte, police in lignes:
        cellule = feuille.cell(row=ligne, column=1, value=texte or None)
        if police:
            cellule.font = police
        feuille.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=4)
        ligne += 1

    indicateurs = [
        ("Nombre d'enseignants", len(etat.resultats), None),
        ("Total heures", totaux.total_heures, FORMAT_HEURES),
        ("Masse salariale brute (base taxable)", totaux.total_gain_heures + totaux.total_primes, FORMAT_FCFA),
        (f"Total taxe ({formater_taxe_periode(etat.periode)})", totaux.total_taxe, FORMAT_FCFA),
        ("Total retenues (amicale + dette)", totaux.total_retenues, FORMAT_FCFA),
        ("Total net à percevoir", totaux.total_net_a_percevoir, FORMAT_FCFA),
    ]
    for libelle, valeur, format_nombre in indicateurs:
        cellule_libelle = feuille.cell(row=ligne, column=1, value=libelle)
        cellule_libelle.font = POLICE_TOTAL
        cellule_valeur = feuille.cell(row=ligne, column=2, value=valeur)
        cellule_valeur.font = POLICE_NORMALE
        cellule_valeur.alignment = ALIGNEMENT_DROITE
        if format_nombre:
            cellule_valeur.number_format = format_nombre
        ligne += 1

    ligne += 1  # ligne vide

    # --- Synthèse par statut ---
    entete_synthese = feuille.cell(row=ligne, column=1, value="Répartition par statut")
    entete_synthese.font = POLICE_SOUS_TITRE
    ligne += 1

    _ecrire_entete_colonnes(feuille, ligne, ["Statut", "Nombre", "Total net"])
    ligne += 1
    ligne_debut_statuts = ligne
    for item in etat.synthese_par_statut:
        feuille.cell(row=ligne, column=1, value=libelle_statut(item.statut)).font = POLICE_NORMALE
        cellule_nombre = feuille.cell(row=ligne, column=2, value=item.nombre)
        cellule_nombre.font = POLICE_NORMALE
        cellule_nombre.alignment = ALIGNEMENT_CENTRE
        cellule_net = feuille.cell(row=ligne, column=3, value=item.total_net)
        cellule_net.font = POLICE_NORMALE
        cellule_net.number_format = FORMAT_FCFA
        cellule_net.alignment = ALIGNEMENT_DROITE
        for col in range(1, 4):
            feuille.cell(row=ligne, column=col).border = BORDURE_FINE
        ligne += 1

    # Ligne TOTAL de la répartition par statut (déjà agrégée, pas recalculée)
    feuille.cell(row=ligne, column=1, value="TOTAL").font = POLICE_TOTAL
    cellule_nombre_total = feuille.cell(row=ligne, column=2, value=len(etat.resultats))
    cellule_nombre_total.font = POLICE_TOTAL
    cellule_nombre_total.alignment = ALIGNEMENT_CENTRE
    cellule_net_total = feuille.cell(row=ligne, column=3, value=totaux.total_net_a_percevoir)
    cellule_net_total.font = POLICE_TOTAL
    cellule_net_total.number_format = FORMAT_FCFA
    cellule_net_total.alignment = ALIGNEMENT_DROITE
    for col in range(1, 4):
        cellule = feuille.cell(row=ligne, column=col)
        cellule.fill = REMPLISSAGE_TOTAL
        cellule.border = BORDURE_FINE

    for index, largeur in enumerate([32, 16, 20], start=1):
        feuille.column_dimensions[get_column_letter(index)].width = largeur


def _construire_feuille_detail_heures(feuille: Worksheet, etat: EtatComptablePeriode) -> None:
    nb_colonnes = len(COLONNES_DETAIL_HEURES)

    lignes_entete = [
        ("DÉTAIL DES HEURES", POLICE_TITRE),
        (f"Période : {etat.periode.libelle}", POLICE_INFO),
        (f"Date de génération : {etat.date_generation}", POLICE_INFO),
        ("", None),
    ]
    ligne_courante = 1
    for texte, police in lignes_entete:
        cellule = feuille.cell(row=ligne_courante, column=1, value=texte or None)
        if police:
            cellule.font = police
        feuille.merge_cells(start_row=ligne_courante, start_column=1, end_row=ligne_courante, end_column=nb_colonnes)
        ligne_courante += 1

    ligne_entete_colonnes = ligne_courante
    _ecrire_entete_colonnes(feuille, ligne_entete_colonnes, COLONNES_DETAIL_HEURES)

    ligne_donnees_debut = ligne_entete_colonnes + 1
    ligne = ligne_donnees_debut
    for numero, resultat in enumerate(etat.resultats, start=1):
        valeurs = [
            numero, resultat.nom, resultat.prenom, libelle_statut(resultat.statut),
            resultat.semaine_1, resultat.semaine_2, resultat.semaine_3, resultat.semaine_4, resultat.semaine_5,
            resultat.total_heures,
        ]
        for index, valeur in enumerate(valeurs):
            cellule = feuille.cell(row=ligne, column=index + 1, value=valeur)
            cellule.font = POLICE_NORMALE
            cellule.border = BORDURE_FINE
            if index == 0:
                cellule.alignment = ALIGNEMENT_CENTRE
            elif index in (1, 2, 3):
                cellule.alignment = ALIGNEMENT_GAUCHE
            else:
                cellule.number_format = FORMAT_HEURES
                cellule.alignment = ALIGNEMENT_DROITE
        ligne += 1

    feuille.freeze_panes = feuille.cell(row=ligne_donnees_debut, column=1)
    feuille.auto_filter.ref = f"A{ligne_entete_colonnes}:{get_column_letter(nb_colonnes)}{ligne - 1}"
    largeurs = [5, 16, 16, 12, 11, 11, 11, 11, 11, 13]
    for index, largeur in enumerate(largeurs, start=1):
        feuille.column_dimensions[get_column_letter(index)].width = largeur


def generer_classeur_comptable(etat: EtatComptablePeriode, etablissement: str = "Établissement scolaire") -> Workbook:
    """
    Construit le classeur Excel complet (3 feuilles) à partir d'un
    EtatComptablePeriode déjà préparé par
    services/comptabilite_service.py. Ne recalcule RIEN : lit
    uniquement les valeurs déjà présentes dans etat.resultats,
    etat.totaux et etat.synthese_par_statut.
    """
    classeur = Workbook()

    feuille_etat = classeur.active
    feuille_etat.title = "État comptable"
    _construire_feuille_etat_comptable(feuille_etat, etat, etablissement)

    feuille_synthese = classeur.create_sheet("Synthèse")
    _construire_feuille_synthese(feuille_synthese, etat, etablissement)

    feuille_heures = classeur.create_sheet("Détail heures")
    _construire_feuille_detail_heures(feuille_heures, etat)

    return ajouter_logo(classeur)


def generer_nom_fichier(etat: EtatComptablePeriode) -> str:
    """
    Construit un nom de fichier dynamique et sûr sous Windows, par
    exemple : Etat_comptable_Aout_2026.xlsx
    """
    libelle_nettoye = nettoyer_nom_fichier(etat.periode.libelle)
    return f"Etat_comptable_{libelle_nettoye}.xlsx"


def chemin_sortie_disponible(nom_fichier: str, dossier: Optional[Path] = None) -> Path:
    """
    Retourne un chemin de fichier garanti disponible dans le dossier
    d'export : n'écrase JAMAIS un fichier existant. Si le nom est déjà
    pris, ajoute un suffixe numérique (_1, _2, ...).
    """
    dossier_cible = dossier if dossier is not None else EXPORT_DIR
    dossier_cible.mkdir(parents=True, exist_ok=True)

    chemin = dossier_cible / nom_fichier
    if not chemin.exists():
        return chemin

    racine = chemin.stem
    suffixe = chemin.suffix
    compteur = 1
    while True:
        candidat = dossier_cible / f"{racine}_{compteur}{suffixe}"
        if not candidat.exists():
            return candidat
        compteur += 1


def generer_fichier_excel(
    etat: EtatComptablePeriode,
    etablissement: str = "Établissement scolaire",
    dossier: Optional[Path] = None,
    utilisateur: Optional[str] = None,
) -> Path:
    """
    Génère le classeur et l'enregistre sur disque dans data/exports/
    (créé automatiquement si besoin), sans jamais écraser un fichier
    existant. Retourne le chemin du fichier créé.
    """
    classeur = generer_classeur_comptable(etat, etablissement=etablissement)
    nom_fichier = generer_nom_fichier(etat)
    chemin = chemin_sortie_disponible(nom_fichier, dossier=dossier)
    classeur.save(chemin)

    # Registre documentaire (module 14) : best-effort, jamais bloquant.
    try:
        from models.enums import TypeDocument
        from services.document_service import enregistrer_document
        enregistrer_document(TypeDocument.EXPORT_EXCEL, chemin, periode_id=etat.periode.id, utilisateur=utilisateur)
    except Exception:  # noqa: BLE001
        pass

    return chemin
