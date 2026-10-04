"""
Import du fichier de paie mensuel de l'établissement (classeur Excel).

Le classeur habituel compte trois feuilles, reconnues par leurs intitulés
de colonnes (pas par leur nom) :

- **Heures** : S/N, Noms & Prénoms, S1 à S5 (heures de chaque semaine) ;
- **Global** : sexe, statut, taux horaire, gain, primes et indemnités,
  retenues et net de chaque enseignant ;
- **Comptable** : net à percevoir, utilisé seulement pour CONTRÔLER le
  calcul de l'application (jamais importé).

Règles retenues :
- la feuille Heures fait foi pour les heures ; un désaccord avec la
  feuille Global est signalé, pour confirmation ;
- un permanent dont le gain est un montant saisi (sans taux horaire, ou
  sans formule heures × taux) est payé au salaire mensuel fixe ;
- les montants sont recalculés par le moteur de paie (services/paie_service.py) :
  un écart avec le net du fichier est signalé, jamais corrigé en silence.

Déroulement : `lire_fichier_paie` (lecture), `verifier_lignes` (contrôles et
net calculé, autant de fois que l'utilisateur corrige le tableau), puis
`enregistrer_lignes` (création ou mise à jour des fiches et saisie de la
paie de la période, en une seule transaction).
"""

import io
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple, Union

from openpyxl import load_workbook

from database.connection import get_connection
from database.repositories import audit_log_repository, enseignant_repository, periode_repository
from models.audit_log import AuditLog
from models.enseignant import Enseignant
from models.enums import StatutEnseignant, StatutPeriode, TypeActionAudit
from services import donnees_paie_service, enseignant_service, licence_service
from services.donnees_paie_service import DonneesPaieEnseignant
from services.import_service import (
    TAILLE_MAX_OCTETS,
    _cle_identite,
    _cle_normalisation,
    _sont_probablement_la_meme_personne,
    interpreter_sexe,
    interpreter_statut,
    separer_nom_complet,
)
from services.paie_service import _calculer_resultat
from utils.validators import nettoyer_texte

logger = logging.getLogger(__name__)

DbPath = Optional[Union[str, Path]]

EXTENSIONS_ACCEPTEES = {".xlsx", ".xlsm"}

# Intitulés reconnus (forme normalisée : sans accents, minuscules, ponctuation -> espace)
INTITULES: Dict[str, Tuple[str, ...]] = {
    "sn": ("s n", "n", "no", "numero", "n o", "num"),
    "nom": ("noms prenoms", "nom prenom", "noms et prenoms", "nom et prenoms", "nom complet",
            "noms", "nom", "enseignant", "enseignants"),
    "s1": ("s1", "semaine 1", "sem 1"), "s2": ("s2", "semaine 2", "sem 2"), "s3": ("s3", "semaine 3", "sem 3"),
    "s4": ("s4", "semaine 4", "sem 4"), "s5": ("s5", "semaine 5", "sem 5"),
    "total": ("total", "total heures"),
    "sexe": ("sexe", "genre"),
    "statut": ("status", "statut"),
    "taux": ("taux horaire", "taux"),
    "gain": ("gain heures", "gain", "gain horaire", "salaire"),
    "prime_ap_pp": ("prime ap pp", "prime ap", "ap pp"),
    "surveillance": ("surveillance secretariat", "surveillance"),
    "indemnite": ("indemnite suggestion admin", "indemnite"),
    "taxe": ("tax", "taxe"),
    "retenue_amicale": ("retenue amicale", "amicale"),
    "dette": ("dette", "dettes"),
    "net": ("net a percevoir", "net a payer", "net"),
}
_CHAMP_PAR_INTITULE = {intitule: champ for champ, intitules in INTITULES.items() for intitule in intitules}
SEMAINES = ("s1", "s2", "s3", "s4", "s5")

# Colonnes du tableau présenté à l'utilisateur (et relu après ses corrections).
COLONNES = (
    "importer", "sn", "nom_complet", "sexe", "statut", "taux_horaire", "salaire_fixe",
    *SEMAINES, "prime_ap_pp", "surveillance", "indemnite", "retenue_amicale", "dette",
    "net_fichier", "remarques_fichier",
)


