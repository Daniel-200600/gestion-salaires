-- =====================================================================
-- SCHEMA SQLite - Application de gestion des salaires des enseignants
-- =====================================================================
-- Ce fichier est la source de vérité unique du schéma. Toute évolution
-- future doit passer par une migration dans database/migrations/,
-- jamais par une modification manuelle de la base en production.
--
-- STRATEGIE MONTANTS MONETAIRES (FCFA)
-- -------------------------------------------------------------------
-- Le FCFA n'a pas de sous-unité utilisée en pratique : tous les
-- montants sont stockés en INTEGER (FCFA entiers), jamais en REAL,
-- afin d'éliminer tout risque d'imprécision flottante sur des données
-- de paie. Une contrainte CHECK (valeur = CAST(valeur AS INTEGER))
-- interdit techniquement l'insertion d'un montant fractionnaire.
-- Les calculs métier (futur paie_service.py) utiliseront le type
-- Decimal en Python, avec arrondi explicite à l'entier avant écriture.
-- Les heures (durées, pas de l'argent) restent en REAL.
--
-- CYCLE DE VIE D'UNE PERIODE : BROUILLON -> OUVERTE -> VALIDEE -> CLOTUREE
-- -------------------------------------------------------------------
-- - BROUILLON : periode fraichement creee, mois/annee/libelle modifiables.
--   Aucune saisie de paie (heures, primes, retenues) n'est encore possible.
-- - OUVERTE   : fenetre de saisie. Les heures, primes/indemnites et
--   retenues peuvent etre ajoutees, modifiees, supprimees. Aucun
--   bulletin ne peut encore exister.
-- - VALIDEE   : les donnees sources (heures, primes, retenues) sont
--   gelees (triggers). Les bulletins peuvent etre generes (INSERT
--   uniquement) pour cette periode.
-- - CLOTUREE  : la periode elle-meme devient figee (plus aucune
--   modification, y compris de statut). date_cloture est renseignee
--   automatiquement a cette transition (contrainte CHECK dediee).
-- Un bulletin, une fois inséré dans bulletins_paie, est immuable en
-- toutes circonstances (UPDATE et DELETE bloqués sans condition).
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Table : enseignants
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enseignants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nom                 TEXT    NOT NULL,
    prenom              TEXT    NOT NULL DEFAULT '',
    -- Sexe, statut et taux horaire peuvent rester vides : fiche importée
    -- depuis une liste existante, à compléter plus tard (page Enseignants).
    -- Une fiche sans statut ou sans taux horaire n'entre dans aucun calcul
    -- de paie (voir Enseignant.est_complet).
    sexe                TEXT    NULL CHECK (sexe IS NULL OR sexe IN ('M', 'F')),
    statut              TEXT    NULL CHECK (statut IS NULL OR statut IN ('V', 'P')),
    taux_horaire        INTEGER NULL
                            CHECK (taux_horaire IS NULL OR taux_horaire >= 0)
                            CHECK (taux_horaire IS NULL OR taux_horaire = CAST(taux_horaire AS INTEGER)),
    -- Salaire mensuel fixe d'un permanent (FCFA) : il remplace heures × taux
    -- horaire dans le calcul ; les heures restent saisies à titre d'information.
    salaire_fixe        INTEGER NULL
                            CHECK (salaire_fixe IS NULL OR salaire_fixe >= 0)
                            CHECK (salaire_fixe IS NULL OR salaire_fixe = CAST(salaire_fixe AS INTEGER)),
    email               TEXT    NULL,
    telephone           TEXT    NULL,
    adresse             TEXT    NULL,
    actif               INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    date_creation       TEXT    NOT NULL DEFAULT (datetime('now')),
    date_modification   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Met à jour automatiquement date_modification à chaque UPDATE
CREATE TRIGGER IF NOT EXISTS trg_enseignants_maj_date
AFTER UPDATE ON enseignants
FOR EACH ROW
BEGIN
    UPDATE enseignants
    SET date_modification = datetime('now')
    WHERE id = OLD.id;
END;

-- ---------------------------------------------------------------------
-- Table : periodes_paie
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS periodes_paie (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mois            INTEGER NOT NULL CHECK (mois BETWEEN 1 AND 12),
    annee           INTEGER NOT NULL CHECK (annee >= 2000),
    libelle         TEXT    NOT NULL,
    statut          TEXT    NOT NULL DEFAULT 'brouillon'
                        CHECK (statut IN ('brouillon', 'ouverte', 'validee', 'cloturee')),
    date_creation   TEXT    NOT NULL DEFAULT (datetime('now')),
    date_cloture    TEXT    NULL,
    -- Taux de taxe propre à la période (fraction décimale, ex. '0.055'
    -- pour 5,5 %). Initialisé au taux par défaut en vigueur à la création
    -- (table parametres_paie), modifiable tant que la période n'est pas
    -- validée, puis figé (trigger trg_periodes_paie_taux_fige).
    taux_taxe       TEXT    NOT NULL DEFAULT '0.055'
                        CHECK (CAST(taux_taxe AS REAL) >= 0 AND CAST(taux_taxe AS REAL) < 1),
    -- Règle de taxe : la taxe ne s'applique qu'aux vacataires (0). Les
    -- périodes validées ou clôturées avant ce changement ont été calculées
    -- avec la taxe appliquée aussi aux permanents (1) : elles la gardent,
    -- pour que leurs montants restent strictement identiques.
    taxe_permanents INTEGER NOT NULL DEFAULT 0 CHECK (taxe_permanents IN (0, 1)),
    UNIQUE (mois, annee),
    -- date_cloture est renseignee si et seulement si la periode est CLOTUREE
    CHECK (
        (statut = 'cloturee' AND date_cloture IS NOT NULL)
        OR (statut != 'cloturee' AND date_cloture IS NULL)
    )
);

-- Une période clôturée devient totalement figée (aucune colonne modifiable)
CREATE TRIGGER IF NOT EXISTS trg_periodes_paie_cloturee_figee
BEFORE UPDATE ON periodes_paie
FOR EACH ROW
WHEN OLD.statut = 'cloturee'
BEGIN
    SELECT RAISE(ABORT, 'Periode cloturee : aucune modification autorisee');
END;

-- Seules les transitions BROUILLON->OUVERTE->VALIDEE->CLOTUREE sont permises
CREATE TRIGGER IF NOT EXISTS trg_periodes_paie_transition_invalide
BEFORE UPDATE OF statut ON periodes_paie
FOR EACH ROW
WHEN NOT (
    (OLD.statut = 'brouillon' AND NEW.statut = 'ouverte') OR
    (OLD.statut = 'ouverte' AND NEW.statut = 'validee') OR
    (OLD.statut = 'validee' AND NEW.statut = 'cloturee') OR
    (OLD.statut = NEW.statut)
)
BEGIN
    SELECT RAISE(ABORT, 'Transition de statut de periode invalide');
END;

-- Le taux de taxe d'une période validée ou clôturée ne peut plus changer :
-- un bulletin validé est toujours recalculé à l'identique.
CREATE TRIGGER IF NOT EXISTS trg_periodes_paie_taux_fige
BEFORE UPDATE OF taux_taxe ON periodes_paie
FOR EACH ROW
WHEN OLD.statut IN ('validee', 'cloturee') AND NEW.taux_taxe IS NOT OLD.taux_taxe
BEGIN
    SELECT RAISE(ABORT, 'Taux de taxe fige : la periode est validee ou cloturee');
END;

-- La règle de taxe d'une période validée ne change plus (clôturée : déjà figée).
CREATE TRIGGER IF NOT EXISTS trg_periodes_paie_regle_taxe_figee
BEFORE UPDATE OF taxe_permanents ON periodes_paie
FOR EACH ROW
WHEN OLD.statut IN ('validee', 'cloturee') AND NEW.taxe_permanents IS NOT OLD.taxe_permanents
BEGIN
    SELECT RAISE(ABORT, 'Regle de taxe figee : la periode est validee ou cloturee');
END;

-- Seule une période encore en brouillon peut être supprimée
CREATE TRIGGER IF NOT EXISTS trg_periodes_paie_suppression_limitee
BEFORE DELETE ON periodes_paie
FOR EACH ROW
WHEN OLD.statut != 'brouillon'
BEGIN
    SELECT RAISE(ABORT, 'Seule une periode en brouillon peut etre supprimee');
END;

-- ---------------------------------------------------------------------
-- Table : saisies_heures
-- Heures effectuées par semaine (1 à 5) pour un enseignant et une période
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saisies_heures (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    enseignant_id       INTEGER NOT NULL,
    periode_id          INTEGER NOT NULL,
    numero_semaine      INTEGER NOT NULL CHECK (numero_semaine BETWEEN 1 AND 5),
    heures_effectuees   REAL    NOT NULL CHECK (heures_effectuees >= 0),
    FOREIGN KEY (enseignant_id) REFERENCES enseignants(id) ON DELETE RESTRICT,
    FOREIGN KEY (periode_id)    REFERENCES periodes_paie(id) ON DELETE RESTRICT,
    UNIQUE (enseignant_id, periode_id, numero_semaine)
);

-- Verrouillage : la saisie des heures n'est possible que si la période est en BROUILLON
CREATE TRIGGER IF NOT EXISTS trg_saisies_heures_insert_periode_modifiable
BEFORE INSERT ON saisies_heures
FOR EACH ROW
WHEN (SELECT statut FROM periodes_paie WHERE id = NEW.periode_id) != 'ouverte'
BEGIN
    SELECT RAISE(ABORT, 'Periode non ouverte : saisie heures impossible');
END;

CREATE TRIGGER IF NOT EXISTS trg_saisies_heures_update_periode_modifiable
BEFORE UPDATE ON saisies_heures
FOR EACH ROW
WHEN (SELECT statut FROM periodes_paie WHERE id = OLD.periode_id) != 'ouverte'
BEGIN
    SELECT RAISE(ABORT, 'Periode non ouverte : modification heures impossible');
END;

-- Remarque : contrairement aux triggers INSERT/UPDATE ci-dessus, AUCUN
-- verrou de période n'est appliqué au DELETE de saisies_heures. Ce
-- choix est délibéré : aucun service de saisie normale (heures_service)
-- n'appelle jamais DELETE sur cette table (uniquement upsert = INSERT/
-- UPDATE, qui restent verrouillés hors période OUVERTE ci-dessus). La
-- suppression complète d'une ligne n'est utilisée que par la
-- suppression définitive d'un enseignant
-- (services/enseignant_service.supprimer_enseignant_definitivement),
-- qui doit pouvoir purger les données d'un enseignant même si leur
-- période a depuis été validée/clôturée — la protection de
-- l'historique de paie est alors assurée non pas par le statut de la
-- période, mais par la vérification de l'existence d'un bulletin
-- (cf. table bulletins_paie, dont le DELETE reste lui totalement
-- interdit ci-dessous, sans aucune exception).

