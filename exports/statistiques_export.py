"""
Export Excel des statistiques (module 17).

Pure présentation : reçoit des structures DÉJÀ calculées par
services/statistiques_service.py, jamais de recalcul. Réutilise les
styles déjà définis dans exports/excel_export.py pour une apparence
cohérente avec les autres exports de l'application.
"""

from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from exports.excel_export import (
    EXPORT_DIR,
    POLICE_ENTETE_COLONNE,
    POLICE_NORMALE,
    POLICE_SOUS_TITRE,
    POLICE_TOTAL,
    REMPLISSAGE_ENTETE,
    chemin_sortie_disponible,
)
from models.resultat_paie import ResultatPaie
from services.statistiques_service import (
    ComposantePaie,
    PointPeriode,
    StatistiquesGenerales,
    ValeurAtypique,
)
from services.reporting_paie_service import SyntheseDetailleeGroupe
from utils.formatters import libelle_sexe, libelle_statut, nettoyer_nom_fichier


def _entete(feuille, titre, nb_colonnes):
    cellule = feuille.cell(row=1, column=1, value=titre)
    cellule.font = POLICE_SOUS_TITRE
    feuille.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(nb_colonnes, 1))
    return 3


def _colonnes(feuille, ligne, colonnes: List[str]):
    for i, nom in enumerate(colonnes, start=1):
        c = feuille.cell(row=ligne, column=i, value=nom)
        c.font = POLICE_ENTETE_COLONNE
        c.fill = REMPLISSAGE_ENTETE
        feuille.column_dimensions[get_column_letter(i)].width = 20


def _feuille_synthese(classeur: Workbook, stats: StatistiquesGenerales) -> None:
    feuille = classeur.create_sheet("Synthese")
    feuille.cell(row=1, column=1, value="SYNTHÈSE STATISTIQUE").font = POLICE_SOUS_TITRE
    lignes = [
        ("Période", stats.periode.libelle), ("", ""),
        ("Enseignants au total", stats.nombre_enseignants_total),
        ("Actifs", stats.nombre_enseignants_actifs), ("Inactifs", stats.nombre_enseignants_inactifs),
        ("Vacataires", stats.nombre_vacataires), ("Permanents", stats.nombre_permanents),
        ("Hommes", stats.nombre_hommes), ("Femmes", stats.nombre_femmes), ("", ""),
        ("Heures - moyenne", stats.heures.moyenne), ("Heures - médiane", stats.heures.mediane),
        ("Taux horaire - moyenne", stats.taux_horaire.moyenne),
        ("Rémunération nette - moyenne", stats.remuneration_nette.moyenne),
        ("Rémunération nette - médiane", stats.remuneration_nette.mediane),
        ("Rémunération nette - écart-type", stats.remuneration_nette.ecart_type), ("", ""),
        ("Masse salariale brute", stats.masse_salariale_brute), ("Total taxe", stats.total_taxe),
        ("Total retenue amicale", stats.total_retenue_amicale), ("Total dettes", stats.total_dette),
        ("Total net payé", stats.total_net),
    ]
    for i, (libelle, valeur) in enumerate(lignes, start=3):
        feuille.cell(row=i, column=1, value=libelle).font = POLICE_NORMALE
        feuille.cell(row=i, column=2, value=valeur).font = POLICE_NORMALE
    feuille.column_dimensions["A"].width = 32
    feuille.column_dimensions["B"].width = 24


def _feuille_par_groupe(classeur: Workbook, nom: str, titre: str, groupes: List[SyntheseDetailleeGroupe]) -> None:
    feuille = classeur.create_sheet(nom)
    colonnes = ["Groupe", "Effectif", "Heures", "Gains", "AP/PP", "Surveillance", "Indemnités", "Taxe", "Retenue amicale", "Dettes", "Net"]
    ligne = _entete(feuille, titre, len(colonnes))
    _colonnes(feuille, ligne, colonnes)
    for i, g in enumerate(groupes, start=ligne + 1):
        valeurs = [g.libelle, g.nombre, g.total_heures, g.total_gain_heures, g.total_prime_ap_pp, g.total_surveillance_secretariat, g.total_indemnite_suggestion_admin, g.total_taxe, g.total_retenue_amicale, g.total_dette, g.total_net]
        for j, v in enumerate(valeurs, start=1):
            feuille.cell(row=i, column=j, value=v).font = POLICE_NORMALE


def _feuille_periodes(classeur: Workbook, points: List[PointPeriode]) -> None:
    feuille = classeur.create_sheet("Par_Periode")
    colonnes = ["Période", "Enseignants", "Heures", "Taux moyen", "Masse brute", "Net total", "Variation nette", "Variation %"]
    ligne = _entete(feuille, "ANALYSE PAR PÉRIODE", len(colonnes))
    _colonnes(feuille, ligne, colonnes)
    for i, p in enumerate(points, start=ligne + 1):
        valeurs = [
            p.periode.libelle, p.nombre_enseignants, p.heures_totales, p.taux_horaire_moyen,
            p.masse_salariale_brute, p.total_net, p.variation_net_absolue,
            f"{p.variation_net_pourcentage:+.1f} %" if p.variation_net_pourcentage is not None else "—",
        ]
        for j, v in enumerate(valeurs, start=1):
            feuille.cell(row=i, column=j, value=v).font = POLICE_NORMALE