class ImportFichierPaieError(ValueError):
    """Fichier illisible ou sans la feuille des enseignants."""


# ---------------------------------------------------------------------
# Lecture du classeur
# ---------------------------------------------------------------------

@dataclass
class FeuilleReconnue:
    nom: str
    role: str  # "global", "heures" ou "comptable"
    ligne_entete: int
    colonnes: Dict[str, int]  # champ -> numéro de colonne (1-based)


@dataclass
class FichierPaie:
    nom_fichier: str
    lignes: List[dict]
    feuilles: List[FeuilleReconnue]
    remarques: List[str] = field(default_factory=list)
    total_net_fichier: Optional[int] = None


def _reconnaitre_entete(feuille) -> Optional[Tuple[int, Dict[str, int]]]:
    for ligne in range(1, min(feuille.max_row, 15) + 1):
        colonnes: Dict[str, int] = {}
        for colonne in range(1, min(feuille.max_column, 60) + 1):
            valeur = feuille.cell(ligne, colonne).value
            if valeur is None:
                continue
            champ = _CHAMP_PAR_INTITULE.get(_cle_normalisation(str(valeur)))
            if champ and champ not in colonnes:
                colonnes[champ] = colonne
        if "nom" in colonnes and len(colonnes) >= 2:
            return ligne, colonnes
    return None


def _role(colonnes: Dict[str, int]) -> Optional[str]:
    if "statut" in colonnes and ("taux" in colonnes or "gain" in colonnes):
        return "global"
    if "s1" in colonnes:
        return "heures"
    if "net" in colonnes:
        return "comptable"
    return None


def _nombre(valeur) -> Optional[Decimal]:
    """Valeur numérique d'une cellule (« 1 800 », « 1500 FCFA », 12,5) ; None si vide ou illisible."""
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        return None
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, (int, float)):
        return Decimal(str(valeur))
    texte = str(valeur).replace(" ", " ").replace(" ", "").replace(",", ".")
    texte = texte.upper().replace("FCFA", "").replace("F", "")
    try:
        return Decimal(texte)
    except InvalidOperation:
        return None


def _entier(valeur) -> Optional[int]:
    nombre = _nombre(valeur)
    return int(nombre.to_integral_value()) if nombre is not None else None


def _heures(valeur) -> Optional[float]:
    nombre = _nombre(valeur)
    return float(nombre) if nombre is not None else None


def _est_formule(cellule) -> bool:
    return isinstance(cellule.value, str) and cellule.value.startswith("=")


def _lignes_feuille(feuille, feuille_formules, reconnue: FeuilleReconnue) -> List[dict]:
    """Lignes de données jusqu'à la ligne de total (ou la fin) ; chaque ligne garde aussi ses cellules de formule."""
    lignes = []
    for numero in range(reconnue.ligne_entete + 1, feuille.max_row + 1):
        nom_brut = feuille.cell(numero, reconnue.colonnes["nom"]).value
        nom = nettoyer_texte(str(nom_brut)) if nom_brut is not None else ""
        if not nom:
            continue
        if _cle_normalisation(nom).startswith("total"):
            break
        valeurs = {champ: feuille.cell(numero, colonne).value for champ, colonne in reconnue.colonnes.items()}
        valeurs["nom"] = nom
        valeurs["_formules"] = {
            champ for champ, colonne in reconnue.colonnes.items()
            if _est_formule(feuille_formules.cell(numero, colonne))
        }
        valeurs["_ligne"] = numero
        lignes.append(valeurs)
    return lignes


def _cle_ligne(ligne: dict) -> tuple:
    return _cle_identite(ligne["nom"], "")


