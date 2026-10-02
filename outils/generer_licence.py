"""
Outil de l'auteur : création des clés de licence de Gestion des Salaires.

Cet outil n'est PAS livré avec l'application. Il utilise la clé privée de
l'auteur, conservée hors du projet (par défaut dans
Documents\\GestionPaie_Licences) : sans elle, aucune clé ne peut être créée.
Sauvegardez ce dossier sur un support externe.

Utilisation (depuis le dossier salaires_app) :

    python outils/generer_licence.py init
        Crée la paire de clés (une seule fois) et affiche la clé publique à
        placer dans services/licence_service.py (CLE_PUBLIQUE_B64).

    python outils/generer_licence.py creer --etablissement "Nom" --machine XXXX-XXXX-XXXX-XXXX [--expire AAAA-MM-JJ]
        Crée une clé pour l'ordinateur dont le client vous a donné le code
        machine (Administration › Licence). Sans --expire : licence sans
        limite de durée. La clé est écrite dans un fichier .cle et inscrite
        au registre des licences (registre_licences.csv).

    python outils/generer_licence.py verifier <clé ou fichier .cle>
        Affiche le contenu d'une clé après vérification de sa signature.
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from services.licence_service import (  # noqa: E402
    LicenceInvalideError,
    _b64_encoder,
    decoder_cle,
    encoder_cle,
    formater_code_machine,
)

DOSSIER_PAR_DEFAUT = Path.home() / "Documents" / "GestionPaie_Licences"
NOM_CLE_PRIVEE = "cle_privee_licences.pem"
NOM_REGISTRE = "registre_licences.csv"
COLONNES_REGISTRE = ["numero", "etablissement", "code_machine", "date_emission", "date_expiration", "fichier"]


def _cle_publique_b64(cle_privee: Ed25519PrivateKey) -> str:
    brute = cle_privee.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return _b64_encoder(brute)


def _charger_cle_privee(dossier: Path) -> Ed25519PrivateKey:
    chemin = dossier / NOM_CLE_PRIVEE
    if not chemin.exists():
        sys.exit(f"Clé privée introuvable : {chemin}. Lancez d'abord « init » (ou indiquez --dossier).")
    return serialization.load_pem_private_key(chemin.read_bytes(), password=None)


def initialiser(dossier: Path) -> None:
    chemin = dossier / NOM_CLE_PRIVEE
    if chemin.exists():
        sys.exit(f"Une clé privée existe déjà ({chemin}) : elle n'est jamais remplacée. Les licences déjà "
                 "délivrées en dépendent.")
    dossier.mkdir(parents=True, exist_ok=True)
    cle_privee = Ed25519PrivateKey.generate()
    chemin.write_bytes(cle_privee.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    print(f"Clé privée créée : {chemin}")
    print("Sauvegardez ce dossier sur un support externe et ne le communiquez à personne.")
    print(f"Clé publique (CLE_PUBLIQUE_B64) : {_cle_publique_b64(cle_privee)}")


def _numero_suivant(registre: Path) -> str:
    annee = date.today().year
    numeros = []
    if registre.exists():
        with registre.open(encoding="utf-8-sig", newline="") as fichier:
            for ligne in csv.DictReader(fichier, delimiter=";"):
                trouve = re.fullmatch(rf"L-{annee}-(\d+)", ligne.get("numero", ""))
                if trouve:
                    numeros.append(int(trouve.group(1)))
    return f"L-{annee}-{max(numeros, default=0) + 1:03d}"


def creer(dossier: Path, etablissement: str, machine: str, expire: str = None) -> Path:
    cle_privee = _charger_cle_privee(dossier)
    etablissement = " ".join(etablissement.split())
    code = formater_code_machine(machine)
    if len(re.sub(r"[^0-9A-Z]", "", code)) != 16:
        sys.exit("Code machine invalide : 16 caractères attendus (XXXX-XXXX-XXXX-XXXX).")
    if not etablissement:
        sys.exit("Indiquez le nom de l'établissement.")
    date_expiration = date.fromisoformat(expire) if expire else None
    if date_expiration is not None and date_expiration < date.today():
        sys.exit("La date d'expiration est déjà passée.")

    registre = dossier / NOM_REGISTRE
    numero = _numero_suivant(registre)
    charge = json.dumps(
        {"n": numero, "e": etablissement, "m": code, "d": date.today().isoformat(),
         "x": date_expiration.isoformat() if date_expiration else None},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    cle = encoder_cle(charge, cle_privee.sign(charge))
    licence = decoder_cle(cle, _cle_publique_b64(cle_privee))  # contrôle immédiat

    nom_court = re.sub(r"[^0-9A-Za-z]+", "_", etablissement).strip("_")[:40] or "etablissement"
    fichier = dossier / f"Licence_{numero}_{nom_court}.cle"
    fichier.write_text(cle + "\n", encoding="utf-8")
    nouveau = not registre.exists()
    with registre.open("a", encoding="utf-8-sig", newline="") as sortie:
        ecrivain = csv.DictWriter(sortie, fieldnames=COLONNES_REGISTRE, delimiter=";")
        if nouveau:
            ecrivain.writeheader()
        ecrivain.writerow({
            "numero": numero, "etablissement": etablissement, "code_machine": code,
            "date_emission": licence.date_emission.isoformat(),
            "date_expiration": licence.date_expiration.isoformat() if licence.date_expiration else "",
            "fichier": fichier.name,
        })
    print(f"Licence {numero} — {etablissement} — ordinateur {code} — {licence.libelle_validite}")
    print(f"Fichier : {fichier}")
    print(cle)
    return fichier


def verifier(texte: str, dossier: Path) -> None:
    chemin = Path(texte)
    if chemin.suffix.lower() == ".cle" and chemin.exists():
        texte = chemin.read_text(encoding="utf-8")
    cle_publique = None
    if (dossier / NOM_CLE_PRIVEE).exists():
        cle_publique = _cle_publique_b64(_charger_cle_privee(dossier))
    try:
        licence = decoder_cle(texte, cle_publique)
    except LicenceInvalideError as erreur:
        sys.exit(str(erreur))
    print(f"Licence {licence.numero} — {licence.etablissement} — ordinateur {licence.code_machine} — "
          f"émise le {licence.date_emission.strftime('%d/%m/%Y')}, {licence.libelle_validite}")


def main(arguments=None) -> None:
    analyseur = argparse.ArgumentParser(description="Clés de licence de Gestion des Salaires (outil de l'auteur).")
    analyseur.add_argument("--dossier", type=Path, default=DOSSIER_PAR_DEFAUT,
                           help=f"Dossier de la clé privée et du registre (défaut : {DOSSIER_PAR_DEFAUT}).")
    commandes = analyseur.add_subparsers(dest="commande", required=True)
    commandes.add_parser("init", help="Créer la paire de clés (une seule fois).")
    creation = commandes.add_parser("creer", help="Créer une clé de licence.")
    creation.add_argument("--etablissement", required=True)
    creation.add_argument("--machine", required=True, help="Code machine affiché dans Administration › Licence.")
    creation.add_argument("--expire", help="Date d'expiration AAAA-MM-JJ (facultative).")
    verification = commandes.add_parser("verifier", help="Vérifier une clé ou un fichier .cle.")
    verification.add_argument("cle")
    options = analyseur.parse_args(arguments)

    if options.commande == "init":
        initialiser(options.dossier)
    elif options.commande == "creer":
        creer(options.dossier, options.etablissement, options.machine, options.expire)
    else:
        verifier(options.cle, options.dossier)


if __name__ == "__main__":
    main()
