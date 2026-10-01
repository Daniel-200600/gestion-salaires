"""
Hachage et vérification de mots de passe (module 11).

Utilise `hashlib.scrypt` (bibliothèque standard Python, aucune
dépendance externe requise) : une fonction de dérivation de clé
« memory-hard » spécifiquement conçue pour le hachage de mots de
passe, recommandée par l'OWASP au même titre que bcrypt/argon2 —
jamais MD5, SHA1, ni SHA256 seul, qui sont explicitement interdits
pour cet usage.

Format de hash auto-descriptif (les paramètres scrypt sont stockés
avec le hash) : `scrypt$n$r$p$sel_hex$hash_hex`. Cela permet de faire
évoluer les paramètres à l'avenir sans invalider les mots de passe
déjà enregistrés.

Aucune fonction de ce module ne dépend de Streamlit : entièrement
testable en isolation (section 8 du module 11).
"""

import hashlib
import hmac
import secrets

_ALGORITHME = "scrypt"
_N = 2**14  # coût CPU/mémoire
_R = 8
_P = 1
_TAILLE_CLE = 32
_TAILLE_SEL = 16


def hash_password(mot_de_passe: str) -> str:
    """
    Produit un hash sûr d'un mot de passe, avec un sel aléatoire
    unique à chaque appel (deux appels avec le même mot de passe
    produisent des hashs différents).
    """
    sel = secrets.token_bytes(_TAILLE_SEL)
    derive = hashlib.scrypt(
        mot_de_passe.encode("utf-8"), salt=sel, n=_N, r=_R, p=_P, dklen=_TAILLE_CLE
    )
    return f"{_ALGORITHME}${_N}${_R}${_P}${sel.hex()}${derive.hex()}"


def verify_password(mot_de_passe: str, hash_stocke: str) -> bool:
    """
    Vérifie un mot de passe contre un hash stocké, sans jamais avoir
    besoin de connaître le mot de passe original à partir du hash.
    Comparaison en temps constant (hmac.compare_digest) pour limiter
    les attaques par mesure de temps.

    Retourne False (jamais d'exception) pour tout hash malformé ou
    utilisant un algorithme inconnu — un hash corrompu ne doit jamais
    faire planter une tentative de connexion.
    """
    try:
        algorithme, n_str, r_str, p_str, sel_hex, hash_hex = hash_stocke.split("$")
        if algorithme != _ALGORITHME:
            return False
        sel = bytes.fromhex(sel_hex)
        hash_attendu = bytes.fromhex(hash_hex)
        n, r, p = int(n_str), int(r_str), int(p_str)
    except (ValueError, AttributeError):
        return False

    derive = hashlib.scrypt(
        mot_de_passe.encode("utf-8"), salt=sel, n=n, r=r, p=p, dklen=len(hash_attendu)
    )
    return hmac.compare_digest(derive, hash_attendu)
