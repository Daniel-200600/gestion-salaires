"""Tests de utils/montant_en_lettres.py — cas requis par l'énoncé du module 07."""

import pytest

from utils.montant_en_lettres import montant_en_lettres


@pytest.mark.parametrize(
    "montant, attendu",
    [
        (0, "Zero"),
        (1, "One"),
        (10, "Ten"),
        (100, "One Hundred"),
        (1000, "One Thousand"),
        (23415, "Twenty Three Thousand Four Hundred Fifteen"),  # forme utilisée sur les bulletins
        (100000, "One Hundred Thousand"),
        (1000000, "One Million"),
    ],
)
def test_cas_requis_par_enonce(montant, attendu):
    assert montant_en_lettres(montant) == attendu


def test_montant_avec_arrondi_taxe():
    """Cas typique d'un net issu d'un arrondi de taxe (ex: base=15 -> taxe arrondie à 1 -> net=14)."""
    assert montant_en_lettres(14) == "Fourteen"


def test_cas_integrite_module05_module06():
    """Le montant net de l'exemple officiel (100h x 2000 FCFA, etc.) doit se convertir correctement."""
    assert montant_en_lettres(208250) == "Two Hundred Eight Thousand Two Hundred Fifty"


def test_dizaine_sans_unite():
    assert montant_en_lettres(20) == "Twenty"
    assert montant_en_lettres(50) == "Fifty"


def test_nombre_juste_sous_mille():
    assert montant_en_lettres(999) == "Nine Hundred Ninety Nine"


def test_million_avec_reste():
    assert montant_en_lettres(1234567) == "One Million Two Hundred Thirty Four Thousand Five Hundred Sixty Seven"


def test_pas_de_and_ni_tiret():
    resultat = montant_en_lettres(23415)
    mots = resultat.split(" ")
    assert "and" not in [mot.lower() for mot in mots]
    assert "-" not in resultat


def test_montant_negatif_gere_proprement():
    assert montant_en_lettres(-100) == "Minus One Hundred"


def test_toujours_une_chaine_non_vide():
    for montant in [0, 5, 999999, 2_000_000]:
        resultat = montant_en_lettres(montant)
        assert isinstance(resultat, str)
        assert resultat.strip() != ""
