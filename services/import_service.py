"""
Service central d'importation massive de données (module 15).

Indépendant de Streamlit : utilisable depuis l'interface, un script,
ou une future API. Réutilise exclusivement les validations déjà
existantes (utils/validators.py) et les repositories déjà existants —
aucune deuxième source de vérité pour les règles métier ou les
formules de paie (services/paie_service.py reste l'unique moteur de
calcul, jamais dupliqué ici).

Pipeline (section 2) :

    Fichier -> Lecture -> Détection format -> Analyse colonnes ->
    Prévisualisation -> Validation technique -> Validation métier ->
    Détection doublons -> Dry run -> Confirmation -> Import
    transactionnel -> Rapport -> Audit

Chaque étape est une fonction pure ou quasi-pure, testable
indépendamment.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

from database.connection import get_connection
from database.repositories import (
    enseignant_repository,
    heures_repository,
    import_repository,
    periode_repository,
)
from models.audit_log import AuditLog
from models.enseignant import Enseignant
from models.enums import (
    NiveauAnomalie,
    StatutImport,
    StatutPeriode,
    StrategieDoublon,
    TypeActionAudit,
    TypeImport,
)
from models.import_journal import AnomalieImport, ImportJournal
from models.saisie_heures import SaisieHeures
from utils.validators import (
    EnseignantValidationError,
    valider_heures,
    valider_nom_ou_prenom,
    valider_sexe,
    valider_statut,
    valider_taux_horaire,
)

DbPath = Optional[Union[str, Path]]

logger = logging.getLogger("salaires_app.import_service")

EXTENSIONS_AUTORISEES = {".xlsx", ".csv"}
TAILLE_MAX_OCTETS = 10 * 1024 * 1024  # 10 Mo — documenté (section 5)


class ImportServiceError(Exception):
    """Erreur de fichier ou de configuration d'import — message toujours compréhensible."""


# ---------------------------------------------------------------------
# Étape A/B — Chargement et lecture (section 5/6)
# ---------------------------------------------------------------------

@dataclass
class ContenuFichier:
    """Résultat de la lecture d'un fichier (section 6) : une ou plusieurs feuilles."""

    nom_fichier: str
    feuilles: Dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def noms_feuilles(self) -> List[str]:
        return list(self.feuilles.keys())


def lire_fichier(chemin: Path, nom_fichier: Optional[str] = None) -> ContenuFichier:
    """
    Lit un fichier .xlsx (toutes feuilles) ou .csv (une seule
    « feuille » nommée `csv`). Contrôle systématiquement : extension,
    existence, taille, lisibilité, présence de données (section 5).

    Ne fait jamais confiance au nom de fichier fourni par
    l'utilisateur pour construire un chemin : `chemin` doit toujours
    être un fichier déjà présent sur un emplacement contrôlé par
    l'application (ex. un fichier temporaire créé par Streamlit),
    jamais un chemin arbitraire assemblé à partir d'une saisie libre.
    """
    nom_affiche = nom_fichier or chemin.name
    extension = Path(nom_affiche).suffix.lower()

    if extension not in EXTENSIONS_AUTORISEES:
        raise ImportServiceError(
            f"Extension non autorisée : « {extension} ». Formats acceptés : .xlsx, .csv."
        )
    if not chemin.exists():
        raise ImportServiceError("Le fichier est introuvable.")
    taille = chemin.stat().st_size
    if taille == 0:
        raise ImportServiceError("Le fichier est vide.")
    if taille > TAILLE_MAX_OCTETS:
        raise ImportServiceError(
            f"Le fichier dépasse la taille maximale autorisée ({TAILLE_MAX_OCTETS // (1024*1024)} Mo)."
        )

    try:
        if extension == ".xlsx":
            classeur = pd.ExcelFile(chemin)
            if not classeur.sheet_names:
                raise ImportServiceError("Le classeur Excel ne contient aucune feuille.")
            feuilles = {}
            for nom_feuille in classeur.sheet_names:
                df = classeur.parse(nom_feuille, dtype=str)
                feuilles[nom_feuille] = df
            if all(df.empty for df in feuilles.values()):
                raise ImportServiceError(
                    "Aucune donnée exploitable dans le classeur (toutes les feuilles sont vides)."
                )
        else:  # .csv
            df = pd.read_csv(chemin, dtype=str)
            if df.empty:
                raise ImportServiceError("Le fichier CSV ne contient aucune ligne de données.")
            feuilles = {"csv": df}
    except ImportServiceError:
        raise
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError, UnicodeDecodeError) as erreur:
        raise ImportServiceError(f"Fichier illisible ou corrompu : {erreur}") from erreur
    except Exception as erreur:  # noqa: BLE001 — jamais de traceback brut à l'utilisateur
        logger.error("Erreur inattendue à la lecture de %s : %s", nom_affiche, erreur)
        raise ImportServiceError("Le fichier n'a pas pu être lu (format inattendu).") from erreur

    return ContenuFichier(nom_fichier=nom_affiche, feuilles=feuilles)


