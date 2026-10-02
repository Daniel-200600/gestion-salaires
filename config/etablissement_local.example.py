"""
Modèle de config/etablissement_local.py (à copier sous ce nom, puis à
compléter). Ce fichier local, exclu de Git, porte l'en-tête et le logo
réels de l'établissement :

    python templates/build_template.py --etablissement --pdf

produit alors les modèles de bulletin de l'établissement dans
data/modeles_etablissement/, que l'application utilise à la place des
modèles neutres livrés dans templates/.
"""

from config.settings import ASSETS_DIR

ETABLISSEMENT_ENTETE_FR = [
    "REPUBLIQUE DU CAMEROUN",
    "Paix – Travail – Patrie",
    "REGION DE ...",
    "DELEGATION REGIONALE DES ENSEIGNEMENTS SECONDAIRES",
    "DELEGATION DEPARTEMENTALE DE ...",
    "NOM DE L'ETABLISSEMENT",
]
ETABLISSEMENT_ENTETE_EN = [
    "REPUBLIC OF CAMEROON",
    "Peace – Work – Fatherland",
    "... REGION",
    "REGIONAL DELEGATION OF SECONDARY EDUCATION",
    "... DIVISIONAL DELEGATION",
    "SCHOOL NAME",
]

# Logo placé à côté des autres images de l'application (fichier exclu de Git).
LOGO_ETABLISSEMENT_PATH = ASSETS_DIR / "logo_etablissement.png"
