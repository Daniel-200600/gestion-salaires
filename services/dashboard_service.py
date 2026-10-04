"""
Service tableau de bord (module 08).

Module de CONSULTATION + AGRÉGATION + CONTRÔLE DE COHÉRENCE. Ne
recalcule JAMAIS gain_heures, taxe_5 ou net_a_percevoir : toutes les
valeurs financières proviennent de services/paie_service.py (via
services/comptabilite_service.py, qui délègue déjà entièrement au
moteur de paie — réutilisé ici tel quel, sans duplication).

Aucune dépendance à Streamlit. Aucune écriture en base : toutes les
fonctions de ce module sont des lectures pures.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

from database.repositories import enseignant_repository
from exports.excel_export import EXPORT_DIR, chemin_sortie_disponible, generer_classeur_comptable
from models.enseignant import Enseignant
from models.enums import Sexe, StatutEnseignant
from models.resultat_paie import ResultatPaie
from services import bulletin_service
from services.comptabilite_service import ComptabiliteError, EtatComptablePeriode, preparer_etat_comptable
from services.periode_service import lister_periodes
from utils.formatters import nettoyer_nom_fichier

DbPath = Optional[Union[str, Path]]


# ---------------------------------------------------------------------
# Indicateurs enseignants (section 5.1)
# ---------------------------------------------------------------------

@dataclass
class IndicateursEnseignants:
    total: int = 0
    actifs: int = 0
    inactifs: int = 0
    permanents: int = 0
    vacataires: int = 0
    a_completer: int = 0  # enseignants actifs à fiche incomplète (hors paie)


def obtenir_indicateurs_enseignants(db_path: DbPath = None) -> IndicateursEnseignants:
    """Dénombre les enseignants (total/actifs/inactifs, permanents/vacataires). Lecture seule."""
    tous = enseignant_repository.lister(inclure_inactifs=True, db_path=db_path)
    return IndicateursEnseignants(
        total=len(tous),
        actifs=sum(1 for e in tous if e.actif),
        inactifs=sum(1 for e in tous if not e.actif),
        permanents=sum(1 for e in tous if e.statut == StatutEnseignant.PERMANENT),
        vacataires=sum(1 for e in tous if e.statut == StatutEnseignant.VACATAIRE),
        a_completer=sum(1 for e in tous if e.actif and not e.est_complet),
    )


# ---------------------------------------------------------------------
# Recherche et filtres (sections 8-9) — réutilise enseignant_service.rechercher_enseignants
# ---------------------------------------------------------------------

def filtrer_enseignants(
    enseignants: List[Enseignant],
    statut: Optional[StatutEnseignant] = None,
    sexe: Optional[Sexe] = None,
    actif: Optional[bool] = None,
) -> List[Enseignant]:
    """
    Filtre combinable (statut, sexe, état actif) sur une liste déjà
    récupérée. Fonction PURE, aucun accès base : la recherche
    textuelle proprement dite reste dans
    enseignant_service.rechercher_enseignants (module 02), déjà
    insensible à la casse et couvrant nom/prénom/nom complet — non
    dupliquée ici.
    """
    resultat = enseignants
    if statut is not None:
        resultat = [e for e in resultat if e.statut == statut]
    if sexe is not None:
        resultat = [e for e in resultat if e.sexe == sexe]
    if actif is not None:
        resultat = [e for e in resultat if e.actif == actif]
    return resultat


# ---------------------------------------------------------------------
# Synthèse par groupe (statut ou sexe) — sections 13 et 14
# ---------------------------------------------------------------------

@dataclass
class SyntheseGroupe:
    """Agrégat descriptif pur (nombre, heures, gains, net) pour un groupe d'enseignants déjà calculés."""

    libelle: str
    nombre: int
    total_heures: float
    total_gain_heures: int
    total_net: int