def lire_fichier_paie(contenu: bytes, nom_fichier: str) -> FichierPaie:
    """Lit le classeur et prépare une ligne par enseignant (sans rien écrire en base)."""
    if Path(nom_fichier).suffix.lower() not in EXTENSIONS_ACCEPTEES:
        raise ImportFichierPaieError("Format non pris en charge : choisissez un classeur Excel (.xlsx ou .xlsm).")
    if len(contenu) > TAILLE_MAX_OCTETS:
        raise ImportFichierPaieError(f"Le fichier dépasse {TAILLE_MAX_OCTETS // (1024 * 1024)} Mo.")
    try:
        classeur_valeurs = load_workbook(io.BytesIO(contenu), data_only=True)
        classeur_formules = load_workbook(io.BytesIO(contenu), data_only=False)
    except Exception as erreur:  # noqa: BLE001 — fichier corrompu, protégé, etc.
        raise ImportFichierPaieError(f"Classeur illisible : {erreur}") from erreur

    feuilles: Dict[str, Tuple[FeuilleReconnue, list]] = {}
    for feuille in classeur_valeurs.worksheets:
        trouve = _reconnaitre_entete(feuille)
        if trouve is None:
            continue
        reconnue = FeuilleReconnue(feuille.title, _role(trouve[1]) or "", trouve[0], trouve[1])
        if reconnue.role and reconnue.role not in feuilles:
            feuilles[reconnue.role] = (reconnue, _lignes_feuille(feuille, classeur_formules[feuille.title], reconnue))
    if "global" not in feuilles:
        raise ImportFichierPaieError(
            "Feuille des enseignants introuvable : le classeur doit contenir une feuille avec les colonnes "
            "« Noms & Prénoms », « Statut » et « Taux horaire » (ou « Gain Heures »)."
        )

    remarques: List[str] = []
    reconnue_globale, lignes_globales = feuilles["global"]
    heures = _index_par_ligne(feuilles.get("heures"), lignes_globales, "Heures", remarques)
    comptable = _index_par_ligne(feuilles.get("comptable"), lignes_globales, "Comptable", remarques)
    if "heures" not in feuilles:
        remarques.append("Aucune feuille d'heures (colonnes S1 à S5) : les heures sont lues dans la feuille "
                         f"« {reconnue_globale.nom} ».")
    if "comptable" not in feuilles and "net" not in reconnue_globale.colonnes:
        remarques.append("Aucun net à percevoir dans le fichier : le calcul ne pourra pas être comparé.")

    lignes = [_construire_ligne(g, heures.get(i), comptable.get(i)) for i, g in enumerate(lignes_globales)]
    nets = [ligne["net_fichier"] for ligne in lignes if ligne["net_fichier"] is not None]
    return FichierPaie(
        nom_fichier=nom_fichier, lignes=lignes, feuilles=[f for f, _ in feuilles.values()],
        remarques=remarques, total_net_fichier=sum(nets) if nets else None,
    )


def _index_par_ligne(feuille, lignes_globales: List[dict], libelle: str, remarques: List[str]) -> Dict[int, dict]:
    """Associe chaque ligne de la feuille Global à la ligne correspondante d'une autre feuille (S/N, puis nom)."""
    if feuille is None:
        return {}
    _reconnue, lignes = feuille
    par_sn = {str(_entier(l.get("sn"))): l for l in lignes if _entier(l.get("sn")) is not None}
    par_nom = {_cle_ligne(l): l for l in lignes}
    index, utilisees = {}, set()
    for i, globale in enumerate(lignes_globales):
        sn = _entier(globale.get("sn"))
        trouvee = par_nom.get(_cle_ligne(globale))
        if trouvee is None and sn is not None:
            trouvee = par_sn.get(str(sn))
        if trouvee is not None:
            index[i] = trouvee
            utilisees.add(id(trouvee))
    absentes = [l["nom"] for l in lignes if id(l) not in utilisees]
    if absentes:
        remarques.append(f"Feuille {libelle} : {len(absentes)} ligne(s) sans correspondance dans la feuille des "
                         "enseignants, ignorée(s) : " + ", ".join(absentes[:5]) + ("…" if len(absentes) > 5 else "."))
    return index


def _texte_heures(valeur: Optional[float]) -> str:
    return "vide" if valeur is None else f"{valeur:g} h"


