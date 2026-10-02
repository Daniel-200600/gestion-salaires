"""
Séparation stricte ADMINISTRATEUR / autres rôles, vérifiée CÔTÉ SERVICE.

Chaque opération sensible exposée par services/administration_service.py
est appelée directement (sans interface) avec un compte de chaque rôle :
seul l'administrateur actif est autorisé. Un contrôle statique vérifie
aussi que les pages n'appellent jamais directement les fonctions de bas
niveau correspondantes, ce qui contournerait ce contrôle.
"""

import ast
import sqlite3
from pathlib import Path

import pytest

import database.connection as database_connection
from models.enums import RoleUtilisateur, TypeActionAudit
from services import (
    administration_service,
    auth_service,
    enseignant_service,
    parametres_service,
    periode_service,
    utilisateur_service,
)
from services.autorisation_service import AutorisationRefuseeError, exiger_permission_utilisateur
from services import permission_service
from services.utilisateur_service import UtilisateurValidationError

RACINE = Path(__file__).resolve().parent.parent
MDP = "Motdepasse-Solide-1"


@pytest.fixture
def comptes(db_path, monkeypatch):
    monkeypatch.setattr(database_connection, "DB_PATH", db_path)
    monkeypatch.setattr(auth_service, "_tentatives_echouees", {})
    admin = utilisateur_service.creer_utilisateur("Admin", "Principal", "admin", MDP, RoleUtilisateur.ADMIN, db_path=db_path)
    gestion = utilisateur_service.creer_utilisateur(
        "Gestion", "Paie", "gestion", MDP, RoleUtilisateur.GESTIONNAIRE_PAIE, db_path=db_path
    )
    lecture = utilisateur_service.creer_utilisateur(
        "Lecture", "Seule", "lecture", MDP, RoleUtilisateur.CONSULTATION, db_path=db_path
    )
    cible = utilisateur_service.creer_utilisateur(
        "Cible", "Compte", "cible", MDP, RoleUtilisateur.CONSULTATION, db_path=db_path
    )
    return {"db": db_path, "admin": admin, "gestion": gestion, "lecture": lecture, "cible": cible}


def _operations(c, tmp_path):
    """Chaque opération sensible, paramétrée par l'identifiant de l'acteur."""
    db = c["db"]
    return {
        "creer_compte": lambda a: administration_service.creer_compte(
            a, "Nouveau", "Compte", f"nouveau{a}", MDP, MDP, RoleUtilisateur.CONSULTATION, db_path=db
        ),
        "modifier_role": lambda a: administration_service.modifier_compte(
            a, c["cible"].id, "Cible", "Compte", RoleUtilisateur.GESTIONNAIRE_PAIE, db_path=db
        ),
        "desactiver_compte": lambda a: administration_service.desactiver_compte(a, c["cible"].id, db_path=db),
        "activer_compte": lambda a: administration_service.activer_compte(a, c["cible"].id, db_path=db),
        "reinitialiser_mot_de_passe": lambda a: administration_service.reinitialiser_mot_de_passe_compte(
            a, c["cible"].id, "Nouveau-Motdepasse-2", db_path=db
        ),
        "creer_sauvegarde": lambda a: administration_service.creer_sauvegarde(
            a, db_path=db, backup_dir=tmp_path / "sauvegardes"
        ),
        "enregistrer_parametres": lambda a: administration_service.enregistrer_parametres(
            a, parametres_service.ParametresEtablissement(nom_etablissement="Test"),
            chemin=tmp_path / "parametres.json", db_path=db,
        ),
        "diagnostiquer": lambda a: administration_service.diagnostiquer_systeme(a, db_path=db),
    }


NOMS_OPERATIONS = [
    "creer_compte", "modifier_role", "desactiver_compte", "activer_compte",
    "reinitialiser_mot_de_passe", "creer_sauvegarde", "enregistrer_parametres", "diagnostiquer",
]


