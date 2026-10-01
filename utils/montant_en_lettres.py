"""
Conversion d'un montant entier FCFA en toutes lettres (anglais).

Utilisé exclusivement pour l'affichage du « montant en lettres » sur
les bulletins de solde Word (cf. services/bulletin_service.py,
exports/word_export.py). Cette fonction ne recalcule RIEN : elle
convertit tel quel le montant `net_a_percevoir` déjà produit par le
moteur de paie (services/paie_service.py) — aucune deuxième
implémentation de la logique de paie.

Format retenu (aligné sur le modèle officiel fourni) : mots en
Title Case, séparés par des espaces, sans « and » ni trait d'union.

Exemple : 23415 -> "Twenty Three Thousand Four Hundred Fifteen"
(la forme utilisée sur les bulletins de solde).
"""

UNITES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]

DIX_A_DIX_NEUF = [
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen",
]

DIZAINES = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
]

# (valeur de l'échelle, mot anglais correspondant), du plus grand au plus petit
ECHELLES = (
    (1_000_000_000, "Billion"),
    (1_000_000, "Million"),
    (1_000, "Thousand"),
)


def _trois_chiffres_en_lettres(nombre: int) -> str:
    """Convertit un nombre entier de 0 à 999 en lettres anglaises."""
    if nombre == 0:
        return ""

    mots = []
    centaines, reste = divmod(nombre, 100)
    if centaines:
        mots.append(UNITES[centaines])
        mots.append("Hundred")

    if reste:
        if reste < 10:
            mots.append(UNITES[reste])
        elif reste < 20:
            mots.append(DIX_A_DIX_NEUF[reste - 10])
        else:
            dizaine, unite = divmod(reste, 10)
            mots.append(DIZAINES[dizaine])
            if unite:
                mots.append(UNITES[unite])

    return " ".join(mots)


def montant_en_lettres(montant: int) -> str:
    """
    Convertit un montant entier (FCFA) en toutes lettres anglaises,
    en Title Case, sans « and » ni trait d'union.

    >>> montant_en_lettres(23415)
    'Twenty Three Thousand Four Hundred Fifteen'
    >>> montant_en_lettres(0)
    'Zero'
    >>> montant_en_lettres(1000000)
    'One Million'
    """
    montant = int(montant)

    if montant < 0:
        return "Minus " + montant_en_lettres(-montant)
    if montant == 0:
        return "Zero"

    groupes = []
    reste = montant
    for valeur_echelle, nom_echelle in ECHELLES:
        if reste >= valeur_echelle:
            quotient, reste = divmod(reste, valeur_echelle)
            groupes.append(f"{_trois_chiffres_en_lettres(quotient)} {nom_echelle}")

    if reste:
        groupes.append(_trois_chiffres_en_lettres(reste))

    return " ".join(groupes)
