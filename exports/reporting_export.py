"""
Générateur du classeur Excel « État de paie » complet (module 13).

Reçoit un `EtatPaieComplet` DÉJÀ préparé par
services/reporting_paie_service.py (lui-même dérivé de
services/comptabilite_service.py et de services/paie_service.py) : ce
module ne contient et ne doit JAMAIS contenir de formule de paie. Il se
limite à la mise en forme et à l'écriture du classeur — pure
présentation de données déjà calculées.

Réutilise les styles déjà définis dans exports/excel_export.py (module
06) plutôt que de les redéfinir, pour une apparence cohérente entre
tous les exports Excel de l'application. N'écrase jamais un fichier
existant (même garantie que le module 06).

Ce module ne dépend pas de Streamlit.
"""

from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from exports.excel_export import (
    ALIGNEMENT_CENTRE,
    BORDURE_FINE,
    EXPORT_DIR,
    POLICE_ENTETE_COLONNE,
    POLICE_INFO,
    POLICE_NORMALE,
    POLICE_SOUS_TITRE,
    POLICE_TITRE,
    POLICE_TOTAL,
    REMPLISSAGE_ENTETE,
    REMPLISSAGE_TOTAL,
    chemin_sortie_disponible,
)
from services.reporting_paie_service import EtatPaieComplet, StatutRapprochement
from services.historique_paie_service import ComparaisonPeriodes
from utils.formatters import libelle_sexe, libelle_statut, libelle_statut_periode, nettoyer_nom_fichier


def _ecrire_entete_feuille(feuille: Worksheet, titre: str, nb_colonnes: int, ligne: int = 1) -> int:
    cellule = feuille.cell(row=ligne, column=1, value=titre)
    cellule.font = POLICE_SOUS_TITRE
    feuille.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=nb_colonnes)
    return ligne + 2


def _ecrire_entete_colonnes(feuille: Worksheet, ligne: int, colonnes: List[str]) -> None:
    for index, nom_colonne in enumerate(colonnes, start=1):
        cellule = feuille.cell(row=ligne, column=index, value=nom_colonne)
        cellule.font = POLICE_ENTETE_COLONNE
        cellule.fill = REMPLISSAGE_ENTETE
        cellule.alignment = ALIGNEMENT_CENTRE
        cellule.border = BORDURE_FINE


def _ajuster_largeurs(feuille: Worksheet, nb_colonnes: int, largeur: int = 20) -> None:
    for index in range(1, nb_colonnes + 1):
        feuille.column_dimensions[get_column_letter(index)].width = largeur


def _feuille_synthese(classeur: Workbook, rapport: EtatPaieComplet) -> None:
    feuille = classeur.create_sheet("Synthese")
    etat = rapport.etat_comptable

    cellule = feuille.cell(row=1, column=1, value="ÉTAT GÉNÉRAL DE PAIE")
    cellule.font = POLICE_TITRE
    feuille.merge_cells("A1:B1")

    lignes_info = [
        ("Établissement", rapport.etablissement),
        ("Période", rapport.periode.libelle),
        ("Statut de la période", libelle_statut_periode(rapport.periode.statut)),
        ("Date de génération", rapport.date_generation),
        ("Utilisateur", rapport.utilisateur or "—"),
        ("", ""),
        ("EFFECTIF", ""),
        ("Nombre d'enseignants", len(etat.resultats)),
        ("", ""),
        ("RÉMUNÉRATIONS", ""),
        ("Total heures", etat.totaux.total_heures),
        ("Total gains", etat.totaux.total_gain_heures),
        ("Total AP/PP", etat.totaux.total_prime_ap_pp),
        ("Total surveillance/secrétariat", etat.totaux.total_surveillance_secretariat),
        ("Total indemnités", etat.totaux.total_indemnite_suggestion_admin),
        ("Total base taxable", etat.totaux.total_gain_heures + etat.totaux.total_primes),
        ("", ""),
        ("RETENUES", ""),
        ("Total taxe", etat.totaux.total_taxe),
        ("Total retenue amicale", etat.totaux.total_retenue_amicale),
        ("Total dettes", etat.totaux.total_dette),
        ("", ""),
        ("NET À PAYER", ""),
        ("Total net à payer", etat.totaux.total_net_a_percevoir),
        ("", ""),
        ("RAPPROCHEMENT", "OK" if rapport.rapprochement.toutes_ok else "ÉCART DÉTECTÉ"),
        ("", ""),
        ("OBSERVATIONS", ""),
    ] + [("", obs) for obs in rapport.observations]

    ligne = 3
    for libelle, valeur in lignes_info:
        cellule_libelle = feuille.cell(row=ligne, column=1, value=libelle)
        cellule_libelle.font = POLICE_TOTAL if libelle.isupper() and libelle else POLICE_NORMALE
        feuille.cell(row=ligne, column=2, value=valeur).font = POLICE_NORMALE
        ligne += 1

    feuille.column_dimensions["A"].width = 35
    feuille.column_dimensions["B"].width = 40