# ---------------------------------------------------------------------
# Normalisation des colonnes (section 7)
# ---------------------------------------------------------------------

VARIANTES_COLONNES: Dict[TypeImport, Dict[str, List[str]]] = {
    TypeImport.ENSEIGNANTS: {
        "nom": ["nom", "nom enseignant", "nom_enseignant"],
        "prenom": ["prenom", "prénom", "prenom enseignant", "prenom_enseignant"],
        "sexe": ["sexe"],
        "statut": ["statut", "statut enseignant"],
        "taux_horaire": ["taux_horaire", "taux horaire", "taux"],
        "email": ["email", "e-mail", "courriel"],
        "telephone": ["telephone", "téléphone", "tel"],
        "adresse": ["adresse"],
    },
    TypeImport.HEURES: {
        "nom": ["nom", "nom enseignant", "nom_enseignant"],
        "prenom": ["prenom", "prénom", "prenom enseignant", "prenom_enseignant"],
        "semaine_1": ["semaine_1", "semaine 1", "s1"],
        "semaine_2": ["semaine_2", "semaine 2", "s2"],
        "semaine_3": ["semaine_3", "semaine 3", "s3"],
        "semaine_4": ["semaine_4", "semaine 4", "s4"],
        "semaine_5": ["semaine_5", "semaine 5", "s5"],
    },
    TypeImport.REMUNERATIONS: {
        "nom": ["nom", "nom enseignant", "nom_enseignant"],
        "prenom": ["prenom", "prénom", "prenom enseignant", "prenom_enseignant"],
        "prime_ap_pp": ["prime_ap_pp", "ap/pp", "ap_pp"],
        "surveillance_secretariat": ["surveillance_secretariat", "surveillance/secretariat", "surveillance"],
        "indemnite_suggestion_admin": ["indemnite_suggestion_admin", "indemnite", "indemnité"],
    },
    TypeImport.RETENUES: {
        "nom": ["nom", "nom enseignant", "nom_enseignant"],
        "prenom": ["prenom", "prénom", "prenom enseignant", "prenom_enseignant"],
        "retenue_amicale": ["retenue_amicale", "retenue amicale"],
        "dette": ["dette"],
    },
}


def _cle_normalisation(valeur: str) -> str:
    return " ".join(str(valeur).strip().lower().replace("_", " ").split())


@dataclass
class ResultatNormalisation:
    correspondance: Dict[str, str]  # colonne brute -> champ canonique
    colonnes_inconnues: List[str]


def normaliser_colonnes(colonnes_brutes: List[str], type_import: TypeImport) -> ResultatNormalisation:
    """
    Associe chaque colonne du fichier à un champ métier canonique
    (section 7). Une colonne inconnue n'est JAMAIS associée par
    approximation dangereuse : elle est listée telle quelle parmi les
    colonnes non reconnues, visible par l'utilisateur.
    """
    variantes = VARIANTES_COLONNES[type_import]
    lookup = {}
    for champ, variantes_champ in variantes.items():
        for variante in variantes_champ:
            lookup[_cle_normalisation(variante)] = champ

    correspondance: Dict[str, str] = {}
    colonnes_inconnues: List[str] = []
    for colonne in colonnes_brutes:
        cle = _cle_normalisation(colonne)
        if cle in lookup:
            correspondance[colonne] = lookup[cle]
        else:
            colonnes_inconnues.append(colonne)

    return ResultatNormalisation(correspondance=correspondance, colonnes_inconnues=colonnes_inconnues)


# ---------------------------------------------------------------------
# Étape analyse / prévisualisation (section 10)
# ---------------------------------------------------------------------

@dataclass
class RapportAnalyse:
    nom_fichier: str
    feuille_choisie: str
    noms_feuilles: List[str]
    nombre_lignes: int
    colonnes_detectees: List[str]
    colonnes_reconnues: Dict[str, str]
    colonnes_inconnues: List[str]
    apercu: List[dict] = field(default_factory=list)