def _construire_ligne(globale: dict, heures: Optional[dict], comptable: Optional[dict]) -> dict:
    remarques: List[str] = []
    ligne = {"importer": True, "sn": _entier(globale.get("sn")), "nom_complet": globale["nom"]}

    if heures is not None and _cle_ligne(heures) != _cle_ligne(globale):
        remarques.append(f"Nom écrit autrement dans la feuille des heures : « {heures['nom']} ».")

    sexe = interpreter_sexe(str(globale["sexe"])) if globale.get("sexe") not in (None, "") else None
    statut = interpreter_statut(str(globale["statut"])) if globale.get("statut") not in (None, "") else None
    ligne["sexe"] = sexe.value if sexe else None
    ligne["statut"] = statut.value if statut else None
    ligne["taux_horaire"] = _entier(globale.get("taux"))

    # Heures : la feuille des heures fait foi ; la feuille Global ne sert qu'au contrôle.
    for semaine in SEMAINES:
        valeur_globale = _heures(globale.get(semaine))
        if heures is not None:
            valeur = _heures(heures.get(semaine))
            # Formule sans valeur enregistrée (fichier jamais recalculé par Excel) : rien à comparer.
            non_calculee = valeur_globale is None and semaine in globale["_formules"]
            if (valeur or 0) != (valeur_globale or 0) and semaine in globale and not non_calculee:
                remarques.append(
                    f"{semaine.upper()} : {_texte_heures(valeur)} dans la feuille des heures, "
                    f"{_texte_heures(valeur_globale)} dans la feuille Global (la feuille des heures est retenue)."
                )
        else:
            valeur = valeur_globale
        ligne[semaine] = valeur
    total_heures = sum(ligne[s] or 0 for s in SEMAINES)
    total_fichier = _heures(globale.get("total"))
    if total_fichier is not None and total_fichier != total_heures:
        remarques.append(f"Total du fichier : {total_fichier:g} h ; somme des semaines retenues : {total_heures:g} h.")

    # Permanent au salaire fixe : gain saisi directement (pas de taux, ou pas de formule heures × taux).
    gain = _entier(globale.get("gain"))
    ligne["salaire_fixe"] = None
    if statut == StatutEnseignant.PERMANENT and gain is not None and (
        ligne["taux_horaire"] is None or "gain" not in globale["_formules"]
    ):
        ligne["salaire_fixe"] = gain
    elif gain is not None and ligne["taux_horaire"] is not None and "gain" not in globale["_formules"]:
        attendu = Decimal(str(total_heures)) * ligne["taux_horaire"]
        if Decimal(gain) != attendu:
            remarques.append(f"Gain saisi à la main dans le fichier ({gain} FCFA) au lieu de heures × taux "
                             f"({attendu:.0f} FCFA) : le calcul retient heures × taux.")

    for champ in ("prime_ap_pp", "surveillance", "indemnite", "retenue_amicale", "dette"):
        ligne[champ] = _entier(globale.get(champ)) or 0

    net = _entier(comptable.get("net")) if comptable is not None else None
    ligne["net_fichier"] = net if net is not None else _entier(globale.get("net"))
    ligne["remarques_fichier"] = " ".join(remarques)
    return ligne


# ---------------------------------------------------------------------
# Vérification (après lecture, puis après chaque correction)
# ---------------------------------------------------------------------

@dataclass
class LigneVerifiee:
    donnees: dict
    enseignant_existant: Optional[Enseignant] = None
    erreurs: List[str] = field(default_factory=list)  # bloquantes
    remarques: List[str] = field(default_factory=list)  # à vérifier
    modifications: List[str] = field(default_factory=list)  # changements de la fiche existante
    net_calcule: Optional[int] = None

    @property
    def action(self) -> str:
        if not self.donnees.get("importer"):
            return "Ignorée"
        return "Mise à jour" if self.enseignant_existant is not None else "Création"

    @property
    def ecart(self) -> Optional[int]:
        net_fichier = self.donnees.get("net_fichier")
        if self.net_calcule is None or net_fichier is None:
            return None
        return self.net_calcule - net_fichier