def _feuille_detail_enseignants(classeur: Workbook, rapport: EtatPaieComplet) -> None:
    feuille = classeur.create_sheet("Detail_Enseignants")
    colonnes = [
        "Nom", "Prénom", "Sexe", "Statut", "Heures", "Taux horaire", "Gain", "AP/PP",
        "Surveillance", "Indemnité", "Base taxable", "Taxe", "Retenue amicale", "Dette", "Net à payer",
    ]
    ligne = _ecrire_entete_feuille(feuille, "DÉTAIL PAR ENSEIGNANT", len(colonnes))
    _ecrire_entete_colonnes(feuille, ligne, colonnes)
    ligne += 1

    for r in rapport.etat_comptable.resultats:
        valeurs = [
            r.nom, r.prenom, libelle_sexe(r.sexe), libelle_statut(r.statut), r.total_heures, r.taux_horaire,
            r.gain_heures, r.prime_ap_pp, r.surveillance_secretariat, r.indemnite_suggestion_admin,
            r.base_taxable, r.taxe_5, r.retenue_amicale, r.dette, r.net_a_percevoir,
        ]
        for index, valeur in enumerate(valeurs, start=1):
            feuille.cell(row=ligne, column=index, value=valeur).font = POLICE_NORMALE
        ligne += 1

    _ajuster_largeurs(feuille, len(colonnes), largeur=14)


def _feuille_par_groupe(classeur: Workbook, nom_feuille: str, titre: str, groupes) -> None:
    feuille = classeur.create_sheet(nom_feuille)
    colonnes = [
        "Groupe", "Effectif", "Heures", "Gains", "AP/PP", "Surveillance", "Indemnités",
        "Base taxable", "Taxe", "Retenue amicale", "Dettes", "Net",
    ]
    ligne = _ecrire_entete_feuille(feuille, titre, len(colonnes))
    _ecrire_entete_colonnes(feuille, ligne, colonnes)
    ligne += 1

    for g in groupes:
        valeurs = [
            g.libelle, g.nombre, g.total_heures, g.total_gain_heures, g.total_prime_ap_pp,
            g.total_surveillance_secretariat, g.total_indemnite_suggestion_admin, g.total_base_taxable,
            g.total_taxe, g.total_retenue_amicale, g.total_dette, g.total_net,
        ]
        for index, valeur in enumerate(valeurs, start=1):
            feuille.cell(row=ligne, column=index, value=valeur).font = POLICE_NORMALE
        ligne += 1

    _ajuster_largeurs(feuille, len(colonnes), largeur=16)


def _feuille_retenues(classeur: Workbook, rapport: EtatPaieComplet) -> None:
    feuille = classeur.create_sheet("Retenues")
    colonnes = ["Enseignant", "Taxe", "Retenue amicale", "Dette", "Total retenues", "Net"]
    ligne = _ecrire_entete_feuille(feuille, "ÉTAT DES RETENUES", len(colonnes))
    _ecrire_entete_colonnes(feuille, ligne, colonnes)
    ligne += 1

    for r in rapport.retenues:
        valeurs = [f"{r.nom} {r.prenom}", r.taxe, r.retenue_amicale, r.dette, r.total_retenues, r.net]
        for index, valeur in enumerate(valeurs, start=1):
            feuille.cell(row=ligne, column=index, value=valeur).font = POLICE_NORMALE
        ligne += 1

    if rapport.retenues:
        cellule = feuille.cell(row=ligne, column=1, value="TOTAL")
        cellule.font = POLICE_TOTAL
        cellule.fill = REMPLISSAGE_TOTAL
        feuille.cell(row=ligne, column=2, value=sum(r.taxe for r in rapport.retenues)).font = POLICE_TOTAL
        feuille.cell(row=ligne, column=3, value=sum(r.retenue_amicale for r in rapport.retenues)).font = POLICE_TOTAL
        feuille.cell(row=ligne, column=4, value=sum(r.dette for r in rapport.retenues)).font = POLICE_TOTAL
        feuille.cell(row=ligne, column=5, value=sum(r.total_retenues for r in rapport.retenues)).font = POLICE_TOTAL
        feuille.cell(row=ligne, column=6, value=sum(r.net for r in rapport.retenues)).font = POLICE_TOTAL

    _ajuster_largeurs(feuille, len(colonnes), largeur=18)