def analyser_fichier(
    contenu: ContenuFichier, type_import: TypeImport, feuille: Optional[str] = None
) -> RapportAnalyse:
    """Analyse une feuille du fichier chargé (section 6/10) — ne modifie jamais la base."""
    nom_feuille = feuille or contenu.noms_feuilles[0]
    if nom_feuille not in contenu.feuilles:
        raise ImportServiceError(f"Feuille introuvable : « {nom_feuille} ».")

    df = contenu.feuilles[nom_feuille]
    if df.empty:
        raise ImportServiceError(f"La feuille « {nom_feuille} » ne contient aucune donnée exploitable.")

    colonnes = [str(c) for c in df.columns]
    normalisation = normaliser_colonnes(colonnes, type_import)

    return RapportAnalyse(
        nom_fichier=contenu.nom_fichier,
        feuille_choisie=nom_feuille,
        noms_feuilles=contenu.noms_feuilles,
        nombre_lignes=len(df),
        colonnes_detectees=colonnes,
        colonnes_reconnues=normalisation.correspondance,
        colonnes_inconnues=normalisation.colonnes_inconnues,
        apercu=df.head(10).fillna("").to_dict(orient="records"),
    )


# ---------------------------------------------------------------------
# Ligne d'import — structure commune à tous les types
# ---------------------------------------------------------------------

class ActionLigne:
    CREATION = "creation"
    MISE_A_JOUR = "mise_a_jour"
    IGNOREE = "ignoree"
    REJETEE = "rejetee"


@dataclass
class LigneImport:
    numero_ligne: int  # 1-based, correspond à la ligne du fichier (hors en-tête)
    donnees: dict
    anomalies: List[AnomalieImport] = field(default_factory=list)
    action: str = ActionLigne.REJETEE
    cible_id: Optional[int] = None  # id de l'enregistrement existant en cas de mise à jour

    @property
    def a_une_erreur(self) -> bool:
        return any(a.niveau == NiveauAnomalie.ERREUR for a in self.anomalies)


def _ajouter_erreur(ligne: LigneImport, champ: Optional[str], valeur, message: str) -> None:
    ligne.anomalies.append(AnomalieImport(
        ligne=ligne.numero_ligne, niveau=NiveauAnomalie.ERREUR, message=message, champ=champ,
        valeur=str(valeur) if valeur is not None else None,
    ))


def _ajouter_avertissement(ligne: LigneImport, champ: Optional[str], valeur, message: str) -> None:
    ligne.anomalies.append(AnomalieImport(
        ligne=ligne.numero_ligne, niveau=NiveauAnomalie.AVERTISSEMENT, message=message, champ=champ,
        valeur=str(valeur) if valeur is not None else None,
    ))


def _valeur_normalisee(row: dict, correspondance: Dict[str, str], champ: str):
    for colonne_brute, champ_canonique in correspondance.items():
        if champ_canonique == champ:
            valeur = row.get(colonne_brute)
            if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
                return None
            valeur_str = str(valeur).strip()
            return valeur_str if valeur_str else None
    return None


@dataclass
class RapportPreparation:
    """Résultat de la préparation (validation + doublons), commun au dry-run et à l'import réel."""

    lignes: List[LigneImport] = field(default_factory=list)

    @property
    def nb_lignes(self) -> int:
        return len(self.lignes)

    @property
    def nb_creations(self) -> int:
        return sum(1 for l in self.lignes if l.action == ActionLigne.CREATION)

    @property
    def nb_mises_a_jour(self) -> int:
        return sum(1 for l in self.lignes if l.action == ActionLigne.MISE_A_JOUR)

    @property
    def nb_ignorees(self) -> int:
        return sum(1 for l in self.lignes if l.action == ActionLigne.IGNOREE)

    @property
    def nb_rejetees(self) -> int:
        return sum(1 for l in self.lignes if l.action == ActionLigne.REJETEE)

    @property
    def nb_erreurs(self) -> int:
        return sum(1 for l in self.lignes for a in l.anomalies if a.niveau == NiveauAnomalie.ERREUR)

    @property
    def nb_avertissements(self) -> int:
        return sum(1 for l in self.lignes for a in l.anomalies if a.niveau == NiveauAnomalie.AVERTISSEMENT)

    @property
    def toutes_anomalies(self) -> List[AnomalieImport]:
        return [a for l in self.lignes for a in l.anomalies]


# ---------------------------------------------------------------------
# Préparation — Import ENSEIGNANTS
# ---------------------------------------------------------------------