def _construire_synthese_par_groupe(resultats: List[ResultatPaie], cle) -> List[SyntheseGroupe]:
    """Regroupe des ResultatPaie déjà calculés selon une fonction `cle`. Pure agrégation, aucun recalcul de paie."""
    groupes: Dict[str, List[ResultatPaie]] = {}
    for resultat in resultats:
        groupes.setdefault(cle(resultat), []).append(resultat)

    return [
        SyntheseGroupe(
            libelle=libelle,
            nombre=len(items),
            total_heures=sum(item.total_heures for item in items),
            total_gain_heures=sum(item.gain_heures for item in items),
            total_net=sum(item.net_a_percevoir for item in items),
        )
        for libelle, items in sorted(groupes.items())
    ]


def synthese_par_statut(resultats: List[ResultatPaie]) -> List[SyntheseGroupe]:
    """Statistiques descriptives Permanent/Vacataire (section 13). Purement descriptif."""
    return _construire_synthese_par_groupe(resultats, cle=lambda r: r.statut.value)


def synthese_par_sexe(resultats: List[ResultatPaie]) -> List[SyntheseGroupe]:
    """
    Statistiques descriptives par sexe (section 14). Purement
    descriptif — aucune conclusion sociale ou RH n'est produite ici,
    uniquement des dénombrements et sommes déjà calculés par le moteur
    de paie.
    """
    return _construire_synthese_par_groupe(resultats, cle=lambda r: r.sexe.value)


# ---------------------------------------------------------------------
# Évolution de la masse salariale (section 12)
# ---------------------------------------------------------------------

@dataclass
class PointEvolution:
    periode_id: int
    libelle: str
    mois: int
    annee: int
    total_gains: int
    total_taxe: int
    total_retenues: int
    total_net: int


def evolution_masse_salariale(db_path: DbPath = None) -> List[PointEvolution]:
    """
    Construit la série chronologique du net total par période, pour
    toutes les périodes disposant de données de paie exploitables
    (BROUILLON et périodes sans aucune donnée sont silencieusement
    ignorées). Chaque point réutilise preparer_etat_comptable, donc
    in fine paie_service — aucun recalcul.
    """
    points: List[PointEvolution] = []
    for periode in sorted(lister_periodes(db_path=db_path), key=lambda p: (p.annee, p.mois)):
        try:
            etat = preparer_etat_comptable(periode.id, db_path=db_path)
        except ComptabiliteError:
            continue  # période non exploitable (brouillon ou sans données) : ignorée, pas une erreur
        points.append(
            PointEvolution(
                periode_id=periode.id,
                libelle=periode.libelle,
                mois=periode.mois,
                annee=periode.annee,
                total_gains=etat.totaux.total_gain_heures + etat.totaux.total_primes,
                total_taxe=etat.totaux.total_taxe,
                total_retenues=etat.totaux.total_retenues,
                total_net=etat.totaux.total_net_a_percevoir,
            )
        )
    return points


# ---------------------------------------------------------------------
# Contrôles de cohérence (section 16) — lecture seule, ne modifie rien
# ---------------------------------------------------------------------

def controler_coherence_resultats(resultats: List[ResultatPaie]) -> List[str]:
    """
    Contrôles de cohérence purement défensifs sur des résultats déjà
    calculés par paie_service. Ne modifie jamais aucune donnée ;
    retourne la liste des anomalies détectées (vide si tout est cohérent).

    Contrôle 1 : base_taxable - taxe - retenue - dette == net_a_percevoir
                 (vérifie que l'identité arithmétique du moteur de paie
                 est respectée pour chaque résultat, defense en profondeur).
    Contrôle 2 : signale tout net à percevoir négatif (cas possible si
                 les retenues dépassent la base, mais à examiner).
    Contrôle 3 : détecte un enseignant apparaissant plusieurs fois dans
                 le même jeu de résultats pour la même période (aucun
                 doublon ne devrait jamais exister).
    """
    anomalies: List[str] = []
    ids_vus = set()

    for resultat in resultats:
        identite = f"{resultat.nom} {resultat.prenom}"

        # Contrôle 1
        net_attendu = resultat.base_taxable - resultat.taxe_5 - resultat.retenue_amicale - resultat.dette
        if net_attendu != resultat.net_a_percevoir:
            anomalies.append(
                f"{identite} : incohérence arithmétique (attendu {net_attendu}, obtenu {resultat.net_a_percevoir})."
            )

        # Contrôle 2
        if resultat.net_a_percevoir < 0:
            anomalies.append(f"{identite} : net à percevoir négatif ({resultat.net_a_percevoir} FCFA).")

        # Contrôle 3
        cle_doublon = (resultat.enseignant_id, resultat.periode_id)
        if cle_doublon in ids_vus:
            anomalies.append(f"{identite} : plusieurs résultats détectés pour la même période (id {cle_doublon}).")
        ids_vus.add(cle_doublon)

    return anomalies


