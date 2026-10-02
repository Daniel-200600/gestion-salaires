"""
Service de permissions (module 11).

Matrice centralisée des permissions par rôle (section 10/11). Aucune
page ne doit contenir de condition `if role == "ADMIN"` dispersée :
toute vérification passe par `a_permission()`.

Ce module est indépendant de Streamlit et entièrement testable en
isolation.
"""

from typing import Dict, Set

from models.enums import RoleUtilisateur

# ---------------------------------------------------------------------
# Permissions élémentaires (section 10)
# ---------------------------------------------------------------------
ENSEIGNANT_CONSULTER = "enseignant.consulter"
ENSEIGNANT_MODIFIER = "enseignant.modifier"
ENSEIGNANT_SUPPRIMER = "enseignant.supprimer"
PERIODE_CONSULTER = "periode.consulter"
PERIODE_GERER = "periode.gerer"  # création, ouverture, modification
PERIODE_SUPPRIMER = "periode.supprimer"
PAIE_CONSULTER = "paie.consulter"
PAIE_MODIFIER = "paie.modifier"
PAIE_CONTROLER = "paie.controler"
PAIE_VALIDER = "paie.valider"
PAIE_CLOTURER = "paie.cloturer"
BULLETIN_GENERER = "bulletin.generer"
BULLETIN_CONSULTER = "bulletin.consulter"
EXPORT_GENERER = "export.generer"
HISTORIQUE_CONSULTER = "historique.consulter"
ADMINISTRATION_CONSULTER = "administration.consulter"
UTILISATEUR_GERER = "utilisateur.gerer"
BACKUP_CREER = "backup.creer"
BACKUP_RESTAURER = "backup.restaurer"
PARAMETRE_MODIFIER = "parametre.modifier"
AUDIT_CONSULTER = "audit.consulter"
REPORTING_CONSULTER = "reporting.consulter"
REPORTING_EXPORTER = "reporting.exporter"
DOCUMENT_CONSULTER = "document.consulter"
DOCUMENT_ARCHIVER = "document.archiver"
DOCUMENT_EXPORTER = "document.exporter"
IMPORT_DONNEES = "import.donnees"
ALERTE_CONSULTER = "alerte.consulter"
ALERTE_GERER = "alerte.gerer"
STATISTIQUES_CONSULTER = "statistiques.consulter"
STATISTIQUES_EXPORTER = "statistiques.exporter"
AUTOMATISATION_EXECUTER = "automatisation.executer"
# Réinitialisation complète des données MÉTIER (enseignants, périodes,
# paie, bulletins, documents, imports, alertes). Ne concerne jamais les
# comptes utilisateurs : voir services/reinitialisation_service.py.
DONNEES_REINITIALISER = "donnees.reinitialiser"
# Consultation de la documentation intégrée (guide utilisateur,
# politique de confidentialité, conditions d'utilisation) : ouverte à
# tout utilisateur authentifié, quel que soit son rôle.
DOCUMENTATION_CONSULTER = "documentation.consulter"
PARAMETRES_PAIE_GERER = "parametres_paie.gerer"
MODELE_BULLETIN_GERER = "modele_bulletin.gerer"

# ---------------------------------------------------------------------
# Matrice des permissions (section 11) — source de vérité unique.
# ---------------------------------------------------------------------
_MATRICE: Dict[str, Set[RoleUtilisateur]] = {
    ENSEIGNANT_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    ENSEIGNANT_MODIFIER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    ENSEIGNANT_SUPPRIMER: {RoleUtilisateur.ADMIN},

    PERIODE_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    PERIODE_GERER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    PERIODE_SUPPRIMER: {RoleUtilisateur.ADMIN},

    PAIE_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    PAIE_MODIFIER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    PAIE_CONTROLER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    PAIE_VALIDER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    # Clôture : la matrice fournie laisse le choix ("Oui ou selon règle
    # existante") ; la règle métier la plus restrictive est conservée
    # (opération irréversible -> réservée à l'ADMIN), conformément à la
    # consigne explicite en cas d'ambiguïté (section 11).
    PAIE_CLOTURER: {RoleUtilisateur.ADMIN},

    BULLETIN_GENERER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    BULLETIN_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},

    EXPORT_GENERER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},

    HISTORIQUE_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},

    ADMINISTRATION_CONSULTER: {RoleUtilisateur.ADMIN},
    UTILISATEUR_GERER: {RoleUtilisateur.ADMIN},
    BACKUP_CREER: {RoleUtilisateur.ADMIN},
    BACKUP_RESTAURER: {RoleUtilisateur.ADMIN},
    PARAMETRE_MODIFIER: {RoleUtilisateur.ADMIN},
    AUDIT_CONSULTER: {RoleUtilisateur.ADMIN},
    REPORTING_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    REPORTING_EXPORTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    DOCUMENT_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    DOCUMENT_ARCHIVER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    DOCUMENT_EXPORTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    IMPORT_DONNEES: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    ALERTE_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    ALERTE_GERER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    STATISTIQUES_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    STATISTIQUES_EXPORTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    AUTOMATISATION_EXECUTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE},
    # Opération destructive globale : strictement réservée à l'ADMIN.
    DONNEES_REINITIALISER: {RoleUtilisateur.ADMIN},
    DOCUMENTATION_CONSULTER: {RoleUtilisateur.ADMIN, RoleUtilisateur.GESTIONNAIRE_PAIE, RoleUtilisateur.CONSULTATION},
    PARAMETRES_PAIE_GERER: {RoleUtilisateur.ADMIN},
    MODELE_BULLETIN_GERER: {RoleUtilisateur.ADMIN},
}