def preparer_import_enseignants(
    analyse: RapportAnalyse,
    df: pd.DataFrame,
    strategie_doublon: StrategieDoublon = StrategieDoublon.REFUSER,
    db_path: DbPath = None,
) -> RapportPreparation:
    """
    Valide (technique + métier) chaque ligne et détecte les doublons
    (internes au fichier et contre la base) — SANS jamais écrire en
    base (section 13/14). Une seule requête pour tous les enseignants
    existants (section 26 : jamais une requête par ligne).
    """
    enseignants_existants = enseignant_repository.lister(inclure_inactifs=True, db_path=db_path)
    index_existants = {
        (_cle_normalisation(e.nom), _cle_normalisation(e.prenom)): e for e in enseignants_existants
    }

    rapport = RapportPreparation()
    cles_vues_dans_fichier: Dict[tuple, int] = {}

    for position, row in enumerate(df.to_dict(orient="records"), start=1):
        ligne = LigneImport(numero_ligne=position, donnees=row)

        nom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "nom")
        prenom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "prenom")
        sexe_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "sexe")
        statut_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "statut")
        taux_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "taux_horaire")

        try:
            nom = valider_nom_ou_prenom(nom_brut, "nom")
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "nom", nom_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue
        try:
            prenom = valider_nom_ou_prenom(prenom_brut, "prenom")
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "prenom", prenom_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue
        try:
            if sexe_brut is None:
                raise EnseignantValidationError("Le sexe est obligatoire.")
            sexe = valider_sexe(sexe_brut)
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "sexe", sexe_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue
        try:
            if statut_brut is None:
                raise EnseignantValidationError("Le statut est obligatoire.")
            statut = valider_statut(statut_brut)
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "statut", statut_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue
        try:
            taux_horaire = valider_taux_horaire(taux_brut)
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "taux_horaire", taux_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue

        cle = (_cle_normalisation(nom), _cle_normalisation(prenom))

        if cle in cles_vues_dans_fichier:
            _ajouter_avertissement(
                ligne, "nom", f"{nom} {prenom}",
                f"Doublon interne au fichier (déjà présent à la ligne {cles_vues_dans_fichier[cle]}).",
            )
            ligne.action = ActionLigne.IGNOREE
            rapport.lignes.append(ligne)
            continue
        cles_vues_dans_fichier[cle] = position

        existant = index_existants.get(cle)
        if existant is not None:
            conflit = existant.taux_horaire != taux_horaire or existant.statut != statut or existant.sexe != sexe
            if strategie_doublon == StrategieDoublon.REFUSER:
                _ajouter_erreur(
                    ligne, "nom", f"{nom} {prenom}",
                    f"« {nom} {prenom} » existe déjà en base (id {existant.id}) — stratégie REFUSER.",
                )
                rapport.lignes.append(ligne)
                continue
            elif strategie_doublon == StrategieDoublon.IGNORER:
                _ajouter_avertissement(
                    ligne, "nom", f"{nom} {prenom}", "Enseignant déjà existant — ignoré (stratégie IGNORER)."
                )
                ligne.action = ActionLigne.IGNOREE
                rapport.lignes.append(ligne)
                continue
            else:  # METTRE_A_JOUR
                if conflit:
                    _ajouter_avertissement(
                        ligne, "nom", f"{nom} {prenom}",
                        "Valeurs différentes de la base (taux/statut/sexe) — seront mises à jour.",
                    )
                ligne.action = ActionLigne.MISE_A_JOUR
                ligne.cible_id = existant.id
                ligne.donnees = {
                    "nom": nom, "prenom": prenom, "sexe": sexe, "statut": statut, "taux_horaire": taux_horaire,
                }
                rapport.lignes.append(ligne)
                continue

        ligne.action = ActionLigne.CREATION
        ligne.donnees = {"nom": nom, "prenom": prenom, "sexe": sexe, "statut": statut, "taux_horaire": taux_horaire}
        rapport.lignes.append(ligne)

    return rapport