-- ---------------------------------------------------------------------
-- Table : elements_remuneration
-- Regroupe les 3 éléments identifiés : prime AP/PP, surveillance/
-- secrétariat, indemnité suggestion/admin. Structure extensible :
-- un nouveau type peut être ajouté sans changer la table.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS elements_remuneration (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    enseignant_id   INTEGER NOT NULL,
    periode_id      INTEGER NOT NULL,
    type_element    TEXT    NOT NULL CHECK (type_element IN (
                        'prime_ap_pp',
                        'surveillance_secretariat',
                        'indemnite_suggestion_admin'
                    )),
    montant         INTEGER NOT NULL DEFAULT 0
                        CHECK (montant >= 0)
                        CHECK (montant = CAST(montant AS INTEGER)),
    FOREIGN KEY (enseignant_id) REFERENCES enseignants(id) ON DELETE RESTRICT,
    FOREIGN KEY (periode_id)    REFERENCES periodes_paie(id) ON DELETE RESTRICT,
    UNIQUE (enseignant_id, periode_id, type_element)
);

CREATE TRIGGER IF NOT EXISTS trg_elements_remuneration_insert_periode_modifiable
BEFORE INSERT ON elements_remuneration
FOR EACH ROW
WHEN (SELECT statut FROM periodes_paie WHERE id = NEW.periode_id) != 'ouverte'
BEGIN
    SELECT RAISE(ABORT, 'Periode non ouverte : saisie element remuneration impossible');
