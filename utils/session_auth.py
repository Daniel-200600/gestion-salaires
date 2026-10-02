"""
Gestion centralisée de la session et de la protection des pages
(module 11).

Seul module du projet qui connaît à la fois Streamlit et
l'authentification. Chaque page appelle `exiger_authentification()`
(ou `exiger_permission(...)`) tout en haut de son script, AVANT toute
logique métier ou tout accès aux données : c'est ce qui empêche
l'accès direct à une page en naviguant vers son URL, puisque Streamlit
réexécute intégralement le script de la page à chaque navigation.

Aucune logique de sécurité dispersée dans les pages : celles-ci se
contentent d'appeler ces deux fonctions, jamais de vérifier `role`
elles-mêmes.
"""

import os
import threading
import time
from typing import Optional

import streamlit as st

from config.settings import SESSION_TIMEOUT_SECONDES
from database.repositories import utilisateur_repository
from models.enums import RoleUtilisateur
from models.utilisateur import Utilisateur
from services import auth_service, permission_service, utilisateur_service
from services.auth_service import ResultatConnexion
from services.utilisateur_service import UtilisateurValidationError

_CLE_AUTHENTICATED = "authenticated"
_CLE_USER_ID = "user_id"
_CLE_USERNAME = "username"
_CLE_NOM_COMPLET = "nom_complet"
_CLE_ROLE = "role"
_CLE_DERNIERE_ACTIVITE = "derniere_activite"
_CLE_BIENVENUE_VUE = "bienvenue_vue"

LIBELLES_ROLES = {
    RoleUtilisateur.ADMIN: "Administrateur",
    RoleUtilisateur.GESTIONNAIRE_PAIE: "Gestionnaire de paie",
    RoleUtilisateur.CONSULTATION: "Consultation",
}


def _session_expiree() -> bool:
    derniere_activite = st.session_state.get(_CLE_DERNIERE_ACTIVITE)
    if derniere_activite is None:
        return False
    return (time.time() - derniere_activite) > SESSION_TIMEOUT_SECONDES


def est_authentifie() -> bool:
    if not st.session_state.get(_CLE_AUTHENTICATED, False):
        return False
    if _session_expiree():
        _purger_session()
        return False

    # Revalidation systématique (module 19) : un compte désactivé ou un
    # rôle modifié entre-temps par un administrateur ne doit jamais
    # continuer à s'appliquer avec les anciennes valeurs mises en cache
    # lors de la connexion initiale — jamais seulement une expiration
    # temporelle. Une session sans user_id valide (état incohérent) est
    # traitée comme non authentifiée plutôt que de lever une exception.
    utilisateur_id = st.session_state.get(_CLE_USER_ID)
    if utilisateur_id is None:
        _purger_session()
        return False
    utilisateur_a_jour = auth_service.revalider_session(utilisateur_id)
    if utilisateur_a_jour is None:
        _purger_session()
        return False

    # Rafraîchit le cache de session avec l'état réel (rôle/nom à jour).
    st.session_state[_CLE_ROLE] = utilisateur_a_jour.role.value
    st.session_state[_CLE_NOM_COMPLET] = utilisateur_a_jour.nom_complet
    return True


def utilisateur_courant_id() -> Optional[int]:
    """Identifiant de l'utilisateur connecté, transmis aux services qui revérifient ses droits en base."""
    return st.session_state.get(_CLE_USER_ID)


def utilisateur_courant_role() -> Optional[RoleUtilisateur]:
    valeur = st.session_state.get(_CLE_ROLE)
    return RoleUtilisateur(valeur) if valeur else None


def _demarrer_session(utilisateur: Utilisateur) -> None:
    """
    Stocke UNIQUEMENT les informations nécessaires dans st.session_state
    (section 13) : jamais le mot de passe, jamais le hash.
    """
    st.session_state[_CLE_AUTHENTICATED] = True
    st.session_state[_CLE_USER_ID] = utilisateur.id
    st.session_state[_CLE_USERNAME] = utilisateur.username
    st.session_state[_CLE_NOM_COMPLET] = utilisateur.nom_complet
    st.session_state[_CLE_ROLE] = utilisateur.role.value
    st.session_state[_CLE_DERNIERE_ACTIVITE] = time.time()


def _purger_session() -> None:
    for cle in (_CLE_AUTHENTICATED, _CLE_USER_ID, _CLE_USERNAME, _CLE_NOM_COMPLET, _CLE_ROLE, _CLE_DERNIERE_ACTIVITE):
        st.session_state.pop(cle, None)


def deconnexion() -> None:
    """Journalise la déconnexion puis purge intégralement la session."""
    if st.session_state.get(_CLE_AUTHENTICATED, False):
        auth_service.deconnecter(st.session_state.get(_CLE_USER_ID), st.session_state.get(_CLE_USERNAME))
    _purger_session()