def executer_import_enseignants(
    rapport_preparation: RapportPreparation,
    nom_fichier: str,
    utilisateur: Optional[str] = None,
    db_path: DbPath = None,
) -> ImportJournal:
    """
    Import réel, transactionnel (section 16) : une seule connexion
    pour toutes les lignes ; ROLLBACK complet en cas d'erreur
    inattendue, COMMIT uniquement si tout s'est déroulé normalement.
    Les lignes REJETEE (déjà écartées lors de la préparation) ne sont
    jamais insérées.
    """
    journal = ImportJournal(
        nom_fichier=nom_fichier, type_import=TypeImport.ENSEIGNANTS, statut=StatutImport.ECHEC,
        utilisateur=utilisateur, nb_lignes=rapport_preparation.nb_lignes,
    )

    with get_connection(db_path) as conn:
        try:
            for ligne in rapport_preparation.lignes:
                if ligne.action == ActionLigne.CREATION:
                    enseignant = Enseignant(
                        nom=ligne.donnees["nom"], prenom=ligne.donnees["prenom"], sexe=ligne.donnees["sexe"],
                        statut=ligne.donnees["statut"], taux_horaire=ligne.donnees["taux_horaire"], actif=True,
                    )
                    enseignant_repository.creer(enseignant, conn=conn)
                elif ligne.action == ActionLigne.MISE_A_JOUR:
                    enseignant = Enseignant(
                        id=ligne.cible_id, nom=ligne.donnees["nom"], prenom=ligne.donnees["prenom"],
                        sexe=ligne.donnees["sexe"], statut=ligne.donnees["statut"],
                        taux_horaire=ligne.donnees["taux_horaire"],
                    )
                    enseignant_repository.mettre_a_jour(enseignant, conn=conn)
        except Exception as erreur:  # noqa: BLE001
            conn.rollback()
            logger.error("Import enseignants annulé (ROLLBACK) : %s", erreur)
            journal.statut = StatutImport.ECHEC
            journal.nb_erreurs = rapport_preparation.nb_erreurs + 1
            journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
            import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
            _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES_ECHEC, db_path=db_path)
            return journal
        else:
            conn.commit()

    journal.statut = StatutImport.TERMINE
    journal.nb_creations = rapport_preparation.nb_creations
    journal.nb_mises_a_jour = rapport_preparation.nb_mises_a_jour
    journal.nb_ignorees = rapport_preparation.nb_ignorees
    journal.nb_rejetees = rapport_preparation.nb_rejetees
    journal.nb_erreurs = rapport_preparation.nb_erreurs
    journal.nb_avertissements = rapport_preparation.nb_avertissements
    journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
    import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
    _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES, db_path=db_path)
    return journal


# ---------------------------------------------------------------------
# Préparation — Import HEURES (respecte le verrouillage des périodes, module 12)
# ---------------------------------------------------------------------

def preparer_import_heures(
    analyse: RapportAnalyse, df: pd.DataFrame, periode_id: int, db_path: DbPath = None
) -> RapportPreparation:
    """
    Valide chaque ligne d'heures. Refuse (erreur par ligne concernée)
    si la période n'autorise pas la modification (module 12) — ne
    contourne jamais cette protection.
    """
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise ImportServiceError(f"Aucune période avec l'id {periode_id}.")
    periode_modifiable = periode.statut == StatutPeriode.OUVERTE

    enseignants_existants = enseignant_repository.lister(inclure_inactifs=True, db_path=db_path)
    index_existants = {(_cle_normalisation(e.nom), _cle_normalisation(e.prenom)): e for e in enseignants_existants}

    rapport = RapportPreparation()
    for position, row in enumerate(df.to_dict(orient="records"), start=1):
        ligne = LigneImport(numero_ligne=position, donnees=row)

        nom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "nom")
        prenom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "prenom")
        try:
            nom = valider_nom_ou_prenom(nom_brut, "nom")
            prenom = valider_nom_ou_prenom(prenom_brut, "prenom")
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "nom", nom_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue

        cle = (_cle_normalisation(nom), _cle_normalisation(prenom))
        enseignant = index_existants.get(cle)
        if enseignant is None:
            _ajouter_erreur(ligne, "nom", f"{nom} {prenom}", f"Enseignant inconnu : « {nom} {prenom} ».")
            rapport.lignes.append(ligne)
            continue

        if not periode_modifiable:
            _ajouter_erreur(
                ligne, "periode", periode.libelle,
                f"Cette période est {periode.statut.value.upper()}. Les données ne peuvent plus être modifiées.",
            )
            rapport.lignes.append(ligne)
            continue

        heures_par_semaine = {}
        erreur_heures = False
        for semaine in range(1, 6):
            champ = f"semaine_{semaine}"
            valeur_brute = _valeur_normalisee(row, analyse.colonnes_reconnues, champ)
            if valeur_brute is None:
                continue
            try:
                heures_par_semaine[semaine] = valider_heures(valeur_brute, champ)
            except ValueError as erreur:
                _ajouter_erreur(ligne, champ, valeur_brute, str(erreur))
                erreur_heures = True
        if erreur_heures:
            rapport.lignes.append(ligne)
            continue

        if not heures_par_semaine:
            _ajouter_avertissement(ligne, None, None, "Aucune heure renseignée sur cette ligne — ignorée.")
            ligne.action = ActionLigne.IGNOREE
            rapport.lignes.append(ligne)
            continue

        ligne.action = ActionLigne.MISE_A_JOUR  # upsert : création ou mise à jour selon l'existant
        ligne.cible_id = enseignant.id
        ligne.donnees = {"enseignant_id": enseignant.id, "heures_par_semaine": heures_par_semaine}
        rapport.lignes.append(ligne)

    return rapport