@pytest.mark.parametrize("operation", NOMS_OPERATIONS)
@pytest.mark.parametrize("role", ["gestion", "lecture"])
def test_operation_sensible_refusee_aux_non_admin_en_appel_direct(comptes, tmp_path, operation, role):
    etat_avant = [(u.username, u.role, u.actif) for u in utilisateur_service.lister_utilisateurs(db_path=comptes["db"])]
    with pytest.raises(AutorisationRefuseeError):
        _operations(comptes, tmp_path)[operation](comptes[role].id)
    etat_apres = [(u.username, u.role, u.actif) for u in utilisateur_service.lister_utilisateurs(db_path=comptes["db"])]
    assert etat_apres == etat_avant


@pytest.mark.parametrize("operation", NOMS_OPERATIONS)
def test_operation_sensible_autorisee_a_admin(comptes, tmp_path, operation):
    _operations(comptes, tmp_path)[operation](comptes["admin"].id)


@pytest.mark.parametrize("acteur", [None, 424242])
@pytest.mark.parametrize("operation", NOMS_OPERATIONS)
def test_operation_refusee_sans_utilisateur_valide(comptes, tmp_path, operation, acteur):
    with pytest.raises(AutorisationRefuseeError):
        _operations(comptes, tmp_path)[operation](acteur)


def test_restauration_refusee_aux_non_admin(comptes, tmp_path):
    sauvegarde = administration_service.creer_sauvegarde(
        comptes["admin"].id, db_path=comptes["db"], backup_dir=tmp_path / "sauvegardes"
    )
    for role in ("gestion", "lecture"):
        with pytest.raises(AutorisationRefuseeError):
            administration_service.restaurer_sauvegarde(
                comptes[role].id, sauvegarde, confirmation=True, db_path=comptes["db"], backup_dir=tmp_path / "s"
            )
    rapport = administration_service.restaurer_sauvegarde(
        comptes["admin"].id, sauvegarde, confirmation=True, db_path=comptes["db"], backup_dir=tmp_path / "s"
    )
    assert rapport.reussie


def test_suppressions_definitives_refusees_aux_non_admin(comptes):
    db = comptes["db"]
    enseignant = enseignant_service.creer_enseignant(
        nom="Abena", prenom="Rose", sexe="F", statut="P", taux_horaire=1500, db_path=db
    )
    periode = periode_service.creer_periode(mois=1, annee=2031, db_path=db)
    for role in ("gestion", "lecture"):
        with pytest.raises(AutorisationRefuseeError):
            administration_service.supprimer_enseignant(comptes[role].id, enseignant.id, confirmation=True, db_path=db)
        with pytest.raises(AutorisationRefuseeError):
            administration_service.supprimer_periode(comptes[role].id, periode.id, confirmation=True, db_path=db)
    assert enseignant_service.obtenir_enseignant(enseignant.id, db_path=db)
    administration_service.supprimer_enseignant(comptes["admin"].id, enseignant.id, confirmation=True, db_path=db)
    administration_service.supprimer_periode(comptes["admin"].id, periode.id, confirmation=True, db_path=db)


def test_un_utilisateur_ne_peut_pas_changer_son_propre_role(comptes):
    for role in ("gestion", "lecture"):
        compte = comptes[role]
        with pytest.raises(AutorisationRefuseeError):
            administration_service.modifier_compte(
                compte.id, compte.id, compte.nom, compte.prenom, RoleUtilisateur.ADMIN, db_path=comptes["db"]
            )
        assert utilisateur_service.obtenir_utilisateur(compte.id, db_path=comptes["db"]).role == compte.role


def test_admin_ne_peut_pas_changer_son_propre_role_ni_se_desactiver(comptes):
    db = comptes["db"]
    admin = comptes["admin"]
    utilisateur_service.creer_utilisateur("Second", "Admin", "admin2", MDP, RoleUtilisateur.ADMIN, db_path=db)
    with pytest.raises(UtilisateurValidationError):
        administration_service.modifier_compte(admin.id, admin.id, admin.nom, admin.prenom, RoleUtilisateur.CONSULTATION, db_path=db)
    with pytest.raises(UtilisateurValidationError):
        administration_service.desactiver_compte(admin.id, admin.id, db_path=db)
    compte = utilisateur_service.obtenir_utilisateur(admin.id, db_path=db)
    assert compte.role == RoleUtilisateur.ADMIN and compte.actif
    # Modifier son propre nom reste possible.
    administration_service.modifier_compte(admin.id, admin.id, "Nouveau-nom", admin.prenom, RoleUtilisateur.ADMIN, db_path=db)