def _valeur_ou_none(valeur):
    if valeur is None:
        return None
    if isinstance(valeur, float) and valeur != valeur:  # NaN : cellule vide du tableau
        return None
    if isinstance(valeur, str) and not valeur.strip():
        return None
    return valeur


def verifier_lignes(lignes: List[dict], periode_id: int, db_path: DbPath = None) -> List[LigneVerifiee]:
    """Contrôle chaque ligne, la rapproche des fiches existantes et calcule le net avec le moteur de paie."""
    periode = periode_repository.obtenir_par_id(periode_id, db_path=db_path)
    existants = enseignant_repository.lister(inclure_inactifs=True, db_path=db_path)
    par_cle = {_cle_identite(e.nom, e.prenom): e for e in existants}
    vus: Dict[tuple, int] = {}
    resultat = []
    for donnees_brutes in lignes:
        donnees = {colonne: _valeur_ou_none(donnees_brutes.get(colonne)) for colonne in COLONNES}
        donnees["importer"] = bool(donnees_brutes.get("importer", True))
        # Le tableau modifié rend des nombres décimaux (1800.0) : montants ramenés à des entiers FCFA.
        for champ in ("sn", "taux_horaire", "salaire_fixe", "prime_ap_pp", "surveillance", "indemnite",
                      "retenue_amicale", "dette", "net_fichier"):
            donnees[champ] = _entier(donnees.get(champ))
        ligne = LigneVerifiee(donnees=donnees)
        if donnees.get("remarques_fichier"):
            ligne.remarques.append(donnees["remarques_fichier"])
        resultat.append(ligne)
        if not donnees["importer"]:
            continue
        _verifier_ligne(ligne, par_cle, existants, vus, periode)
    return resultat


def _verifier_ligne(ligne: LigneVerifiee, par_cle, existants, vus, periode) -> None:
    d = ligne.donnees
    nom_complet = nettoyer_texte(str(d.get("nom_complet") or ""))
    if not nom_complet:
        ligne.erreurs.append("Nom absent.")
        return
    cle = _cle_identite(nom_complet, "")
    if cle in vus:
        ligne.erreurs.append(f"Même enseignant que la ligne S/N {vus[cle]} : gardez une seule des deux lignes.")
    vus[cle] = d.get("sn") or "?"

    sexe = interpreter_sexe(str(d["sexe"])) if d.get("sexe") else None
    statut = interpreter_statut(str(d["statut"])) if d.get("statut") else None
    if sexe is None:
        ligne.erreurs.append("Sexe manquant ou illisible (M ou F).")
    if statut is None:
        ligne.erreurs.append("Statut manquant ou illisible (V ou P).")
    existant = par_cle.get(cle)
    taux, salaire = _remuneration_effective(d, statut, existant)
    if taux is not None and taux < 0 or salaire is not None and salaire < 0:
        ligne.erreurs.append("Montant négatif.")
    if salaire is not None and statut == StatutEnseignant.VACATAIRE:
        ligne.erreurs.append("Le salaire mensuel fixe est réservé aux permanents.")
    if taux is None and not (statut == StatutEnseignant.PERMANENT and salaire is not None):
        ligne.erreurs.append("Taux horaire manquant." if statut != StatutEnseignant.PERMANENT
                             else "Taux horaire ou salaire fixe manquant.")

    heures = {}
    for numero, semaine in enumerate(SEMAINES, start=1):
        valeur = _heures(d.get(semaine))
        if d.get(semaine) is not None and valeur is None:
            ligne.erreurs.append(f"{semaine.upper()} : nombre d'heures illisible.")
        elif valeur is not None and valeur < 0:
            ligne.erreurs.append(f"{semaine.upper()} : heures négatives.")
        heures[numero] = valeur or 0.0
    montants = {}
    for champ in ("prime_ap_pp", "surveillance", "indemnite", "retenue_amicale", "dette"):
        montant = _entier(d.get(champ)) or 0
        if montant < 0:
            ligne.erreurs.append("Montant négatif.")
        montants[champ] = montant

    if existant is None:
        proche = next((e for e in existants if _sont_probablement_la_meme_personne(cle, _cle_identite(e.nom, e.prenom))),
                      None)
        if proche is not None:
            ligne.remarques.append(f"Nom proche d'un enseignant déjà enregistré (« {proche.nom} {proche.prenom} ») : "
                                   "une nouvelle fiche sera créée, vérifiez qu'il ne s'agit pas du même.")
    else:
        ligne.enseignant_existant = existant
        if not existant.actif:
            ligne.erreurs.append("Enseignant désactivé : réactivez-le dans Gestion › Enseignants, ou décochez la ligne.")
        for libelle, avant, apres in (
            ("Sexe", existant.sexe.value if existant.sexe else None, sexe.value if sexe else None),
            ("Statut", existant.statut.value if existant.statut else None, statut.value if statut else None),
            ("Taux horaire", existant.taux_horaire, _entier(d.get("taux_horaire"))),
            ("Salaire fixe", existant.salaire_fixe, _entier(d.get("salaire_fixe"))),
        ):
            if apres is not None and apres != avant:
                ligne.modifications.append(f"{libelle} : {avant if avant is not None else 'vide'} → {apres}")

    if ligne.erreurs or periode is None:
        return
    enseignant = SimpleNamespace(id=existant.id if existant else 0, nom=nom_complet, prenom="", sexe=sexe,
                                 statut=statut, taux_horaire=taux or 0, salaire_fixe=salaire)
    calcul = _calculer_resultat(
        periode.id, enseignant, heures,
        {"prime_ap_pp": montants["prime_ap_pp"], "surveillance_secretariat": montants["surveillance"],
         "indemnite_suggestion_admin": montants["indemnite"]},
        {"retenue_amicale": montants["retenue_amicale"], "dette": montants["dette"]},
        taux_taxe=periode.taux_taxe, taxe_permanents=periode.taxe_permanents,
    )
    ligne.net_calcule = calcul.net_a_percevoir
    if ligne.ecart:
        ligne.remarques.append(f"Net du fichier : {d['net_fichier']} FCFA ; net calculé : {ligne.net_calcule} FCFA "
                               f"(écart de {ligne.ecart:+d} FCFA).")