def executer_import_heures(
    rapport_preparation: RapportPreparation,
    nom_fichier: str,
    periode_id: int,
    utilisateur: Optional[str] = None,
    db_path: DbPath = None,
) -> ImportJournal:
    """Import transactionnel des heures — mêmes garanties que executer_import_enseignants."""
    journal = ImportJournal(
        nom_fichier=nom_fichier, type_import=TypeImport.HEURES, statut=StatutImport.ECHEC,
        utilisateur=utilisateur, periode_id=periode_id, nb_lignes=rapport_preparation.nb_lignes,
    )

    with get_connection(db_path) as conn:
        try:
            for ligne in rapport_preparation.lignes:
                if ligne.action != ActionLigne.MISE_A_JOUR:
                    continue
                for semaine, heures in ligne.donnees["heures_par_semaine"].items():
                    saisie = SaisieHeures(
                        enseignant_id=ligne.donnees["enseignant_id"], periode_id=periode_id,
                        numero_semaine=semaine, heures_effectuees=heures,
                    )
                    heures_repository.upsert(saisie, conn=conn)
        except Exception as erreur:  # noqa: BLE001
            conn.rollback()
            logger.error("Import heures annulé (ROLLBACK) : %s", erreur)
            journal.nb_erreurs = rapport_preparation.nb_erreurs + 1
            journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
            import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
            _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES_ECHEC, db_path=db_path)
            return journal
        else:
            conn.commit()

    journal.statut = StatutImport.TERMINE
    journal.nb_creations = rapport_preparation.nb_mises_a_jour
    journal.nb_ignorees = rapport_preparation.nb_ignorees
    journal.nb_rejetees = rapport_preparation.nb_rejetees
    journal.nb_erreurs = rapport_preparation.nb_erreurs
    journal.nb_avertissements = rapport_preparation.nb_avertissements
    journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
    import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
    _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES, db_path=db_path)
    return journal


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def _journaliser_audit_import(journal: ImportJournal, type_action: TypeActionAudit, db_path: DbPath = None) -> None:
    try:
        from database.repositories import audit_log_repository
        audit_log_repository.enregistrer(
            AuditLog(
                type_action=type_action, entite="import", entite_id=journal.id, utilisateur=journal.utilisateur,
                details=(
                    f"{journal.nom_fichier} ({journal.type_import.value}) — "
                    f"{journal.nb_lignes} ligne(s), {journal.nb_creations} création(s), "
                    f"{journal.nb_mises_a_jour} mise(s) à jour, {journal.nb_rejetees} rejet(s), "
                    f"{journal.nb_erreurs} erreur(s)"
                ),
            ),
            db_path=db_path,
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Impossible de journaliser l'import dans l'audit : %s", erreur)


# ---------------------------------------------------------------------
# Préparation — Import RÉMUNÉRATIONS (respecte le verrouillage des périodes)
# ---------------------------------------------------------------------

def preparer_import_remunerations(
    analyse: RapportAnalyse, df: pd.DataFrame, periode_id: int, db_path: DbPath = None
) -> RapportPreparation:
    """Même structure que preparer_import_heures, pour les 3 éléments de rémunération (section 8C)."""
    from utils.validators import valider_montant_fcfa

    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise ImportServiceError(f"Aucune période avec l'id {periode_id}.")
    periode_modifiable = periode.statut == StatutPeriode.OUVERTE

    enseignants_existants = enseignant_repository.lister(inclure_inactifs=True, db_path=db_path)
    index_existants = {(_cle_normalisation(e.nom), _cle_normalisation(e.prenom)): e for e in enseignants_existants}

    champs_montants = ["prime_ap_pp", "surveillance_secretariat", "indemnite_suggestion_admin"]

    rapport = RapportPreparation()
    for position, row in enumerate(df.to_dict(orient="records"), start=1):
        ligne = LigneImport(numero_ligne=position, donnees=row)

        nom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "nom")
        prenom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "prenom")
        try:
            nom = valider_nom_ou_prenom(nom_brut, "nom")
            prenom = valider_nom_ou_prenom(prenom_brut, "prenom")
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "nom", nom_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue

        cle = (_cle_normalisation(nom), _cle_normalisation(prenom))
        enseignant = index_existants.get(cle)
        if enseignant is None:
            _ajouter_erreur(ligne, "nom", f"{nom} {prenom}", f"Enseignant inconnu : « {nom} {prenom} ».")
            rapport.lignes.append(ligne)
            continue

        if not periode_modifiable:
            _ajouter_erreur(
                ligne, "periode", periode.libelle,
                f"Cette période est {periode.statut.value.upper()}. Les données ne peuvent plus être modifiées.",
            )
            rapport.lignes.append(ligne)
            continue

        montants = {}
        erreur_montant = False
        for champ in champs_montants:
            valeur_brute = _valeur_normalisee(row, analyse.colonnes_reconnues, champ)
            if valeur_brute is None:
                montants[champ] = 0
                continue
            try:
                montants[champ] = valider_montant_fcfa(valeur_brute, champ)
            except ValueError as erreur:
                _ajouter_erreur(ligne, champ, valeur_brute, str(erreur))
                erreur_montant = True
        if erreur_montant:
            rapport.lignes.append(ligne)
            continue

        if all(v == 0 for v in montants.values()):
            _ajouter_avertissement(ligne, None, None, "Aucun montant renseigné sur cette ligne — ignorée.")
            ligne.action = ActionLigne.IGNOREE
            rapport.lignes.append(ligne)
            continue

        ligne.action = ActionLigne.MISE_A_JOUR
        ligne.cible_id = enseignant.id
        ligne.donnees = {"enseignant_id": enseignant.id, "montants": montants}
        rapport.lignes.append(ligne)

    return rapport