def test_admin_retrograde_perd_immediatement_ses_droits(comptes, tmp_path):
    db = comptes["db"]
    second = utilisateur_service.creer_utilisateur("Second", "Admin", "admin2", MDP, RoleUtilisateur.ADMIN, db_path=db)
    administration_service.modifier_compte(comptes["admin"].id, second.id, "Second", "Admin", RoleUtilisateur.CONSULTATION, db_path=db)
    with pytest.raises(AutorisationRefuseeError):
        administration_service.creer_sauvegarde(second.id, db_path=db, backup_dir=tmp_path / "s")


def test_admin_desactive_perd_immediatement_ses_droits(comptes, tmp_path):
    db = comptes["db"]
    second = utilisateur_service.creer_utilisateur("Second", "Admin", "admin2", MDP, RoleUtilisateur.ADMIN, db_path=db)
    administration_service.desactiver_compte(comptes["admin"].id, second.id, db_path=db)
    with pytest.raises(AutorisationRefuseeError):
        exiger_permission_utilisateur(second.id, permission_service.UTILISATEUR_GERER, db)


def test_operations_sur_les_comptes_journalisees_sans_secret(comptes):
    db = comptes["db"]
    a = comptes["admin"].id
    nouveau = administration_service.creer_compte(a, "Mbida", "Anne", "anne", MDP, MDP, RoleUtilisateur.CONSULTATION, db_path=db)
    administration_service.modifier_compte(a, nouveau.id, "Mbida", "Anne", RoleUtilisateur.GESTIONNAIRE_PAIE, db_path=db)
    administration_service.desactiver_compte(a, nouveau.id, db_path=db)
    administration_service.activer_compte(a, nouveau.id, db_path=db)
    administration_service.reinitialiser_mot_de_passe_compte(a, nouveau.id, "Autre-Motdepasse-3", db_path=db)
    administration_service.changer_mon_mot_de_passe(nouveau.id, "Autre-Motdepasse-3", "Encore-Autre-4", db_path=db)

    conn = sqlite3.connect(db)
    try:
        lignes = conn.execute("SELECT type_action, utilisateur, details FROM audit_log").fetchall()
        hashes = [r[0] for r in conn.execute("SELECT password_hash FROM utilisateurs")]
    finally:
        conn.close()
    types = {ligne[0] for ligne in lignes}
    for attendu in (
        TypeActionAudit.UTILISATEUR_CREE, TypeActionAudit.UTILISATEUR_MODIFIE, TypeActionAudit.ROLE_MODIFIE,
        TypeActionAudit.UTILISATEUR_DESACTIVE, TypeActionAudit.UTILISATEUR_ACTIVE,
        TypeActionAudit.MOT_DE_PASSE_REINITIALISE, TypeActionAudit.MOT_DE_PASSE_MODIFIE,
    ):
        assert attendu.value in types
    texte = " ".join(f"{l[1]} {l[2]}" for l in lignes)
    for secret in (MDP, "Autre-Motdepasse-3", "Encore-Autre-4", "scrypt$", *hashes):
        assert secret not in texte


def test_matrice_operations_reservees_a_admin():
    reservees = [
        permission_service.UTILISATEUR_GERER, permission_service.BACKUP_CREER, permission_service.BACKUP_RESTAURER,
        permission_service.PARAMETRE_MODIFIER, permission_service.ADMINISTRATION_CONSULTER,
        permission_service.AUDIT_CONSULTER, permission_service.DONNEES_REINITIALISER,
        permission_service.ENSEIGNANT_SUPPRIMER, permission_service.PERIODE_SUPPRIMER,
    ]
    for permission in reservees:
        assert permission_service.a_permission(RoleUtilisateur.ADMIN, permission)
        assert not permission_service.a_permission(RoleUtilisateur.GESTIONNAIRE_PAIE, permission)
        assert not permission_service.a_permission(RoleUtilisateur.CONSULTATION, permission)