# ---------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------

@dataclass
class RapportImportPaie:
    nb_crees: int = 0
    nb_mis_a_jour: int = 0
    nb_lignes: int = 0


def nombre_enseignants_avec_donnees(periode_id: int, db_path: DbPath = None) -> int:
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT enseignant_id) FROM saisies_heures WHERE periode_id = ?", (periode_id,)
        ).fetchone()[0]


def enregistrer_lignes(
    lignes: List[LigneVerifiee], periode_id: int, nom_fichier: str,
    utilisateur: Optional[str] = None, db_path: DbPath = None,
) -> RapportImportPaie:
    """
    Crée ou met à jour les fiches, puis enregistre heures, primes et retenues
    de la période — en une seule transaction : en cas d'erreur, rien n'est
    enregistré. Refusé si une ligne à importer comporte une erreur.
    """
    a_importer = [ligne for ligne in lignes if ligne.donnees.get("importer")]
    if not a_importer:
        raise ImportFichierPaieError("Aucune ligne à importer.")
    en_erreur = [ligne for ligne in a_importer if ligne.erreurs]
    if en_erreur:
        raise ImportFichierPaieError(
            f"{len(en_erreur)} ligne(s) comportent une erreur : corrigez-les ou décochez-les avant d'enregistrer."
        )
    creations = [ligne for ligne in a_importer if ligne.enseignant_existant is None]
    try:
        licence_service.verifier_ajout_enseignants(len(creations), db_path=db_path)
    except licence_service.LicenceRequiseError as erreur:
        raise ImportFichierPaieError(str(erreur)) from erreur

    changements_statut = []
    rapport = RapportImportPaie(nb_lignes=len(a_importer))
    with get_connection(db_path) as conn:
        try:
            periode = periode_repository.obtenir_par_id(periode_id, conn=conn)
            if periode is None or periode.statut != StatutPeriode.OUVERTE:
                raise ImportFichierPaieError("La période doit être ouverte pour recevoir les données de paie.")
            for ligne in a_importer:
                enseignant = _fiche(ligne)
                if ligne.enseignant_existant is None:
                    enseignant.id = enseignant_repository.creer(enseignant, conn=conn)
                    rapport.nb_crees += 1
                else:
                    if enseignant.statut != ligne.enseignant_existant.statut:
                        changements_statut.append((ligne.enseignant_existant, enseignant.statut))
                    enseignant_repository.mettre_a_jour(enseignant, conn=conn)
                    rapport.nb_mis_a_jour += 1
                d = ligne.donnees
                donnees_paie_service.ecrire_donnees_paie(conn, periode_id, DonneesPaieEnseignant(
                    enseignant_id=enseignant.id,
                    heures_par_semaine={n: _heures(d.get(s)) or 0.0 for n, s in enumerate(SEMAINES, start=1)},
                    prime_ap_pp=_entier(d.get("prime_ap_pp")) or 0,
                    surveillance_secretariat=_entier(d.get("surveillance")) or 0,
                    indemnite_suggestion_admin=_entier(d.get("indemnite")) or 0,
                    retenue_amicale=_entier(d.get("retenue_amicale")) or 0,
                    dette=_entier(d.get("dette")) or 0,
                ))
        except Exception as erreur:
            conn.rollback()
            logger.error("Import du fichier de paie annulé : %s", erreur)
            if isinstance(erreur, ImportFichierPaieError):
                raise
            raise ImportFichierPaieError(f"Import annulé, rien n'a été enregistré : {erreur}") from erreur
        conn.commit()

    for existant, nouveau_statut in changements_statut:
        enseignant_service.journaliser_changement_statut(existant, nouveau_statut, utilisateur, db_path)
    audit_log_repository.enregistrer(
        AuditLog(
            type_action=TypeActionAudit.IMPORT_DONNEES, entite="periode", entite_id=periode_id,
            utilisateur=utilisateur,
            details=(f"Fichier de paie « {nom_fichier} » : {rapport.nb_lignes} enseignant(s), "
                     f"{rapport.nb_crees} fiche(s) créée(s), {rapport.nb_mis_a_jour} mise(s) à jour."),
        ),
        db_path=db_path,
    )
    return rapport


