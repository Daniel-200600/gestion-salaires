"""
Opérations d'administration sensibles, avec contrôle d'autorisation
côté service.

La page Administration (et les actions de suppression définitive des
pages Enseignants et Périodes) appellent exclusivement ces fonctions,
jamais directement les services de bas niveau. Chaque fonction :

1. relit en base l'utilisateur qui agit (`acteur_id`) et vérifie la
   permission requise dans la matrice centrale
   (services/permission_service.py) — un rôle affiché en session ou un
   bouton masqué ne suffisent jamais ;
2. délègue au service existant, dont les règles métier restent
   inchangées (dernier administrateur protégé, politique de mot de
   passe, confirmation des suppressions...) ;
3. journalise les opérations sur les comptes dans le journal d'audit,
   sans jamais y écrire de mot de passe ni d'empreinte de mot de passe.

Les services de bas niveau restent utilisables par le code interne et
par les tests ; l'interface, elle, ne les appelle plus directement pour
ces opérations (vérifié par tests/test_separation_privileges.py).
"""

import logging
from pathlib import Path
from typing import Optional, Union

from database.repositories import audit_log_repository
from models.audit_log import AuditLog
from models.enums import RoleUtilisateur, TypeActionAudit
from models.utilisateur import Utilisateur
from services import (
    backup_service,
    diagnostic_service,
    enseignant_service,
    identite_etablissement_service,
    modele_bulletin_service,
    parametres_paie_service,
    parametres_service,
    periode_service,
    permission_service,
    utilisateur_service,
)
from services.autorisation_service import AutorisationRefuseeError, exiger_permission_utilisateur
from services.utilisateur_service import UtilisateurValidationError

logger = logging.getLogger("salaires_app.administration_service")

DbPath = Optional[Union[str, Path]]

LIBELLES_ROLES = {
    RoleUtilisateur.ADMIN: "Administrateur",
    RoleUtilisateur.GESTIONNAIRE_PAIE: "Gestionnaire de paie",
    RoleUtilisateur.CONSULTATION: "Consultation",
}


def _journaliser_compte(
    type_action: TypeActionAudit, acteur: Utilisateur, cible_id: Optional[int], details: str, db_path: DbPath
) -> None:
    try:
        audit_log_repository.enregistrer(
            AuditLog(
                type_action=type_action, entite="utilisateur", entite_id=cible_id,
                utilisateur=acteur.username, details=details,
            ),
            db_path=db_path,
        )
    except Exception as erreur:  # noqa: BLE001 — l'audit ne doit jamais annuler une opération déjà effectuée
        logger.error("Audit de gestion des comptes non enregistré : %s", erreur)


# ---------------------------------------------------------------------
# Comptes utilisateurs
# ---------------------------------------------------------------------

def creer_compte(
    acteur_id: Optional[int],
    nom: str,
    prenom: str,
    username: str,
    mot_de_passe: str,
    confirmation_mot_de_passe: Optional[str],
    role: RoleUtilisateur,
    actif: bool = True,
    db_path: DbPath = None,
) -> Utilisateur:
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.UTILISATEUR_GERER, db_path)
    compte = utilisateur_service.creer_utilisateur(
        nom=nom, prenom=prenom, username=username, mot_de_passe=mot_de_passe,
        confirmation_mot_de_passe=confirmation_mot_de_passe, role=role, actif=actif, db_path=db_path,
    )
    _journaliser_compte(
        TypeActionAudit.UTILISATEUR_CREE, acteur, compte.id,
        f"Compte créé : {compte.username} — rôle {LIBELLES_ROLES[compte.role]} — "
        f"{'actif' if compte.actif else 'inactif'}",
        db_path,
    )
    return compte


def modifier_compte(
    acteur_id: Optional[int],
    utilisateur_id: int,
    nom: str,
    prenom: str,
    role: RoleUtilisateur,
    db_path: DbPath = None,
) -> Utilisateur:
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.UTILISATEUR_GERER, db_path)
    avant = utilisateur_service.obtenir_utilisateur(utilisateur_id, db_path=db_path)
    if avant.id == acteur.id and role != avant.role:
        raise UtilisateurValidationError(
            "Vous ne pouvez pas modifier votre propre rôle. Cette opération doit être effectuée "
            "par un autre administrateur."
        )
    apres = utilisateur_service.modifier_utilisateur(utilisateur_id, nom=nom, prenom=prenom, role=role, db_path=db_path)
    _journaliser_compte(
        TypeActionAudit.UTILISATEUR_MODIFIE, acteur, utilisateur_id,
        f"Compte modifié : {apres.username} (nom et prénom)", db_path,
    )
    if avant.role != apres.role:
        _journaliser_compte(
            TypeActionAudit.ROLE_MODIFIE, acteur, utilisateur_id,
            f"Rôle de {apres.username} : {LIBELLES_ROLES[avant.role]} → {LIBELLES_ROLES[apres.role]}", db_path,
        )
    return apres