# ---------------------------------------------------------------------
# Historique des bulletins (section 17) — lecture seule du système existant
# ---------------------------------------------------------------------

def etat_bulletins_periode(resultats: List[ResultatPaie], libelle_periode: str) -> Dict[int, bool]:
    """
    Indique, pour chaque enseignant d'une liste de résultats, si un
    bulletin a déjà été généré pour cette période — en relisant
    uniquement le dossier d'export du module 07
    (bulletin_service.bulletin_deja_genere), sans jamais générer ni
    dupliquer le système de génération Word.
    """
    return {
        resultat.enseignant_id: bulletin_service.bulletin_deja_genere(
            resultat.nom, resultat.prenom, libelle_periode
        )
        for resultat in resultats
    }


# ---------------------------------------------------------------------
# Export de la consultation filtrée (section 18) — réutilise le module 06
# ---------------------------------------------------------------------

def exporter_consultation_excel(
    periode_id: int,
    enseignant_ids: Optional[List[int]] = None,
    etablissement: str = "Établissement scolaire",
    db_path: DbPath = None,
) -> Path:
    """
    Exporte la consultation courante au format Excel. Réutilise
    intégralement le générateur du module 06
    (exports.excel_export.generer_classeur_comptable) : aucune
    duplication du code d'export Excel.

    `enseignant_ids` reflète EXACTEMENT la sélection filtrée affichée
    dans le tableau de bord (recherche + filtres statut/sexe/actif
    combinés) :
    - `None` : aucun filtre actif -> export de tous les enseignants de
      la période -> `Consultation_Paie_{periode}.xlsx`.
    - une liste d'un seul identifiant -> export de cet enseignant ->
      `Consultation_Paie_{NOM}_{PRENOM}_{periode}.xlsx`.
    - une liste de plusieurs identifiants (résultat d'un filtre) ->
      export limité à CES enseignants uniquement ->
      `Consultation_Paie_Filtree_{periode}.xlsx`.
    - une liste VIDE (filtres ne correspondant à aucun enseignant) :
      lève ComptabiliteError plutôt que de générer silencieusement un
      fichier vide ou, pire, un export non filtré.
    """
    if enseignant_ids is not None and len(enseignant_ids) == 0:
        raise ComptabiliteError("Aucune donnée à exporter pour les critères sélectionnés.")

    etat: EtatComptablePeriode = preparer_etat_comptable(periode_id, enseignant_ids=enseignant_ids, db_path=db_path)
    classeur = generer_classeur_comptable(etat, etablissement=etablissement)

    libelle_nettoye = nettoyer_nom_fichier(etat.periode.libelle)
    if enseignant_ids is not None and len(enseignant_ids) == 1 and etat.resultats:
        cible = etat.resultats[0]
        nom_fichier = (
            f"Consultation_Paie_{nettoyer_nom_fichier(cible.nom.upper())}_"
            f"{nettoyer_nom_fichier(cible.prenom.upper())}_{libelle_nettoye}.xlsx"
        )
    elif enseignant_ids is not None:
        nom_fichier = f"Consultation_Paie_Filtree_{libelle_nettoye}.xlsx"
    else:
        nom_fichier = f"Consultation_Paie_{libelle_nettoye}.xlsx"

    chemin = chemin_sortie_disponible(nom_fichier, dossier=EXPORT_DIR)
    from exports.logo_excel import ajouter_logo  # import local : la couche export ne dépend pas des services

    ajouter_logo(classeur).save(chemin)
    return chemin