def _feuille_rapprochement(classeur: Workbook, rapport: EtatPaieComplet) -> None:
    feuille = classeur.create_sheet("Rapprochement")
    colonnes = ["Élément", "Montant attendu", "Montant enregistré", "Écart", "Statut"]
    ligne = _ecrire_entete_feuille(feuille, "RAPPROCHEMENT DE PÉRIODE", len(colonnes))
    _ecrire_entete_colonnes(feuille, ligne, colonnes)
    ligne += 1

    for l in rapport.rapprochement.lignes:
        valeurs = [l.element, l.montant_attendu, l.montant_enregistre, l.ecart, l.statut.value]
        for index, valeur in enumerate(valeurs, start=1):
            cellule = feuille.cell(row=ligne, column=index, value=valeur)
            cellule.font = POLICE_NORMALE
            if index == 5 and l.statut != StatutRapprochement.OK:
                cellule.font = POLICE_TOTAL
        ligne += 1

    _ajuster_largeurs(feuille, len(colonnes), largeur=22)


def _feuille_comparaison(classeur: Workbook, comparaison: ComparaisonPeriodes) -> None:
    feuille = classeur.create_sheet("Comparaison")
    colonnes = ["Indicateur", comparaison.periode_a.libelle, comparaison.periode_b.libelle, "Variation", "Variation %"]
    ligne = _ecrire_entete_feuille(feuille, "COMPARAISON ENTRE PÉRIODES", len(colonnes))
    _ecrire_entete_colonnes(feuille, ligne, colonnes)
    ligne += 1

    for indicateur in comparaison.indicateurs:
        pourcentage = indicateur.variation_pourcentage
        valeurs = [
            indicateur.libelle, indicateur.valeur_a, indicateur.valeur_b, indicateur.variation_absolue,
            f"{pourcentage:+.1f} %" if pourcentage is not None else "—",
        ]
        for index, valeur in enumerate(valeurs, start=1):
            feuille.cell(row=ligne, column=index, value=valeur).font = POLICE_NORMALE
        ligne += 1

    _ajuster_largeurs(feuille, len(colonnes), largeur=20)


def generer_classeur_etat_paie(
    rapport: EtatPaieComplet, comparaison: Optional[ComparaisonPeriodes] = None
) -> Workbook:
    """
    Construit le classeur complet (section 20) : Synthese,
    Detail_Enseignants, Par_Statut, Par_Sexe, Retenues, Rapprochement,
    et Comparaison (uniquement si `comparaison` est fournie — sinon
    cette feuille est simplement omise, gérée proprement).
    """
    classeur = Workbook()
    classeur.remove(classeur.active)  # feuille par défaut vide, retirée

    _feuille_synthese(classeur, rapport)
    _feuille_detail_enseignants(classeur, rapport)
    _feuille_par_groupe(classeur, "Par_Statut", "SYNTHÈSE PAR STATUT", rapport.synthese_statut)
    _feuille_par_groupe(classeur, "Par_Sexe", "SYNTHÈSE PAR SEXE", rapport.synthese_sexe)
    _feuille_retenues(classeur, rapport)
    _feuille_rapprochement(classeur, rapport)
    if comparaison is not None:
        _feuille_comparaison(classeur, comparaison)

    return classeur


def generer_nom_fichier_etat_paie(rapport: EtatPaieComplet) -> str:
    """Ex : Etat_Paie_Aout_2026.xlsx"""
    return f"Etat_Paie_{nettoyer_nom_fichier(rapport.periode.libelle)}.xlsx"


def generer_fichier_etat_paie(
    rapport: EtatPaieComplet, comparaison: Optional[ComparaisonPeriodes] = None, dossier: Optional[Path] = None
) -> Path:
    """Génère le classeur et l'enregistre sur disque, sans jamais écraser un fichier existant."""
    classeur = generer_classeur_etat_paie(rapport, comparaison=comparaison)
    nom_fichier = generer_nom_fichier_etat_paie(rapport)
    chemin = chemin_sortie_disponible(nom_fichier, dossier=dossier if dossier is not None else EXPORT_DIR)
    classeur.save(chemin)

    # Registre documentaire (module 14) : best-effort, jamais bloquant.
    try:
        from models.enums import TypeDocument
        from services.document_service import enregistrer_document
        enregistrer_document(
            TypeDocument.ETAT_PAIE, chemin, periode_id=rapport.periode.id, utilisateur=rapport.utilisateur
        )
    except Exception:  # noqa: BLE001
        pass

    return chemin