def desactiver_compte(acteur_id: Optional[int], utilisateur_id: int, db_path: DbPath = None) -> Utilisateur:
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.UTILISATEUR_GERER, db_path)
    if utilisateur_id == acteur.id:
        raise UtilisateurValidationError(
            "Vous ne pouvez pas désactiver votre propre compte. Cette opération doit être effectuée "
            "par un autre administrateur."
        )
    compte = utilisateur_service.desactiver_utilisateur(utilisateur_id, db_path=db_path)
    _journaliser_compte(
        TypeActionAudit.UTILISATEUR_DESACTIVE, acteur, utilisateur_id, f"Compte désactivé : {compte.username}", db_path
    )
    return compte


def activer_compte(acteur_id: Optional[int], utilisateur_id: int, db_path: DbPath = None) -> Utilisateur:
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.UTILISATEUR_GERER, db_path)
    compte = utilisateur_service.activer_utilisateur(utilisateur_id, db_path=db_path)
    _journaliser_compte(
        TypeActionAudit.UTILISATEUR_ACTIVE, acteur, utilisateur_id, f"Compte réactivé : {compte.username}", db_path
    )
    return compte


def reinitialiser_mot_de_passe_compte(
    acteur_id: Optional[int], utilisateur_id: int, nouveau_mot_de_passe: str, db_path: DbPath = None
) -> None:
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.UTILISATEUR_GERER, db_path)
    compte = utilisateur_service.obtenir_utilisateur(utilisateur_id, db_path=db_path)
    utilisateur_service.reinitialiser_mot_de_passe(utilisateur_id, nouveau_mot_de_passe, db_path=db_path)
    _journaliser_compte(
        TypeActionAudit.MOT_DE_PASSE_REINITIALISE, acteur, utilisateur_id,
        f"Mot de passe réinitialisé par un administrateur pour : {compte.username}", db_path,
    )


def changer_mon_mot_de_passe(
    acteur_id: Optional[int], mot_de_passe_actuel: str, nouveau_mot_de_passe: str, db_path: DbPath = None
) -> None:
    """Changement de SON PROPRE mot de passe : l'ancien mot de passe est toujours exigé."""
    if acteur_id is None:
        raise AutorisationRefuseeError("Opération refusée : aucun utilisateur authentifié.")
    from services import auth_service

    acteur = auth_service.revalider_session(acteur_id, db_path=db_path)
    if acteur is None:
        raise AutorisationRefuseeError("Opération refusée : compte introuvable ou désactivé.")
    utilisateur_service.changer_mot_de_passe(acteur.id, mot_de_passe_actuel, nouveau_mot_de_passe, db_path=db_path)
    _journaliser_compte(
        TypeActionAudit.MOT_DE_PASSE_MODIFIE, acteur, acteur.id,
        f"Mot de passe modifié par l'utilisateur : {acteur.username}", db_path,
    )


# ---------------------------------------------------------------------
# Sauvegarde, restauration, paramètres, diagnostic
# ---------------------------------------------------------------------

def creer_sauvegarde(acteur_id: Optional[int], db_path: DbPath = None, backup_dir: Optional[Path] = None) -> Path:
    exiger_permission_utilisateur(acteur_id, permission_service.BACKUP_CREER, db_path)
    return backup_service.creer_sauvegarde(
        db_path=Path(db_path) if db_path is not None else None, backup_dir=backup_dir
    )


def restaurer_sauvegarde(
    acteur_id: Optional[int],
    chemin_sauvegarde: Path,
    confirmation: bool = False,
    db_path: DbPath = None,
    backup_dir: Optional[Path] = None,
) -> backup_service.RapportRestauration:
    exiger_permission_utilisateur(acteur_id, permission_service.BACKUP_RESTAURER, db_path)
    return backup_service.restaurer_sauvegarde(
        chemin_sauvegarde, confirmation=confirmation,
        db_path=Path(db_path) if db_path is not None else None, backup_dir=backup_dir,
    )


def enregistrer_parametres(
    acteur_id: Optional[int],
    parametres: parametres_service.ParametresEtablissement,
    chemin: Optional[Path] = None,
    db_path: DbPath = None,
) -> None:
    exiger_permission_utilisateur(acteur_id, permission_service.PARAMETRE_MODIFIER, db_path)
    parametres_service.enregistrer_parametres(parametres, chemin=chemin)