def executer_import_remunerations(
    rapport_preparation: RapportPreparation,
    nom_fichier: str,
    periode_id: int,
    utilisateur: Optional[str] = None,
    db_path: DbPath = None,
) -> ImportJournal:
    """Import transactionnel des rémunérations — mêmes garanties que les autres types."""
    from database.repositories import remuneration_repository
    from models.element_remuneration import ElementRemuneration
    from models.enums import TypeElementRemuneration

    journal = ImportJournal(
        nom_fichier=nom_fichier, type_import=TypeImport.REMUNERATIONS, statut=StatutImport.ECHEC,
        utilisateur=utilisateur, periode_id=periode_id, nb_lignes=rapport_preparation.nb_lignes,
    )
    correspondance_type = {
        "prime_ap_pp": TypeElementRemuneration.PRIME_AP_PP,
        "surveillance_secretariat": TypeElementRemuneration.SURVEILLANCE_SECRETARIAT,
        "indemnite_suggestion_admin": TypeElementRemuneration.INDEMNITE_SUGGESTION_ADMIN,
    }

    with get_connection(db_path) as conn:
        try:
            for ligne in rapport_preparation.lignes:
                if ligne.action != ActionLigne.MISE_A_JOUR:
                    continue
                for champ, montant in ligne.donnees["montants"].items():
                    element = ElementRemuneration(
                        enseignant_id=ligne.donnees["enseignant_id"], periode_id=periode_id,
                        type_element=correspondance_type[champ], montant=montant,
                    )
                    remuneration_repository.upsert(element, conn=conn)
        except Exception as erreur:  # noqa: BLE001
            conn.rollback()
            logger.error("Import rémunérations annulé (ROLLBACK) : %s", erreur)
            journal.nb_erreurs = rapport_preparation.nb_erreurs + 1
            journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
            import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
            _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES_ECHEC, db_path=db_path)
            return journal
        else:
            conn.commit()

    journal.statut = StatutImport.TERMINE
    journal.nb_creations = rapport_preparation.nb_mises_a_jour
    journal.nb_ignorees = rapport_preparation.nb_ignorees
    journal.nb_rejetees = rapport_preparation.nb_rejetees
    journal.nb_erreurs = rapport_preparation.nb_erreurs
    journal.nb_avertissements = rapport_preparation.nb_avertissements
    journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
    import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
    _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES, db_path=db_path)
    return journal


# ---------------------------------------------------------------------
# Préparation — Import RETENUES (respecte le verrouillage des périodes)
# ---------------------------------------------------------------------