def arreter_application() -> None:
    """
    Arrête le serveur de l'application (bouton « Quitter l'application »).
    Sans cela, fermer le navigateur laisse le programme tourner en
    arrière-plan. L'arrêt est différé d'une seconde pour que le message
    de confirmation ait le temps de s'afficher.
    """
    threading.Timer(1.0, os._exit, args=(0,)).start()


def _bouton_quitter(cle: str) -> None:
    if st.button("Quitter l'application", icon=":material/power_settings_new:", key=cle):
        deconnexion()
        st.info("L'application est arrêtée. Vous pouvez fermer cet onglet du navigateur.")
        arreter_application()
        st.stop()


def _afficher_formulaire_initialisation_admin() -> None:
    """
    Affiché uniquement lorsqu'AUCUN utilisateur n'existe encore en
    base (première installation, section 23). Aucun mot de passe par
    défaut n'est jamais créé automatiquement : c'est la personne ayant
    un accès physique à l'application qui choisit elle-même le premier
    identifiant et mot de passe administrateur.
    """
    st.title("Première configuration")
    st.subheader("Création du premier compte administrateur")
    st.info(
        "Aucun compte n'existe encore dans cette installation. Le compte créé ici disposera du rôle "
        "Administrateur : il permettra ensuite de créer les autres comptes depuis "
        "Administration & Sécurité › Administration."
    )
    st.caption("Mot de passe : 8 caractères minimum. Aucun mot de passe n'est fourni par défaut.")

    with st.form("formulaire_initialisation_admin"):
        nom = st.text_input("Nom")
        prenom = st.text_input("Prénom")
        username = st.text_input("Nom d'utilisateur")
        mot_de_passe = st.text_input("Mot de passe", type="password")
        confirmation = st.text_input("Confirmer le mot de passe", type="password")
        soumis = st.form_submit_button("Créer le compte administrateur", type="primary")

    if soumis:
        try:
            utilisateur_service.creer_utilisateur(
                nom=nom, prenom=prenom, username=username,
                mot_de_passe=mot_de_passe, confirmation_mot_de_passe=confirmation,
                role=RoleUtilisateur.ADMIN, actif=True,
            )
            st.success("Compte administrateur créé. Vous pouvez maintenant vous connecter.")
            st.rerun()
        except UtilisateurValidationError as erreur:
            st.error(str(erreur))

    st.stop()


def _afficher_formulaire_connexion() -> None:
    from config.settings import NOM_APPLICATION

    st.title("Connexion")
    st.caption(f"{NOM_APPLICATION} — saisissez les identifiants de votre compte.")

    with st.form("formulaire_connexion"):
        username = st.text_input("Nom d'utilisateur", autocomplete="username")
        mot_de_passe = st.text_input("Mot de passe", type="password", autocomplete="current-password")
        soumis = st.form_submit_button("Se connecter", type="primary")

    if soumis:
        resultat: ResultatConnexion = auth_service.connecter(username, mot_de_passe)
        if resultat.reussie:
            _demarrer_session(resultat.utilisateur)
            st.rerun()
        else:
            st.error(resultat.message)

    st.caption("Mot de passe oublié : un administrateur peut le réinitialiser depuis la page Administration.")
    if st.button("Retour à la présentation"):
        st.session_state[_CLE_BIENVENUE_VUE] = False
        st.rerun()
    _bouton_quitter("quitter_connexion")
    st.stop()


def exiger_authentification() -> None:
    """
    À appeler tout en haut de CHAQUE page protégée. Affiche l'écran de
    connexion (ou l'initialisation du premier compte administrateur si
    la base ne contient encore aucun utilisateur) et interrompt
    l'exécution du script (`st.stop()`) si l'utilisateur n'est pas
    authentifié — empêche donc tout accès direct à une page sans être
    connecté, quelle que soit la manière dont Streamlit y a été amené.
    """
    if est_authentifie():
        st.session_state[_CLE_DERNIERE_ACTIVITE] = time.time()  # session active : prolonge l'expiration
        return

    if not st.session_state.get(_CLE_BIENVENUE_VUE, False):
        _afficher_ecran_bienvenue()
        return

    if utilisateur_repository.compter_tout() == 0:
        _afficher_formulaire_initialisation_admin()
    else:
        _afficher_formulaire_connexion()


