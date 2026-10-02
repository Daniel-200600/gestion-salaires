"""
Enumérations utilisées par les modèles.

Ces valeurs doivent rester synchronisées avec les contraintes CHECK
définies dans database/schema.sql. En cas de modification, mettre à
jour les deux en même temps.
"""

from enum import Enum


class Sexe(str, Enum):
    HOMME = "M"
    FEMME = "F"


class StatutEnseignant(str, Enum):
    VACATAIRE = "V"
    PERMANENT = "P"


class StatutPeriode(str, Enum):
    BROUILLON = "brouillon"
    OUVERTE = "ouverte"
    VALIDEE = "validee"
    CLOTUREE = "cloturee"


class TypeElementRemuneration(str, Enum):
    PRIME_AP_PP = "prime_ap_pp"
    SURVEILLANCE_SECRETARIAT = "surveillance_secretariat"
    INDEMNITE_SUGGESTION_ADMIN = "indemnite_suggestion_admin"


class TypeRetenue(str, Enum):
    RETENUE_AMICALE = "retenue_amicale"
    DETTE = "dette"


class TypeActionAudit(str, Enum):
    CREATION = "creation"
    MODIFICATION = "modification"
    CLOTURE_PERIODE = "cloture_periode"
    VALIDATION_PERIODE = "validation_periode"
    CALCUL_PAIE = "calcul_paie"
    GENERATION_BULLETIN = "generation_bulletin"
    EXPORT_COMPTABLE = "export_comptable"
    RESTAURATION_SAUVEGARDE = "restauration_sauvegarde"
    SUPPRESSION_DEFINITIVE = "suppression_definitive"
    CONNEXION_REUSSIE = "connexion_reussie"
    CONNEXION_ECHOUEE = "connexion_echouee"
    DECONNEXION = "deconnexion"
    UTILISATEUR_CREE = "utilisateur_cree"
    UTILISATEUR_MODIFIE = "utilisateur_modifie"
    UTILISATEUR_DESACTIVE = "utilisateur_desactive"
    UTILISATEUR_ACTIVE = "utilisateur_active"
    MOT_DE_PASSE_MODIFIE = "mot_de_passe_modifie"
    MOT_DE_PASSE_REINITIALISE = "mot_de_passe_reinitialise"
    ROLE_MODIFIE = "role_modifie"
    PERIODE_OUVERTE = "periode_ouverte"
    VALIDATION_REFUSEE = "validation_refusee"
    CLOTURE_REFUSEE = "cloture_refusee"
    REPORTING_EXPORTE = "reporting_exporte"
    RAPPROCHEMENT_EXECUTE = "rapprochement_execute"
    DOCUMENT_ARCHIVE = "document_archive"
    DOCUMENT_INTEGRITE_VERIFIEE = "document_integrite_verifiee"
    DOCUMENT_SUPPRIME = "document_supprime"
    DOCUMENT_TELECHARGE = "document_telecharge"
    ARCHIVE_CREEE = "archive_creee"
    ARCHIVE_RESTAUREE = "archive_restauree"
    IMPORT_DONNEES = "import_donnees"
    IMPORT_DONNEES_ECHEC = "import_donnees_echec"
    IMPORT_DONNEES_SIMULATION = "import_donnees_simulation"
    ALERTE_CREEE = "alerte_creee"
    ALERTE_ACQUITTEE = "alerte_acquittee"
    ALERTE_RESOLUE = "alerte_resolue"
    ALERTE_IGNOREE = "alerte_ignoree"
    AUTOMATISATION_PREPAREE = "automatisation_preparee"
    AUTOMATISATION_EXECUTEE = "automatisation_executee"
    AUTOMATISATION_ECHEC = "automatisation_echec"
    GENERATION_MASSIVE_BULLETINS = "generation_massive_bulletins"
    EXPORT_MASSIF = "export_massif"
    ARCHIVE_MASSIVE = "archive_massive"
    REINITIALISATION_DONNEES = "reinitialisation_donnees"
    REINITIALISATION_DONNEES_ECHEC = "reinitialisation_donnees_echec"
    PARAMETRE_PAIE_MODIFIE = "parametre_paie_modifie"
    MODELE_BULLETIN_IMPORTE = "modele_bulletin_importe"
    MODELE_BULLETIN_ACTIVE = "modele_bulletin_active"
    MODELE_BULLETIN_SUPPRIME = "modele_bulletin_supprime"
    STATUT_ENSEIGNANT_MODIFIE = "statut_enseignant_modifie"


class RoleUtilisateur(str, Enum):
    """Les trois rôles du module 11 (section 9)."""

    ADMIN = "admin"
    GESTIONNAIRE_PAIE = "gestionnaire_paie"
    CONSULTATION = "consultation"


class TypeDocument(str, Enum):
    """Types de documents référencés dans le registre documentaire (module 14, section 7)."""

    BULLETIN = "bulletin"
    RAPPORT_PAIE = "rapport_paie"
    ETAT_PAIE = "etat_paie"
    EXPORT_EXCEL = "export_excel"


class StatutDocument(str, Enum):
    """État d'un document au regard du registre et du disque (module 14, section 14)."""

    VALIDE = "valide"
    MANQUANT = "manquant"
    MODIFIE = "modifie"
    ORPHELIN = "orphelin"


class TypeImport(str, Enum):
    """Types d'importation massive pris en charge (module 15, section 8)."""

    ENSEIGNANTS = "enseignants"
    HEURES = "heures"
    REMUNERATIONS = "remunerations"
    RETENUES = "retenues"


class NiveauAnomalie(str, Enum):
    """Sévérité d'une anomalie détectée lors d'un import (module 15, section 27)."""

    ERREUR = "erreur"
    AVERTISSEMENT = "avertissement"
    INFO = "info"


class StatutImport(str, Enum):
    """État d'une opération d'import enregistrée (module 15)."""

    SIMULATION = "simulation"
    TERMINE = "termine"
    ECHEC = "echec"
    ANNULE = "annule"


class StrategieDoublon(str, Enum):
    """Stratégie appliquée face à un doublon détecté (module 15, section 14)."""

    REFUSER = "refuser"
    IGNORER = "ignorer"
    METTRE_A_JOUR = "mettre_a_jour"


class StatutOperationAutomatisation(str, Enum):
    """État d'une opération d'automatisation massive (module 18, section 15)."""

    PREPAREE = "preparee"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"
    TERMINEE_AVEC_ERREURS = "terminee_avec_erreurs"
    ECHEC = "echec"
    ANNULEE = "annulee"


class TypeOperationAutomatisation(str, Enum):
    """Type d'opération massive orchestrée (module 18)."""

    BULLETINS_MASSIFS = "bulletins_massifs"
    EXPORTS_MASSIFS = "exports_massifs"
    PACK_PAIE = "pack_paie"
    ARCHIVE_MASSIVE = "archive_massive"
    VERIFICATION_INTEGRITE = "verification_integrite"


class NiveauAlerte(str, Enum):
    """Niveau d'importance d'une alerte (module 16, section 3)."""

    INFO = "info"
    AVERTISSEMENT = "avertissement"
    ERREUR = "erreur"
    CRITIQUE = "critique"


class StatutAlerte(str, Enum):
    """État d'une alerte dans son cycle de vie (module 16, section 12)."""

    NOUVELLE = "nouvelle"
    LUE = "lue"
    ACQUITTEE = "acquittee"
    RESOLUE = "resolue"
    IGNOREE = "ignoree"