END;

CREATE TRIGGER IF NOT EXISTS trg_elements_remuneration_update_periode_modifiable
BEFORE UPDATE ON elements_remuneration
FOR EACH ROW
WHEN (SELECT statut FROM periodes_paie WHERE id = OLD.periode_id) != 'ouverte'
BEGIN
    SELECT RAISE(ABORT, 'Periode non ouverte : modification element remuneration impossible');
END;

-- Même remarque que pour saisies_heures ci-dessus : aucun verrou de
-- période sur le DELETE (seul le service de suppression définitive
-- d'enseignant l'utilise ; l'INSERT/UPDATE normal reste verrouillé
-- hors période OUVERTE).

-- ---------------------------------------------------------------------
-- Table : retenues
-- Distingue retenue amicale et dette (montants séparés sur le bulletin)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retenues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    enseignant_id   INTEGER NOT NULL,
    periode_id      INTEGER NOT NULL,
    type_retenue    TEXT    NOT NULL CHECK (type_retenue IN (
                        'retenue_amicale',
                        'dette'
                    )),
    montant         INTEGER NOT NULL DEFAULT 0
                        CHECK (montant >= 0)
                        CHECK (montant = CAST(montant AS INTEGER)),
    FOREIGN KEY (enseignant_id) REFERENCES enseignants(id) ON DELETE RESTRICT,
    FOREIGN KEY (periode_id)    REFERENCES periodes_paie(id) ON DELETE RESTRICT,
    UNIQUE (enseignant_id, periode_id, type_retenue)
);