# Libellés lisibles, utilisés pour afficher la matrice réellement
# appliquée (page Guide administrateur). Chaque permission de la
# matrice doit en avoir un (vérifié par les tests).
LIBELLES_PERMISSIONS: Dict[str, str] = {
    ENSEIGNANT_CONSULTER: "Consulter les enseignants",
    ENSEIGNANT_MODIFIER: "Créer et modifier les enseignants",
    ENSEIGNANT_SUPPRIMER: "Supprimer définitivement un enseignant",
    PERIODE_CONSULTER: "Consulter les périodes de paie",
    PERIODE_GERER: "Créer, corriger et ouvrir les périodes",
    PERIODE_SUPPRIMER: "Supprimer définitivement une période",
    PAIE_CONSULTER: "Consulter la paie et le tableau de bord",
    PAIE_MODIFIER: "Saisir les données de paie",
    PAIE_CONTROLER: "Consulter le contrôle de la paie",
    PAIE_VALIDER: "Valider une période",
    PAIE_CLOTURER: "Clôturer une période",
    BULLETIN_GENERER: "Générer les bulletins",
    BULLETIN_CONSULTER: "Consulter les bulletins",
    EXPORT_GENERER: "Générer les états comptables",
    HISTORIQUE_CONSULTER: "Consulter l'historique de paie",
    ADMINISTRATION_CONSULTER: "Accéder à l'administration et au diagnostic",
    UTILISATEUR_GERER: "Gérer les comptes et les rôles",
    BACKUP_CREER: "Créer une sauvegarde",
    BACKUP_RESTAURER: "Restaurer une sauvegarde",
    PARAMETRE_MODIFIER: "Modifier les paramètres de l'établissement",
    AUDIT_CONSULTER: "Consulter les journaux",
    REPORTING_CONSULTER: "Consulter les rapports comptables",
    REPORTING_EXPORTER: "Exporter les rapports comptables",
    DOCUMENT_CONSULTER: "Consulter les documents",
    DOCUMENT_ARCHIVER: "Archiver les documents",
    DOCUMENT_EXPORTER: "Télécharger et exporter les documents",
    IMPORT_DONNEES: "Importer des données",
    ALERTE_CONSULTER: "Consulter les notifications",
    ALERTE_GERER: "Traiter les notifications",
    STATISTIQUES_CONSULTER: "Consulter les statistiques",
    STATISTIQUES_EXPORTER: "Exporter les statistiques",
    AUTOMATISATION_EXECUTER: "Lancer les traitements automatisés",
    DONNEES_REINITIALISER: "Réinitialiser les données métier",
    DOCUMENTATION_CONSULTER: "Consulter la documentation intégrée",
    PARAMETRES_PAIE_GERER: "Modifier le taux de taxe (par défaut et par période)",
    MODELE_BULLETIN_GERER: "Importer, activer et supprimer les modèles de bulletin",
}


def matrice_lisible() -> list:
    """Matrice des permissions sous forme de lignes lisibles (Oui/Non par rôle), dans l'ordre de définition."""
    lignes = []
    for permission, roles in _MATRICE.items():
        lignes.append({
            "Permission": LIBELLES_PERMISSIONS.get(permission, permission),
            "Identifiant": permission,
            "Administrateur": "Oui" if RoleUtilisateur.ADMIN in roles else "Non",
            "Gestionnaire de paie": "Oui" if RoleUtilisateur.GESTIONNAIRE_PAIE in roles else "Non",
            "Consultation": "Oui" if RoleUtilisateur.CONSULTATION in roles else "Non",
        })
    return lignes


def a_permission(role: RoleUtilisateur, permission: str) -> bool:
    """
    Vrai si le rôle donné possède la permission demandée. Une
    permission inconnue (faute de frappe, permission pas encore
    définie) est toujours refusée par défaut — jamais d'accès
    accordé par erreur de configuration.
    """
    return role in _MATRICE.get(permission, set())


def permissions_du_role(role: RoleUtilisateur) -> Set[str]:
    """Liste toutes les permissions accordées à un rôle (utile pour l'affichage en Administration)."""
    return {permission for permission, roles in _MATRICE.items() if role in roles}
