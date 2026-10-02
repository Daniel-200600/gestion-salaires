"""
Lancement de l'application : écoute locale uniquement, une seule instance,
bouton « Quitter l'application ».
"""

import socket
import tomllib
from pathlib import Path

import launcher
from utils import session_auth

RACINE = Path(__file__).resolve().parent.parent


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_l_application_n_ecoute_que_sur_cet_ordinateur():
    with open(RACINE / ".streamlit" / "config.toml", "rb") as fichier:
        assert tomllib.load(fichier)["server"]["address"] == "127.0.0.1"
    assert launcher.ADRESSE == "127.0.0.1"
    assert launcher._url(8501) == "http://127.0.0.1:8501"


def test_aucune_instance_detectee_sur_un_port_libre():
    assert launcher.application_deja_lancee(_port_libre()) is False


def test_second_lancement_rouvre_le_navigateur_sans_seconde_instance(monkeypatch):
    from streamlit.web import bootstrap

    ouverts, demarrages = [], []
    monkeypatch.setattr(launcher, "application_deja_lancee", lambda port=None: True)
    monkeypatch.setattr(launcher.webbrowser, "open", ouverts.append)
    monkeypatch.setattr(bootstrap, "run", lambda *a, **k: demarrages.append(a))

    launcher.main()

    assert ouverts == ["http://127.0.0.1:8501"]
    assert demarrages == []


def test_quitter_arrete_le_serveur_apres_un_court_delai(monkeypatch):
    minuteries = []

    class MinuterieFactice:
        def __init__(self, delai, fonction, args=()):
            minuteries.append((delai, fonction, args))

        def start(self):
            pass

    monkeypatch.setattr(session_auth.threading, "Timer", MinuterieFactice)
    session_auth.arreter_application()
    assert minuteries == [(1.0, session_auth.os._exit, (0,))]


def test_bouton_quitter_sur_l_ecran_de_connexion_et_dans_la_barre_laterale():
    source = (RACINE / "utils" / "session_auth.py").read_text(encoding="utf-8")
    assert '_bouton_quitter("quitter_connexion")' in source
    assert '_bouton_quitter("quitter_barre_laterale")' in source
