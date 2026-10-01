# Module 10 — Administration, sécurité, sauvegarde, configuration

## 1. Objectif

Professionnaliser l'application pour un usage durable dans un
établissement scolaire : administration technique centralisée,
configuration persistante, sauvegarde/restauration sécurisées de la
base SQLite, diagnostic de santé du système, logs techniques
distincts de l'audit métier, et portabilité complète (aucun chemin
codé en dur spécifique à une machine).

Aucune règle de calcul de paie n'est touchée : `services/paie_service.py`
reste l'unique moteur, `TAUX_TAXE` reste fixé à 5 % et n'est jamais
modifiable depuis l'interface.

## 2. Ce qui existait déjà (réutilisé, non recréé)

- Chemins déjà construits relativement à `BASE_DIR` dans
  `config/settings.py` (`Path(__file__).resolve()`), aucun chemin
  absolu codé en dur — la portabilité de base était déjà acquise.
- Audit métier (`audit_log_repository`), avec
  `TypeActionAudit.RESTAURATION_SAUVEGARDE` déjà provisionné dans le
  schéma depuis la fondation du projet mais jamais utilisé jusqu'ici.
- `database.initialization.get_table_names` (déjà présent), réutilisé
  tel quel par le diagnostic.

`config/logging_config.py`, mentionné comme existant dans la demande,
était en réalité absent du projet : il a été créé pour ce module.

## 3. Ce que le module 10 ajoute

### 3.1 Configuration centralisée — `config/settings.py` (additif)

`LOGS_DIR`, `LOG_FILE`, `PARAMETRES_PATH` ajoutés, toujours dérivés de
`BASE_DIR`. `ensure_data_dirs()` crée désormais aussi `LOGS_DIR`.

### 3.2 Logging technique — `config/logging_config.py` (nouveau)

`configurer_logging()` (idempotent), `obtenir_logger(nom)`,
`lire_dernieres_lignes(n)` (lecture bornée, jamais le fichier entier
en mémoire). Rotation automatique (1 Mo, 3 fichiers conservés). Aucun
mot de passe ni donnée personnelle sensible journalisé. Distinct de
l'audit métier existant, qui reste inchangé et n'est jamais remplacé.

### 3.3 Paramètres de l'établissement — `services/parametres_service.py` (nouveau)

Persistance JSON (`data/parametres_etablissement.json`), survit à un
redémarrage (contrairement à `st.session_state`). Valeurs par défaut
si fichier absent, vide ou corrompu — jamais d'exception propagée.
N'expose ni ne modifie jamais `TAUX_TAXE`.

### 3.4 Sauvegarde et restauration — `services/backup_service.py` (nouveau)

- `creer_sauvegarde()` : copie cohérente via `sqlite3.Connection.backup()`
  (jamais une copie de fichier brute), nom horodaté
  (`backup_2026-09-14_165500.db`), dossier créé automatiquement, pas
  d'écrasement en cas de collision de nom.
- `verifier_integrite()` : en-tête SQLite + `PRAGMA integrity_check`,
  jamais d'exception, toujours un message compréhensible.
- `restaurer_sauvegarde()` : confirmation obligatoire → validation du
  fichier → sauvegarde de sécurité automatique de la base actuelle →
  restauration → vérification post-restauration (intégrité + tables
  essentielles) → rollback automatique vers la sauvegarde de sécurité
  en cas d'échec à n'importe quelle étape → audit métier
  (`RESTAURATION_SAUVEGARDE`) systématique, succès ou échec.
- `lister_sauvegardes()` : nom, date, taille lisible, emplacement.

### 3.5 Diagnostic système — `services/diagnostic_service.py` (nouveau)

Tables essentielles dérivées **du schéma SQL réel** (regex sur
`database/schema.sql`), jamais d'une liste arbitraire. Dénombrements
non sensibles (enseignants, périodes, bulletins réellement générés
sur disque, lignes d'audit), taille des exports, nombre de
sauvegardes, présence du template Word, dossiers essentiels.

État global (section 21) :
- 🔴 **Rouge** : base inaccessible, intégrité échouée, table ou
  fichier critique manquant.
- 🟠 **Orange** : tout est correct mais aucune sauvegarde n'existe
  encore (non bloquant).
- 🟢 **Vert** : tout est en ordre.

### 3.6 Page Administration — `pages/10_Administration.py` (nouveau)

7 onglets : Paramètres (formulaire persistant + paramètres de paie en
lecture seule + chemins de stockage), Sauvegarde, Restauration
(confirmation par saisie exacte « JE CONFIRME CETTE OPÉRATION »),
Diagnostic, Maintenance (vérifications non destructives uniquement),
Logs (recherche, nombre de lignes borné), À propos (versions Python /
Streamlit / SQLite réellement installées, aucune inventée).

### 3.7 Accueil — `app.py` (amélioration légère)

État du système et période active affichés en tête de page, liens
vers les fonctions principales et l'Administration. Crée également
`EXPORT_DIR`/`EXPORT_DIR_BULLETINS` dès le démarrage (portabilité :
une installation neuve, sur une autre machine, ne doit jamais afficher
un état « rouge » trompeur simplement parce qu'aucun export n'a encore
été généré).

## 4. Base de données

Aucune modification du schéma. `database/repositories/audit_log_repository.py` :
ajout additif de `compter_tout()` (dénombrement global, utilisé par le
diagnostic).

## 5. Sécurité

- Restauration : confirmation explicite obligatoire, sauvegarde de
  sécurité systématique avant tout remplacement, validation
  d'intégrité avant ET après, rollback automatique en cas d'échec.
- Aucune authentification artificielle ajoutée (conforme à la
  consigne) : les opérations administratives sensibles restent
  protégées par confirmation explicite, pas par un système de comptes
  fictif.
- Maintenance strictement non destructive : aucune suppression
  automatique de bulletin, historique, sauvegarde, log ou donnée de
  paie.

## 6. Portabilité

Tous les chemins dérivent de `BASE_DIR = Path(__file__).resolve().parent.parent`
(`config/settings.py`). Aucun chemin absolu spécifique à une machine
dans le code. L'application peut être déplacée telle quelle sur un
autre ordinateur.

## 7. Test de référence conservé

100 h × 2 000 FCFA → Net = 208 250 FCFA — inchangé, aucune règle de
paie modifiée par ce module.