CREATE TRIGGER IF NOT EXISTS trg_retenues_insert_periode_modifiable
BEFORE INSERT ON retenues
FOR EACH ROW
WHEN (SELECT statut FROM periodes_paie WHERE id = NEW.periode_id) != 'ouverte'
BEGIN
    SELECT RAISE(ABORT, 'Periode non ouverte : saisie retenue impossible');
END;

CREATE TRIGGER IF NOT EXISTS trg_retenues_update_periode_modifiable
BEFORE UPDATE ON retenues
FOR EACH ROW
WHEN (SELECT statut FROM periodes_paie WHERE id = OLD.periode_id) != 'ouverte'
BEGIN
    SELECT RAISE(ABORT, 'Periode non ouverte : modification retenue impossible');
END;

-- Même remarque que pour saisies_heures ci-dessus : aucun verrou de
-- période sur le DELETE (seul le service de suppression définitive
-- d'enseignant l'utilise ; l'INSERT/UPDATE normal reste verrouillé
-- hors période OUVERTE).

-- ---------------------------------------------------------------------
-- Table : bulletins_paie
-- Historique immuable : toutes les valeurs utilisées au moment du calcul
-- sont dupliquées ici (snapshot), indépendamment des données sources.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bulletins_paie (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    enseignant_id               INTEGER NOT NULL,
    periode_id                  INTEGER NOT NULL,

    -- Snapshots identité (immuables même si l'enseignant change ensuite)
    nom_snapshot                TEXT    NOT NULL,
    prenom_snapshot             TEXT    NOT NULL,
    sexe_snapshot                TEXT   NOT NULL CHECK (sexe_snapshot IN ('M', 'F')),
    statut_snapshot              TEXT   NOT NULL CHECK (statut_snapshot IN ('V', 'P')),

    -- Heures (durées : REAL)
    total_heures                REAL    NOT NULL CHECK (total_heures >= 0),

    -- Montants (FCFA entiers : INTEGER)
    taux_horaire                 INTEGER NOT NULL
                                    CHECK (taux_horaire >= 0)
                                    CHECK (taux_horaire = CAST(taux_horaire AS INTEGER)),
    gain_heures                  INTEGER NOT NULL
                                    CHECK (gain_heures >= 0)
                                    CHECK (gain_heures = CAST(gain_heures AS INTEGER)),
    prime_ap_pp                  INTEGER NOT NULL DEFAULT 0
                                    CHECK (prime_ap_pp >= 0)
                                    CHECK (prime_ap_pp = CAST(prime_ap_pp AS INTEGER)),
    surveillance_secretariat     INTEGER NOT NULL DEFAULT 0
                                    CHECK (surveillance_secretariat >= 0)
                                    CHECK (surveillance_secretariat = CAST(surveillance_secretariat AS INTEGER)),
    indemnite_suggestion_admin   INTEGER NOT NULL DEFAULT 0
                                    CHECK (indemnite_suggestion_admin >= 0)
                                    CHECK (indemnite_suggestion_admin = CAST(indemnite_suggestion_admin AS INTEGER)),
    base_taxable                 INTEGER NOT NULL
                                    CHECK (base_taxable >= 0)
                                    CHECK (base_taxable = CAST(base_taxable AS INTEGER)),
    taxe_5pct                    INTEGER NOT NULL
                                    CHECK (taxe_5pct >= 0)
                                    CHECK (taxe_5pct = CAST(taxe_5pct AS INTEGER)),
    retenue_amicale               INTEGER NOT NULL DEFAULT 0
                                    CHECK (retenue_amicale >= 0)
                                    CHECK (retenue_amicale = CAST(retenue_amicale AS INTEGER)),
    dette                         INTEGER NOT NULL DEFAULT 0
                                    CHECK (dette >= 0)
                                    CHECK (dette = CAST(dette AS INTEGER)),
    net_a_payer                  INTEGER NOT NULL
                                    CHECK (net_a_payer = CAST(net_a_payer AS INTEGER)),

    date_generation               TEXT    NOT NULL DEFAULT (datetime('now')),
    utilisateur_generation         TEXT    NULL,

    FOREIGN KEY (enseignant_id) REFERENCES enseignants(id) ON DELETE RESTRICT,
    FOREIGN KEY (periode_id)    REFERENCES periodes_paie(id) ON DELETE RESTRICT,
    UNIQUE (enseignant_id, periode_id)
);

-- Un bulletin ne peut être généré que pour une période VALIDEE
CREATE TRIGGER IF NOT EXISTS trg_bulletins_paie_requiert_periode_validee
BEFORE INSERT ON bulletins_paie
FOR EACH ROW
WHEN (SELECT statut FROM periodes_paie WHERE id = NEW.periode_id) != 'validee'
BEGIN
    SELECT RAISE(ABORT, 'Le bulletin ne peut etre genere que pour une periode validee');
END;

-- Immutabilité totale et inconditionnelle des bulletins générés
CREATE TRIGGER IF NOT EXISTS trg_bulletins_paie_immuable_update
BEFORE UPDATE ON bulletins_paie
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Bulletin immuable : modification interdite');
END;

CREATE TRIGGER IF NOT EXISTS trg_bulletins_paie_immuable_delete
BEFORE DELETE ON bulletins_paie
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Bulletin immuable : suppression interdite');
END;

-- ---------------------------------------------------------------------
-- Table : utilisateurs (module 11 — authentification et permissions)
-- ---------------------------------------------------------------------
-- password_hash ne contient JAMAIS de mot de passe en clair : format
-- auto-descriptif produit par utils.security.hash_password (scrypt,
-- paramètres + sel + hash, cf. ce module pour le détail).
CREATE TABLE IF NOT EXISTS utilisateurs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nom                 TEXT    NOT NULL,
    prenom              TEXT    NOT NULL,
    username            TEXT    NOT NULL UNIQUE,
    password_hash       TEXT    NOT NULL,
    role                TEXT    NOT NULL CHECK (role IN ('admin', 'gestionnaire_paie', 'consultation')),
    actif               INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    date_creation       TEXT    NOT NULL DEFAULT (datetime('now')),
    date_modification   TEXT    NOT NULL DEFAULT (datetime('now')),
    derniere_connexion  TEXT    NULL
);