def _remuneration_effective(d: dict, statut, existant: Optional[Enseignant]) -> Tuple[Optional[int], Optional[int]]:
    """
    Taux horaire et salaire fixe qui seront enregistrés : ceux du tableau ; pour
    une fiche existante, une case vide garde la valeur de la fiche (le salaire
    fixe n'est conservé que pour un permanent).
    """
    taux, salaire = _entier(d.get("taux_horaire")), _entier(d.get("salaire_fixe"))
    if existant is not None:
        if taux is None:
            taux = existant.taux_horaire
        if salaire is None and statut == StatutEnseignant.PERMANENT:
            salaire = existant.salaire_fixe
    return taux, salaire


def _fiche(ligne: LigneVerifiee) -> Enseignant:
    d = ligne.donnees
    existant = ligne.enseignant_existant
    nom, prenom = separer_nom_complet(str(d["nom_complet"]))
    statut = interpreter_statut(str(d["statut"]))
    taux, salaire = _remuneration_effective(d, statut, existant)
    if existant is None:
        return Enseignant(nom=nom, prenom=prenom, sexe=interpreter_sexe(str(d["sexe"])), statut=statut,
                          taux_horaire=taux, salaire_fixe=salaire)
    # Fiche existante : le nom enregistré est conservé ; une case vide ne retire rien.
    return Enseignant(
        id=existant.id, nom=existant.nom, prenom=existant.prenom, sexe=interpreter_sexe(str(d["sexe"])),
        statut=statut, taux_horaire=taux, salaire_fixe=salaire,
        email=existant.email, telephone=existant.telephone, adresse=existant.adresse, actif=existant.actif,
    )


__all__ = [
    "ImportFichierPaieError", "FichierPaie", "LigneVerifiee", "RapportImportPaie", "COLONNES", "SEMAINES",
    "lire_fichier_paie", "verifier_lignes", "enregistrer_lignes", "nombre_enseignants_avec_donnees",
]