def preparer_import_retenues(
    analyse: RapportAnalyse, df: pd.DataFrame, periode_id: int, db_path: DbPath = None
) -> RapportPreparation:
    """Même structure que preparer_import_remunerations, pour retenue_amicale/dette (section 8D)."""
    from utils.validators import valider_montant_fcfa

    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    if periode is None:
        raise ImportServiceError(f"Aucune période avec l'id {periode_id}.")
    periode_modifiable = periode.statut == StatutPeriode.OUVERTE

    enseignants_existants = enseignant_repository.lister(inclure_inactifs=True, db_path=db_path)
    index_existants = {(_cle_normalisation(e.nom), _cle_normalisation(e.prenom)): e for e in enseignants_existants}

    champs_montants = ["retenue_amicale", "dette"]

    rapport = RapportPreparation()
    for position, row in enumerate(df.to_dict(orient="records"), start=1):
        ligne = LigneImport(numero_ligne=position, donnees=row)

        nom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "nom")
        prenom_brut = _valeur_normalisee(row, analyse.colonnes_reconnues, "prenom")
        try:
            nom = valider_nom_ou_prenom(nom_brut, "nom")
            prenom = valider_nom_ou_prenom(prenom_brut, "prenom")
        except EnseignantValidationError as erreur:
            _ajouter_erreur(ligne, "nom", nom_brut, str(erreur))
            rapport.lignes.append(ligne)
            continue

        cle = (_cle_normalisation(nom), _cle_normalisation(prenom))
        enseignant = index_existants.get(cle)
        if enseignant is None:
            _ajouter_erreur(ligne, "nom", f"{nom} {prenom}", f"Enseignant inconnu : « {nom} {prenom} ».")
            rapport.lignes.append(ligne)
            continue

        if not periode_modifiable:
            _ajouter_erreur(
                ligne, "periode", periode.libelle,
                f"Cette période est {periode.statut.value.upper()}. Les données ne peuvent plus être modifiées.",
            )
            rapport.lignes.append(ligne)
            continue

        montants = {}
        erreur_montant = False
        for champ in champs_montants:
            valeur_brute = _valeur_normalisee(row, analyse.colonnes_reconnues, champ)
            if valeur_brute is None:
                montants[champ] = 0
                continue
            try:
                montants[champ] = valider_montant_fcfa(valeur_brute, champ)
            except ValueError as erreur:
                _ajouter_erreur(ligne, champ, valeur_brute, str(erreur))
                erreur_montant = True
        if erreur_montant:
            rapport.lignes.append(ligne)
            continue

        if all(v == 0 for v in montants.values()):
            _ajouter_avertissement(ligne, None, None, "Aucun montant renseigné sur cette ligne — ignorée.")
            ligne.action = ActionLigne.IGNOREE
            rapport.lignes.append(ligne)
            continue

        ligne.action = ActionLigne.MISE_A_JOUR
        ligne.cible_id = enseignant.id
        ligne.donnees = {"enseignant_id": enseignant.id, "montants": montants}
        rapport.lignes.append(ligne)

    return rapport


def executer_import_retenues(
    rapport_preparation: RapportPreparation,
    nom_fichier: str,
    periode_id: int,
    utilisateur: Optional[str] = None,
    db_path: DbPath = None,
) -> ImportJournal:
    """Import transactionnel des retenues — mêmes garanties que les autres types."""
    from database.repositories import retenue_repository
    from models.retenue import Retenue
    from models.enums import TypeRetenue

    journal = ImportJournal(
        nom_fichier=nom_fichier, type_import=TypeImport.RETENUES, statut=StatutImport.ECHEC,
        utilisateur=utilisateur, periode_id=periode_id, nb_lignes=rapport_preparation.nb_lignes,
    )
    correspondance_type = {"retenue_amicale": TypeRetenue.RETENUE_AMICALE, "dette": TypeRetenue.DETTE}

    with get_connection(db_path) as conn:
        try:
            for ligne in rapport_preparation.lignes:
                if ligne.action != ActionLigne.MISE_A_JOUR:
                    continue
                for champ, montant in ligne.donnees["montants"].items():
                    retenue = Retenue(
                        enseignant_id=ligne.donnees["enseignant_id"], periode_id=periode_id,
                        type_retenue=correspondance_type[champ], montant=montant,
                    )
                    retenue_repository.upsert(retenue, conn=conn)
        except Exception as erreur:  # noqa: BLE001
            conn.rollback()
            logger.error("Import retenues annulé (ROLLBACK) : %s", erreur)
            journal.nb_erreurs = rapport_preparation.nb_erreurs + 1
            journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
            import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
            _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES_ECHEC, db_path=db_path)
            return journal
        else:
            conn.commit()

    journal.statut = StatutImport.TERMINE
    journal.nb_creations = rapport_preparation.nb_mises_a_jour
    journal.nb_ignorees = rapport_preparation.nb_ignorees
    journal.nb_rejetees = rapport_preparation.nb_rejetees
    journal.nb_erreurs = rapport_preparation.nb_erreurs
    journal.nb_avertissements = rapport_preparation.nb_avertissements
    journal.id = import_repository.enregistrer_import(journal, db_path=db_path)
    import_repository.enregistrer_anomalies(journal.id, rapport_preparation.toutes_anomalies, db_path=db_path)
    _journaliser_audit_import(journal, TypeActionAudit.IMPORT_DONNEES, db_path=db_path)
    return journal