# ---------------------------------------------------------------------
# Contrôle statique : l'interface ne contourne jamais la façade sécurisée
# ---------------------------------------------------------------------

FONCTIONS_BAS_NIVEAU_INTERDITES_DANS_LES_PAGES = {
    "creer_utilisateur", "modifier_utilisateur", "desactiver_utilisateur", "activer_utilisateur",
    "reinitialiser_mot_de_passe", "changer_mot_de_passe", "reinitialiser_tous_les_comptes",
    "restaurer_sauvegarde_brute", "enregistrer_parametres", "supprimer_enseignant_definitivement",
    "supprimer_periode_definitivement", "enregistrer_identite",
}


def _appels(fichier: Path):
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            fonction = noeud.func
            if isinstance(fonction, ast.Attribute):
                module = fonction.value.id if isinstance(fonction.value, ast.Name) else None
                yield module, fonction.attr
            elif isinstance(fonction, ast.Name):
                yield None, fonction.id


@pytest.mark.parametrize("page", sorted((RACINE / "ui_pages").glob("*.py")), ids=lambda p: p.name)
def test_pages_n_appellent_pas_les_fonctions_sensibles_de_bas_niveau(page):
    for module, nom in _appels(page):
        if module == "administration_service":
            continue
        assert nom not in FONCTIONS_BAS_NIVEAU_INTERDITES_DANS_LES_PAGES, (
            f"{page.name} appelle {module}.{nom} directement : passer par administration_service."
        )
        if module == "backup_service":
            assert nom not in {"creer_sauvegarde", "restaurer_sauvegarde"}, (
                f"{page.name} appelle backup_service.{nom} directement."
            )


@pytest.mark.parametrize("page", sorted((RACINE / "ui_pages").glob("*.py")), ids=lambda p: p.name)
def test_chaque_page_exige_une_permission(page):
    appels = {nom for _module, nom in _appels(page)}
    assert "exiger_permission" in appels, f"{page.name} n'appelle pas exiger_permission()"


def test_aucune_page_n_expose_la_reinitialisation_des_comptes():
    for page in (RACINE / "ui_pages").glob("*.py"):
        assert "reinitialiser_tous_les_comptes" not in page.read_text(encoding="utf-8")


# Fonctions de modification des enseignants appelées depuis la page
# Enseignants : chaque appel doit se trouver sous un test de permission
# (sinon un compte CONSULTATION peut, par exemple, désactiver un enseignant).
MODIFICATIONS_ENSEIGNANT = {
    "modifier_enseignant", "changer_statut_enseignant", "desactiver_enseignant", "reactiver_enseignant",
}


def _appels_non_proteges(fichier: Path, fonctions: set) -> list:
    source = fichier.read_text(encoding="utf-8")
    arbre = ast.parse(source)
    parents = {enfant: noeud for noeud in ast.walk(arbre) for enfant in ast.iter_child_nodes(noeud)}
    fautifs = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        nom = noeud.func.attr if isinstance(noeud.func, ast.Attribute) else getattr(noeud.func, "id", None)
        if nom not in fonctions:
            continue
        courant, protege = noeud, False
        while courant in parents:
            courant = parents[courant]
            if isinstance(courant, ast.If):
                condition = ast.get_source_segment(source, courant.test) or ""
                if "peut_" in condition or "a_permission" in condition:
                    protege = True
                    break
        if not protege:
            fautifs.append(f"{fichier.name}:{noeud.lineno} {nom}()")
    return fautifs


def test_modifications_d_enseignant_protegees_par_une_permission_dans_la_page():
    page = RACINE / "ui_pages" / "1_Enseignants.py"
    assert _appels_non_proteges(page, MODIFICATIONS_ENSEIGNANT) == []
