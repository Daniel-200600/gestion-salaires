"""
Licence d'utilisation du logiciel.

Une clé de licence est délivrée par l'auteur pour UN ordinateur (son
« code machine ») et, si besoin, jusqu'à une date d'expiration. Elle est
signée avec la clé privée de l'auteur (Ed25519) : l'application ne
contient que la clé publique, qui permet de vérifier une clé mais jamais
d'en fabriquer une. Outil de l'auteur : outils/generer_licence.py.

Sans licence valide, le logiciel fonctionne en mode démonstration :
- au plus LIMITE_DEMO_ENSEIGNANTS enseignants enregistrés ;
- si la base en contient davantage (licence expirée, base copiée sur un
  autre ordinateur), la paie des périodes ouvertes n'est plus calculée.
Les données ne sont jamais bloquées : consultation, périodes validées ou
clôturées, sauvegardes et restauration restent accessibles.
"""

import base64
import binascii
import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DbPath = Optional[Union[str, Path]]

PREFIXE_CLE = "GPAIE1"
# Clé publique Ed25519 de l'auteur (la clé privée correspondante n'est
# jamais livrée avec l'application).
CLE_PUBLIQUE_B64 = "G8c1XFAf8VvTT8NHvwXdpW8o7uk2G8hTKSMHf-K2okg"
LIMITE_DEMO_ENSEIGNANTS = 5
NOM_FICHIER_LICENCE = "licence.cle"


class LicenceInvalideError(ValueError):
    """Clé de licence illisible, falsifiée, d'un autre ordinateur ou expirée."""


class LicenceRequiseError(ValueError):
    """Action refusée en mode démonstration."""


@dataclass(frozen=True)
class Licence:
    numero: str
    etablissement: str
    code_machine: str
    date_emission: date
    date_expiration: Optional[date] = None

    @property
    def libelle_validite(self) -> str:
        if self.date_expiration is None:
            return "sans limite de durée"
        return f"jusqu'au {self.date_expiration.strftime('%d/%m/%Y')}"


@dataclass(frozen=True)
class EtatLicence:
    active: bool
    licence: Optional[Licence] = None
    motif: str = ""  # pourquoi le mode démonstration s'applique


# ---------------------------------------------------------------------
# Code machine
# ---------------------------------------------------------------------

def _identifiant_brut_machine() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as cle:
                return str(winreg.QueryValueEx(cle, "MachineGuid")[0])
        except OSError:
            pass
    for chemin in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            contenu = Path(chemin).read_text(encoding="utf-8").strip()
            if contenu:
                return contenu
        except OSError:
            continue
    return f"{uuid.getnode():012x}"


def _normaliser_code(code: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(code).upper())


def formater_code_machine(code: str) -> str:
    brut = _normaliser_code(code)
    return "-".join(brut[i:i + 4] for i in range(0, len(brut), 4))


@lru_cache(maxsize=1)
def code_machine() -> str:
    """Code de cet ordinateur, à communiquer à l'auteur pour obtenir une licence."""
    empreinte = hashlib.sha256(f"GestionPaie|{_identifiant_brut_machine()}".encode("utf-8")).hexdigest()
    return formater_code_machine(empreinte[:16])


# ---------------------------------------------------------------------
# Clé de licence
# ---------------------------------------------------------------------

def _b64_decoder(texte: str) -> bytes:
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def _b64_encoder(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).decode("ascii").rstrip("=")


def encoder_cle(charge: bytes, signature: bytes) -> str:
    """Assemble une clé (utilisé par l'outil de l'auteur)."""
    return f"{PREFIXE_CLE}.{_b64_encoder(charge)}.{_b64_encoder(signature)}"


def decoder_cle(texte: str, cle_publique_b64: Optional[str] = None) -> Licence:
    """Vérifie la signature d'une clé et en extrait la licence (sans vérifier l'ordinateur ni la date)."""
    compacte = re.sub(r"\s+", "", texte or "")
    morceaux = compacte.split(".")
    if len(morceaux) != 3 or morceaux[0] != PREFIXE_CLE:
        raise LicenceInvalideError(
            "Ce texte n'est pas une clé de licence de Gestion des Salaires (elle commence par « GPAIE1. »). "
            "Copiez la clé en entier."
        )
    try:
        charge, signature = _b64_decoder(morceaux[1]), _b64_decoder(morceaux[2])
        cle_publique = Ed25519PublicKey.from_public_bytes(_b64_decoder(cle_publique_b64 or CLE_PUBLIQUE_B64))
        cle_publique.verify(signature, charge)
        donnees = json.loads(charge.decode("utf-8"))
        return Licence(
            numero=str(donnees["n"]),
            etablissement=str(donnees["e"]),
            code_machine=formater_code_machine(donnees["m"]),
            date_emission=date.fromisoformat(donnees["d"]),
            date_expiration=date.fromisoformat(donnees["x"]) if donnees.get("x") else None,
        )
    except (InvalidSignature, binascii.Error, ValueError, KeyError, TypeError) as erreur:
        raise LicenceInvalideError(
            "Clé de licence invalide : elle a été modifiée ou mal copiée. Copiez-la à nouveau en entier, "
            "ou demandez une nouvelle clé à l'auteur."
        ) from erreur