def _afficher_ecran_bienvenue() -> None:
    """
    Écran de présentation affiché une fois par session, avant l'écran de
    connexion. Contenu factuel : ce que fait le logiciel, qui peut y
    accéder, et accès en lecture à la politique de confidentialité et
    aux conditions d'utilisation. N'affecte jamais l'authentification
    elle-même (gérée exclusivement par _afficher_formulaire_connexion /
    _afficher_formulaire_initialisation_admin).
    """
    from config.settings import LOGO_SYMBOLE_PATH, NOM_APPLICATION, TAUX_TAXE, VERSION
    from services import parametres_service
    from utils.documentation import DocumentationIntrouvableError, lire_document

    colonne_logo, colonne_titre = st.columns([1, 11], vertical_alignment="center")
    with colonne_logo:
        if LOGO_SYMBOLE_PATH.exists():
            st.image(str(LOGO_SYMBOLE_PATH), width=64, caption=None)
    with colonne_titre:
        st.title(NOM_APPLICATION)
        etablissement = parametres_service.charger_parametres().nom_etablissement.strip()
        if etablissement:
            st.caption(etablissement)

    st.write(
        "Logiciel de gestion de la paie des enseignants : saisie des heures et des éléments de "
        "rémunération, calcul du net à payer, édition des bulletins de solde et des états comptables, "
        "contrôle puis clôture des périodes de paie."
    )

    try:
        from services.parametres_paie_service import formater_taux, obtenir_taux_taxe_defaut
        taux = formater_taux(obtenir_taux_taxe_defaut())
    except Exception:  # noqa: BLE001 — écran d'accueil : jamais bloquant (base pas encore initialisée)
        taux = f"{float(TAUX_TAXE) * 100:g} %"
    fonctions = [
        ("Saisie et calcul",
         f"Heures hebdomadaires, taux horaire, primes, indemnités et retenues. Calcul du net à payer "
         f"avec application de la taxe ({taux} par défaut, taux réglable par l'administrateur)."),
        ("Bulletins et états",
         "Bulletins de solde au format Word ou PDF, fidèles au modèle de l'établissement. États comptables, rapports et statistiques exportables "
         "au format Excel."),
        ("Contrôle et clôture",
         "Détection des anomalies avant validation. Une période clôturée n'est plus modifiable."),
        ("Accès et traçabilité",
         "Comptes nominatifs avec trois rôles : Administrateur, Gestionnaire de paie, Consultation. "
         "Les opérations sensibles sont enregistrées dans un journal d'audit."),
    ]
    colonnes = st.columns(len(fonctions))
    for colonne, (titre, description) in zip(colonnes, fonctions):
        with colonne:
            with st.container(border=True):
                st.markdown(f"**{titre}**")
                st.caption(description)

    if utilisateur_repository.compter_tout() == 0:
        st.info(
            "Première utilisation : aucun compte n'existe encore. L'étape suivante permet de créer "
            "le compte administrateur."
        )
    else:
        st.write(
            "L'accès est réservé aux personnes disposant d'un compte. Les comptes sont créés par un "
            "administrateur de l'établissement."
        )

    if st.button("Continuer vers la connexion", type="primary"):
        st.session_state[_CLE_BIENVENUE_VUE] = True
        st.rerun()

    st.divider()
    for cle, libelle in (
        ("politique_confidentialite", "Politique de confidentialité"),
        ("conditions_utilisation", "Conditions générales d'utilisation"),
    ):
        with st.expander(libelle):
            try:
                st.markdown(lire_document(cle))
            except DocumentationIntrouvableError as erreur:
                st.warning(str(erreur))

    st.caption(f"{NOM_APPLICATION} — version {VERSION}")
    st.stop()


def exiger_permission(permission: str) -> None:
    """
    Exige l'authentification PUIS la permission donnée
    (services.permission_service). Affiche un message clair et
    interrompt le script si la permission est refusée — jamais un
    accès silencieusement dégradé.
    """
    exiger_authentification()
    role = utilisateur_courant_role()
    if role is None or not permission_service.a_permission(role, permission):
        st.error("Accès refusé : votre rôle ne dispose pas de la permission nécessaire pour cette page.")
        st.stop()


def _afficher_etat_licence() -> None:
    from services import licence_service

    etat = licence_service.etat_licence()
    if etat.active:
        st.caption(f"Licence : {etat.licence.etablissement}")
    else:
        st.caption(
            f":orange[Mode démonstration ({licence_service.LIMITE_DEMO_ENSEIGNANTS} enseignants au maximum)]"
        )


def afficher_bandeau_utilisateur() -> None:
    """Affiche discrètement l'utilisateur connecté, un bouton de déconnexion, et le pied de page applicatif (module 20)."""
    from config.settings import NOM_APPLICATION, VERSION

    role = utilisateur_courant_role()
    with st.sidebar:
        st.caption(f"Connecté : {st.session_state.get(_CLE_NOM_COMPLET, '')}")
        st.caption(f"Rôle : {LIBELLES_ROLES.get(role, '')}")
        if st.button("Se déconnecter", icon=":material/logout:"):
            deconnexion()
            st.rerun()
        _bouton_quitter("quitter_barre_laterale")
        st.divider()
        st.caption(f"{NOM_APPLICATION} — version {VERSION}")
        _afficher_etat_licence()