def diagnostiquer_systeme(acteur_id: Optional[int], db_path: DbPath = None) -> diagnostic_service.DiagnosticSysteme:
    exiger_permission_utilisateur(acteur_id, permission_service.ADMINISTRATION_CONSULTER, db_path)
    return diagnostic_service.diagnostiquer_systeme(db_path=Path(db_path) if db_path is not None else None)


# ---------------------------------------------------------------------
# Suppressions définitives unitaires (ADMIN uniquement)
# ---------------------------------------------------------------------

def supprimer_enseignant(
    acteur_id: Optional[int], enseignant_id: int, confirmation: bool = False, db_path: DbPath = None
):
    exiger_permission_utilisateur(acteur_id, permission_service.ENSEIGNANT_SUPPRIMER, db_path)
    return enseignant_service.supprimer_enseignant_definitivement(
        enseignant_id, confirmation=confirmation, db_path=db_path
    )


def supprimer_periode(acteur_id: Optional[int], periode_id: int, confirmation: bool = False, db_path: DbPath = None):
    exiger_permission_utilisateur(acteur_id, permission_service.PERIODE_SUPPRIMER, db_path)
    return periode_service.supprimer_periode_definitivement(periode_id, confirmation=confirmation, db_path=db_path)


# ---------------------------------------------------------------------
# Paramètres de paie (taux de taxe) — ADMIN uniquement
# ---------------------------------------------------------------------

def definir_identite_etablissement(
    acteur_id: Optional[int],
    entete_fr, entete_en, lieu_signature: str, titre_signataire_fr: str, titre_signataire_en: str,
    logo: Optional[bytes] = None, retirer_logo: bool = False, db_path: DbPath = None,
):
    """En-tête, logo et signature du bulletin ; produit les modèles de l'établissement."""
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.PARAMETRE_MODIFIER, db_path)
    return identite_etablissement_service.enregistrer_identite(
        entete_fr, entete_en, lieu_signature, titre_signataire_fr, titre_signataire_en,
        logo=logo, retirer_logo=retirer_logo, utilisateur=acteur.username, db_path=db_path,
    )


def revenir_a_l_entete_neutre(acteur_id: Optional[int], db_path: DbPath = None) -> None:
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.PARAMETRE_MODIFIER, db_path)
    identite_etablissement_service.revenir_a_l_entete_neutre(utilisateur=acteur.username, db_path=db_path)


def definir_taux_taxe_defaut(acteur_id: Optional[int], pourcentage, db_path: DbPath = None):
    """Taux appliqué aux périodes créées ensuite. Aucune période existante n'est modifiée."""
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.PARAMETRES_PAIE_GERER, db_path)
    return parametres_paie_service.definir_taux_taxe_defaut(pourcentage, utilisateur=acteur.username, db_path=db_path)


def definir_taux_taxe_periode(acteur_id: Optional[int], periode_id: int, pourcentage, db_path: DbPath = None):
    """Taux d'une période en brouillon ou ouverte (refusé si validée ou clôturée)."""
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.PARAMETRES_PAIE_GERER, db_path)
    return parametres_paie_service.definir_taux_taxe_periode(
        periode_id, pourcentage, utilisateur=acteur.username, db_path=db_path
    )


# ---------------------------------------------------------------------
# Modèles de bulletin — ADMIN uniquement
# ---------------------------------------------------------------------

def analyser_modele_bulletin(acteur_id: Optional[int], contenu: bytes, nom_fichier: str, db_path: DbPath = None):
    exiger_permission_utilisateur(acteur_id, permission_service.MODELE_BULLETIN_GERER, db_path)
    return modele_bulletin_service.analyser_modele(contenu, nom_fichier)


def importer_modele_bulletin(
    acteur_id: Optional[int], nom: str, contenu: bytes, nom_fichier: str,
    correspondances=None, alignements=None, activer: bool = False, db_path: DbPath = None,
):
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.MODELE_BULLETIN_GERER, db_path)
    return modele_bulletin_service.importer_modele(
        nom, contenu, nom_fichier, correspondances=correspondances, alignements=alignements,
        utilisateur=acteur.username, activer=activer, db_path=db_path,
    )


def activer_modele_bulletin(acteur_id: Optional[int], cle: str, db_path: DbPath = None):
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.MODELE_BULLETIN_GERER, db_path)
    return modele_bulletin_service.activer_modele(cle, utilisateur=acteur.username, db_path=db_path)


def supprimer_modele_bulletin(acteur_id: Optional[int], cle: str, db_path: DbPath = None) -> None:
    acteur = exiger_permission_utilisateur(acteur_id, permission_service.MODELE_BULLETIN_GERER, db_path)
    modele_bulletin_service.supprimer_modele(cle, utilisateur=acteur.username, db_path=db_path)