-- Met à jour automatiquement date_modification à chaque UPDATE
-- (même convention que trg_enseignants_maj_date).
CREATE TRIGGER IF NOT EXISTS trg_utilisateurs_maj_date
AFTER UPDATE ON utilisateurs
FOR EACH ROW
BEGIN
    UPDATE utilisateurs
    SET date_modification = datetime('now')
    WHERE id = OLD.id;
END;

CREATE INDEX IF NOT EXISTS idx_utilisateurs_username ON utilisateurs(username);

-- ---------------------------------------------------------------------
-- Table : audit_log
-- Structure prévue dès maintenant ; alimentation complète faite plus
-- tard par les services (paie_service, backup_service, etc.).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date_action     TEXT    NOT NULL DEFAULT (datetime('now')),
    type_action     TEXT    NOT NULL CHECK (type_action IN (
                        'creation',
                        'modification',
                        'cloture_periode',
                        'validation_periode',
                        'reinitialisation_donnees',
                        'reinitialisation_donnees_echec',
                        'parametre_paie_modifie',
                        'modele_bulletin_importe',
                        'modele_bulletin_active',
                        'modele_bulletin_supprime',
                        'statut_enseignant_modifie',
                        'calcul_paie',
                        'generation_bulletin',
                        'export_comptable',
                        'restauration_sauvegarde',
                        'suppression_definitive',
                        'connexion_reussie',
                        'connexion_echouee',
                        'deconnexion',
                        'utilisateur_cree',
                        'utilisateur_modifie',
                        'utilisateur_desactive',
                        'utilisateur_active',
                        'mot_de_passe_modifie',
                        'mot_de_passe_reinitialise',
                        'role_modifie',
                        'periode_ouverte',
                        'validation_refusee',
                        'cloture_refusee',
                        'reporting_exporte',
                        'rapprochement_execute',
                        'document_archive',
                        'document_integrite_verifiee',
                        'document_supprime',
                        'document_telecharge',
                        'archive_creee',
                        'archive_restauree',
                        'import_donnees',
                        'import_donnees_echec',
                        'import_donnees_simulation',
                        'alerte_creee',
                        'alerte_acquittee',
                        'alerte_resolue',
                        'alerte_ignoree',
                        'automatisation_preparee',
                        'automatisation_executee',
                        'automatisation_echec',
                        'generation_massive_bulletins',
                        'export_massif',
                        'archive_massive'
                    )),
    entite          TEXT    NULL,       -- ex: 'enseignant', 'periode_paie'
    entite_id       INTEGER NULL,
    utilisateur     TEXT    NULL,
    details         TEXT    NULL
);

