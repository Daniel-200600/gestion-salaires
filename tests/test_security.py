"""
Tests de utils/security.py (module 11) : hachage et vérification de
mots de passe. Entièrement indépendants de Streamlit et de la base de
données (section 8).
"""

from utils.security import hash_password, verify_password


def test_hash_cree():
    h = hash_password("MonMotDePasse123")
    assert h
    assert isinstance(h, str)


def test_hash_different_du_mot_de_passe_original():
    h = hash_password("MonMotDePasse123")
    assert "MonMotDePasse123" not in h


def test_deux_hash_du_meme_mot_de_passe_sont_differents():
    """Sel aléatoire : deux appels ne doivent jamais produire le même hash."""
    h1 = hash_password("MemeMotDePasse")
    h2 = hash_password("MemeMotDePasse")
    assert h1 != h2


def test_verification_mot_de_passe_correct():
    h = hash_password("MotDePasseCorrect1")
    assert verify_password("MotDePasseCorrect1", h) is True


def test_verification_mot_de_passe_incorrect_refusee():
    h = hash_password("MotDePasseCorrect1")
    assert verify_password("MauvaisMotDePasse", h) is False


def test_verification_hash_malformee_ne_leve_pas():
    assert verify_password("peu importe", "hash_completement_invalide") is False
    assert verify_password("peu importe", "") is False
    assert verify_password("peu importe", "scrypt$abc") is False


def test_verification_algorithme_inconnu_refusee():
    hash_falsifie = "md5$deadbeef"
    assert verify_password("peu importe", hash_falsifie) is False


def test_hash_utilise_bien_scrypt_pas_md5_sha1_sha256_seul():
    h = hash_password("test")
    assert h.startswith("scrypt$")


def test_sensibilite_a_la_casse():
    h = hash_password("MotDePasse")
    assert verify_password("motdepasse", h) is False
    assert verify_password("MOTDEPASSE", h) is False