def _verifier_applicable(licence: Licence, aujourdhui: date) -> None:
    if _normaliser_code(licence.code_machine) != _normaliser_code(code_machine()):
        raise LicenceInvalideError(
            f"Cette clé a été délivrée pour un autre ordinateur (code {licence.code_machine}). "
            f"Le code de cet ordinateur est {code_machine()} : communiquez-le à l'auteur pour obtenir sa clé."
        )
    if licence.date_expiration is not None and aujourdhui > licence.date_expiration:
        raise LicenceInvalideError(
            f"La licence n° {licence.numero} a expiré le {licence.date_expiration.strftime('%d/%m/%Y')}. "
            "Contactez l'auteur pour la renouveler."
        )


# ---------------------------------------------------------------------
# Licence installée
# ---------------------------------------------------------------------

def chemin_licence() -> Path:
    from config.settings import DATA_DIR

    return Path(DATA_DIR) / NOM_FICHIER_LICENCE


@lru_cache(maxsize=4)
def _licence_du_fichier(chemin: str, date_modification_ns: int, taille: int) -> Licence:
    # Mise en cache par état du fichier : la paie est calculée enseignant par enseignant.
    return decoder_cle(Path(chemin).read_text(encoding="utf-8"))


def etat_licence(aujourdhui: Optional[date] = None) -> EtatLicence:
    chemin = chemin_licence()
    if not chemin.exists():
        return EtatLicence(active=False, motif="Aucune licence n'est installée sur cet ordinateur.")
    try:
        infos = chemin.stat()
        licence = _licence_du_fichier(str(chemin), infos.st_mtime_ns, infos.st_size)
        _verifier_applicable(licence, aujourdhui or date.today())
    except (LicenceInvalideError, OSError) as erreur:
        return EtatLicence(active=False, motif=str(erreur))
    return EtatLicence(active=True, licence=licence)


def licence_active() -> bool:
    return etat_licence().active


def activer_licence(texte: str, utilisateur: Optional[str] = None, db_path: DbPath = None) -> Licence:
    """Vérifie la clé (signature, ordinateur, date) puis l'installe. Rien n'est modifié si elle est refusée."""
    licence = decoder_cle(texte)
    _verifier_applicable(licence, date.today())
    chemin = chemin_licence()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(re.sub(r"\s+", "", texte) + "\n", encoding="utf-8")
    os.replace(temporaire, chemin)

    from database.repositories import audit_log_repository
    from models.audit_log import AuditLog
    from models.enums import TypeActionAudit

    audit_log_repository.enregistrer(
        AuditLog(
            type_action=TypeActionAudit.MODIFICATION, entite="licence", entite_id=None, utilisateur=utilisateur,
            details=f"Licence n° {licence.numero} activée : {licence.etablissement}, {licence.libelle_validite}.",
        ),
        db_path=db_path,
    )
    return licence


# ---------------------------------------------------------------------
# Mode démonstration
# ---------------------------------------------------------------------

def _nombre_enseignants(db_path: DbPath) -> int:
    from database.repositories import enseignant_repository

    return enseignant_repository.compter(db_path=db_path)


def places_restantes_demo(db_path: DbPath = None) -> Optional[int]:
    """None si une licence est active ; sinon le nombre d'enseignants encore autorisés."""
    if licence_active():
        return None
    return max(0, LIMITE_DEMO_ENSEIGNANTS - _nombre_enseignants(db_path))


def message_limite_demo() -> str:
    return (
        f"Mode démonstration : {LIMITE_DEMO_ENSEIGNANTS} enseignants au maximum. Pour enregistrer tous vos "
        "enseignants, activez une licence (Administration › Licence)."
    )


def verifier_ajout_enseignants(nombre: int = 1, db_path: DbPath = None) -> None:
    places = places_restantes_demo(db_path)
    if places is not None and nombre > places:
        raise LicenceRequiseError(message_limite_demo())


def verifier_calcul_autorise(db_path: DbPath = None) -> None:
    """Sans licence, la paie d'une période ouverte n'est calculée que si la base reste dans la limite."""
    if licence_active() or _nombre_enseignants(db_path) <= LIMITE_DEMO_ENSEIGNANTS:
        return
    raise LicenceRequiseError(
        f"Licence requise : cette base compte plus de {LIMITE_DEMO_ENSEIGNANTS} enseignants et aucune licence "
        f"valide n'est active. {etat_licence().motif} La paie des périodes ouvertes ne peut pas être calculée ; "
        "les périodes validées ou clôturées restent consultables. Activez une licence dans "
        "Administration › Licence."
    )