-- ---------------------------------------------------------------------
-- Table : documents (module 14 — registre documentaire)
-- ---------------------------------------------------------------------
-- Registre léger des fichiers générés par l'application (bulletins,
-- exports Excel, états de paie). Ne duplique PAS les données de paie
-- déjà présentes dans bulletins_paie (snapshot immuable, module 12) :
-- cette table référence uniquement l'EMPLACEMENT et l'INTÉGRITÉ d'un
-- fichier sur disque (chemin, taille, hash), jamais son contenu
-- métier. `hash_fichier` permet de détecter une modification après
-- génération (module 14, section 13).
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type_document   TEXT    NOT NULL CHECK (type_document IN (
                        'bulletin', 'rapport_paie', 'etat_paie', 'export_excel'
                    )),
    nom_fichier     TEXT    NOT NULL,
    chemin          TEXT    NOT NULL,
    enseignant_id   INTEGER NULL,
    periode_id      INTEGER NULL,
    date_creation   TEXT    NOT NULL DEFAULT (datetime('now')),
    utilisateur     TEXT    NULL,
    taille          INTEGER NULL,
    hash_fichier    TEXT    NULL,

    FOREIGN KEY (enseignant_id) REFERENCES enseignants(id) ON DELETE SET NULL,
    FOREIGN KEY (periode_id)    REFERENCES periodes_paie(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_periode ON documents(periode_id);
CREATE INDEX IF NOT EXISTS idx_documents_enseignant ON documents(enseignant_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(type_document);

-- ---------------------------------------------------------------------
-- Tables : imports / import_erreurs (module 15 — importation massive)
-- ---------------------------------------------------------------------
-- Historique des opérations d'importation. Ne duplique aucune donnée
-- métier : uniquement des compteurs et métadonnées décrivant chaque
-- opération, pour la traçabilité et le rapport d'import (section 17).
CREATE TABLE IF NOT EXISTS imports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    utilisateur         TEXT    NULL,
    date_import         TEXT    NOT NULL DEFAULT (datetime('now')),
    nom_fichier         TEXT    NOT NULL,
    type_import         TEXT    NOT NULL CHECK (type_import IN (
                            'enseignants', 'heures', 'remunerations', 'retenues'
                        )),
    statut              TEXT    NOT NULL CHECK (statut IN (
                            'simulation', 'termine', 'echec', 'annule'
                        )),
    periode_id          INTEGER NULL,
    nb_lignes           INTEGER NOT NULL DEFAULT 0,
    nb_creations        INTEGER NOT NULL DEFAULT 0,
    nb_mises_a_jour     INTEGER NOT NULL DEFAULT 0,
    nb_ignorees         INTEGER NOT NULL DEFAULT 0,
    nb_rejetees         INTEGER NOT NULL DEFAULT 0,
    nb_erreurs          INTEGER NOT NULL DEFAULT 0,
    nb_avertissements   INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (periode_id) REFERENCES periodes_paie(id) ON DELETE SET NULL
);

-- Détail ligne par ligne des anomalies rencontrées (section 18).
CREATE TABLE IF NOT EXISTS import_erreurs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id   INTEGER NOT NULL,
    ligne       INTEGER NOT NULL,
    champ       TEXT    NULL,
    valeur      TEXT    NULL,
    niveau      TEXT    NOT NULL CHECK (niveau IN ('erreur', 'avertissement', 'info')),
    message     TEXT    NOT NULL,

    FOREIGN KEY (import_id) REFERENCES imports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_imports_periode ON imports(periode_id);
CREATE INDEX IF NOT EXISTS idx_import_erreurs_import ON import_erreurs(import_id);

-- ---------------------------------------------------------------------
-- Table : alertes (module 16 — notifications et surveillance opérationnelle)
-- ---------------------------------------------------------------------
-- Ne duplique aucune logique de détection : chaque alerte reflète un
-- résultat déjà produit par un service existant (contrôle de paie,
-- intégrité documentaire, diagnostic, import). `cle_deduplication`
-- garantit qu'une même anomalie ne génère jamais plusieurs alertes
-- actives identiques (section 13) : une nouvelle détection identique
-- met à jour `date_derniere_detection` plutôt que de créer une ligne.
--
-- ON DELETE CASCADE (et non RESTRICT) sur periode_id/enseignant_id :
-- une alerte n'a plus de sens une fois l'objet qu'elle concerne
-- supprimé, et RESTRICT bloquerait à tort des suppressions déjà
-- strictement protégées par ailleurs (modules 08/09) pour la seule
-- raison qu'une alerte les référence — cela romprait des
-- fonctionnalités déjà validées, contraire à la règle de
-- non-régression de ce module.
CREATE TABLE IF NOT EXISTS alertes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    type_alerte             TEXT    NOT NULL,
    niveau                  TEXT    NOT NULL CHECK (niveau IN ('info', 'avertissement', 'erreur', 'critique')),
    titre                   TEXT    NOT NULL,
    message                 TEXT    NOT NULL,
    source                  TEXT    NOT NULL,
    cle_deduplication       TEXT    NOT NULL,
    statut                  TEXT    NOT NULL DEFAULT 'nouvelle' CHECK (statut IN (
                                'nouvelle', 'lue', 'acquittee', 'resolue', 'ignoree'
                            )),
    date_creation           TEXT    NOT NULL DEFAULT (datetime('now')),
    date_derniere_detection TEXT    NOT NULL DEFAULT (datetime('now')),
    periode_id              INTEGER NULL,
    enseignant_id           INTEGER NULL,
    document_id             INTEGER NULL,
    import_id               INTEGER NULL,
    utilisateur_concerne    TEXT    NULL,
    date_acquittement       TEXT    NULL,
    acquitte_par            TEXT    NULL,
    date_resolution         TEXT    NULL,
    resolue_par             TEXT    NULL,

    FOREIGN KEY (periode_id)    REFERENCES periodes_paie(id) ON DELETE CASCADE,
    FOREIGN KEY (enseignant_id) REFERENCES enseignants(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id)   REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (import_id)     REFERENCES imports(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alertes_dedup_active
    ON alertes(cle_deduplication)
    WHERE statut NOT IN ('resolue', 'ignoree');

CREATE INDEX IF NOT EXISTS idx_alertes_niveau ON alertes(niveau);
CREATE INDEX IF NOT EXISTS idx_alertes_statut ON alertes(statut);
CREATE INDEX IF NOT EXISTS idx_alertes_periode ON alertes(periode_id);

-- ---------------------------------------------------------------------
-- Index utiles (accélèrent les jointures et filtres fréquents)
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_saisies_heures_periode ON saisies_heures(periode_id);
CREATE INDEX IF NOT EXISTS idx_elements_remuneration_periode ON elements_remuneration(periode_id);
CREATE INDEX IF NOT EXISTS idx_retenues_periode ON retenues(periode_id);
CREATE INDEX IF NOT EXISTS idx_bulletins_periode ON bulletins_paie(periode_id);
CREATE INDEX IF NOT EXISTS idx_enseignants_actif ON enseignants(actif);

-- ---------------------------------------------------------------------
-- Table : parametres_paie
-- Paramètres de paie modifiables par l'administrateur (taux de taxe par
-- défaut des nouvelles périodes, modèle de bulletin actif). Stockés en
-- base pour être inclus dans les sauvegardes et restaurations.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parametres_paie (
    cle                 TEXT    PRIMARY KEY,
    valeur              TEXT    NOT NULL,
    date_modification   TEXT    NOT NULL DEFAULT (datetime('now')),
    utilisateur         TEXT    NULL
);

-- ---------------------------------------------------------------------
-- Table : modeles_bulletin
-- Modèles de bulletin importés (Word .docx ou PDF). Le fichier est
-- conservé dans data/modeles_bulletin/ ; `correspondances` contient,
-- en JSON, les zones à remplacer (modèles PDF) ou la liste des balises
-- détectées (modèles Word).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS modeles_bulletin (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    nom                     TEXT    NOT NULL,
    format                  TEXT    NOT NULL CHECK (format IN ('docx', 'pdf')),
    nom_fichier             TEXT    NOT NULL UNIQUE,
    nom_fichier_origine     TEXT    NOT NULL,
    empreinte               TEXT    NOT NULL,
    correspondances         TEXT    NOT NULL DEFAULT '[]',
    date_import             TEXT    NOT NULL DEFAULT (datetime('now')),
    utilisateur             TEXT    NULL
);