def _feuille_composantes(classeur: Workbook, composantes: List[ComposantePaie]) -> None:
    feuille = classeur.create_sheet("Composantes")
    colonnes = ["Composante", "Montant total", "Part (%)"]
    ligne = _entete(feuille, "COMPOSANTES DE LA PAIE", len(colonnes))
    _colonnes(feuille, ligne, colonnes)
    for i, c in enumerate(composantes, start=ligne + 1):
        feuille.cell(row=i, column=1, value=c.libelle).font = POLICE_NORMALE
        feuille.cell(row=i, column=2, value=c.montant_total).font = POLICE_NORMALE
        feuille.cell(row=i, column=3, value=f"{c.part_pourcentage:.1f} %" if c.part_pourcentage is not None else "—").font = POLICE_NORMALE


def _feuille_enseignants(classeur: Workbook, resultats: List[ResultatPaie]) -> None:
    feuille = classeur.create_sheet("Enseignants")
    colonnes = ["Nom", "Prénom", "Sexe", "Statut", "Heures", "Taux horaire", "Gain", "Net à payer"]
    ligne = _entete(feuille, "DÉTAIL PAR ENSEIGNANT", len(colonnes))
    _colonnes(feuille, ligne, colonnes)
    for i, r in enumerate(resultats, start=ligne + 1):
        valeurs = [r.nom, r.prenom, libelle_sexe(r.sexe), libelle_statut(r.statut), r.total_heures, r.taux_horaire, r.gain_heures, r.net_a_percevoir]
        for j, v in enumerate(valeurs, start=1):
            feuille.cell(row=i, column=j, value=v).font = POLICE_NORMALE


def _feuille_outliers(classeur: Workbook, outliers: List[ValeurAtypique]) -> None:
    feuille = classeur.create_sheet("Outliers")
    colonnes = ["Enseignant", "Champ", "Valeur", "Borne basse", "Borne haute", "Niveau"]
    ligne = _entete(feuille, "VALEURS ATYPIQUES (À VÉRIFIER)", len(colonnes))
    _colonnes(feuille, ligne, colonnes)
    for i, o in enumerate(outliers, start=ligne + 1):
        valeurs = [f"{o.nom} {o.prenom}", o.champ, o.valeur, round(o.borne_basse, 1), round(o.borne_haute, 1), o.niveau]
        for j, v in enumerate(valeurs, start=1):
            feuille.cell(row=i, column=j, value=v).font = POLICE_NORMALE


def generer_classeur_statistiques(
    stats: StatistiquesGenerales,
    resultats: List[ResultatPaie],
    par_statut: List[SyntheseDetailleeGroupe],
    par_sexe: List[SyntheseDetailleeGroupe],
    composantes: List[ComposantePaie],
    outliers: Optional[List[ValeurAtypique]] = None,
    points_periodes: Optional[List[PointPeriode]] = None,
) -> Workbook:
    """Construit le classeur complet (section 19) — chaque feuille est optionnelle selon les données disponibles."""
    classeur = Workbook()
    classeur.remove(classeur.active)

    _feuille_synthese(classeur, stats)
    _feuille_enseignants(classeur, resultats)
    if par_statut:
        _feuille_par_groupe(classeur, "Par_Statut", "SYNTHÈSE PAR STATUT", par_statut)
    if par_sexe:
        _feuille_par_groupe(classeur, "Par_Sexe", "SYNTHÈSE PAR SEXE", par_sexe)
    _feuille_composantes(classeur, composantes)
    if points_periodes:
        _feuille_periodes(classeur, points_periodes)
    if outliers is not None:
        _feuille_outliers(classeur, outliers)

    return classeur


def generer_fichier_statistiques(
    stats: StatistiquesGenerales,
    resultats: List[ResultatPaie],
    par_statut: List[SyntheseDetailleeGroupe],
    par_sexe: List[SyntheseDetailleeGroupe],
    composantes: List[ComposantePaie],
    outliers: Optional[List[ValeurAtypique]] = None,
    points_periodes: Optional[List[PointPeriode]] = None,
    dossier: Optional[Path] = None,
) -> Path:
    classeur = generer_classeur_statistiques(stats, resultats, par_statut, par_sexe, composantes, outliers, points_periodes)
    nom_fichier = f"Statistiques_{nettoyer_nom_fichier(stats.periode.libelle)}.xlsx"
    chemin = chemin_sortie_disponible(nom_fichier, dossier=dossier if dossier is not None else EXPORT_DIR)
    classeur.save(chemin)
    return chemin
