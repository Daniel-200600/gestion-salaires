# Rapport d'audit de sécurité — Module 19

**Méthode** : inspection statique du code (grep ciblé + lecture), tests dynamiques
sur les points d'entrée réels de l'application, base de départ validée à 779 tests
passants avant toute modification.

**Avertissement honnête** : ce rapport ne prétend pas que l'application est
« parfaitement sécurisée ». Il documente ce qui a été vérifié, ce qui a été
corrigé, et ce qui reste comme limite connue.

---

## 1. Authentification

| ID | Gravité | Description | Statut |
|---|---|---|---|
| AUTH-01 | INFO | Hachage scrypt avec sel aléatoire par mot de passe, comparaison en temps constant (`hmac.compare_digest`), hash malformé ne lève jamais d'exception. | Conforme, vérifié par test. |
| AUTH-02 | INFO | Message de connexion strictement identique pour « utilisateur inexistant » et « mot de passe incorrect ». | Conforme, vérifié par test. |
| AUTH-03 | INFO | Verrouillage après `MAX_LOGIN_ATTEMPTS` échecs, par utilisateur, avec expiration de fenêtre et réinitialisation après succès. | Conforme, vérifié par test. |
| AUTH-04 | INFO | Aucun mot de passe (clair ou haché sans nécessité), secret ou token codé en dur dans le code source. | Vérifié par audit statique. |

## 2. Autorisation / permissions

| ID | Gravité | Description | Statut |
|---|---|---|---|
| **AUTHZ-01** | **ÉLEVÉ** | **La session utilisateur ne revérifiait jamais l'état réel du compte (actif/rôle) en base après la connexion initiale.** Un compte désactivé par un administrateur, ou dont le rôle était rétrogradé, conservait ses anciens privilèges en session jusqu'à expiration naturelle du délai d'inactivité (`SESSION_TIMEOUT_SECONDES`), potentiellement long. **Impact** : un utilisateur dont l'accès vient d'être révoqué pouvait continuer à effectuer des opérations sensibles (paie, validation, suppression) pendant cette fenêtre. **Correction** : ajout de `services/auth_service.revalider_session()` (fonction pure, testable), appelée à chaque `utils/session_auth.est_authentifie()` — donc à chaque page protégée. Un compte désactivé ou supprimé fait désormais échouer immédiatement la session ; un changement de rôle est répercuté immédiatement. **Test de non-régression** : `tests/security/test_auth_security.py::test_revalider_session_utilisateur_desactive_retourne_none`, `test_revalider_session_reflete_changement_de_role`. |
| AUTHZ-02 | INFO | La matrice de permissions a été vérifiée exhaustivement : ADMIN possède systématiquement toutes les permissions connues, et aucune permission n'est jamais accordée à CONSULTATION sans l'être aussi à GESTIONNAIRE_PAIE (hiérarchie cohérente). | Vérifié par test paramétré sur l'ensemble de la matrice (74 cas). |
| AUTHZ-03 | INFO | `permission_service.a_permission(None, ...)` retourne toujours `False` plutôt que de lever une exception. | Vérifié par test. |

## 3. SQL

| ID | Gravité | Description | Statut |
|---|---|---|---|
| SQL-01 | INFO | Toutes les requêtes du projet utilisent des paramètres liés (`?`) — aucune concaténation ni f-string interpolant une valeur utilisateur, à une exception près (voir SQL-02). Vérifié par audit statique sur l'ensemble de `database/repositories/`. | Conforme. |
| SQL-02 | FAIBLE | `alerte_repository.changer_statut` construit une requête `UPDATE` via f-string interpolant deux **noms de colonnes** (`date_acquittement`/`acquitte_par` ou `date_resolution`/`resolue_par`). Ces valeurs proviennent exclusivement d'un dictionnaire interne fixe (`colonnes_date`), jamais d'une entrée utilisateur — aucun risque d'injection réel. Revu manuellement, sans modification (le code fonctionnel n'a pas été touché pour une raison purement stylistique). | Revu, jugé sans danger. |
| SQL-03 | INFO | Tentatives d'injection (`' OR '1'='1`, `'; DROP TABLE ...`, `' UNION SELECT ...`, etc.) testées sur la création d'enseignant et la recherche : stockées comme texte littéral, jamais exécutées ; schéma intact après tentative. | Vérifié par test (7 charges × plusieurs points d'entrée). |

## 4. Fichiers

| ID | Gravité | Description | Statut |
|---|---|---|---|
| FICHIER-01 | INFO | `nettoyer_nom_fichier` neutralise systématiquement `/` et `\` (remplacés par `_`) — aucune séquence de path traversal ne peut survivre au nettoyage, testé sur 6 charges dont chemins Windows/Unix absolus et relatifs. | Conforme. |
| FICHIER-02 | INFO | Les fichiers importés (module 15) ne sont jamais lus depuis un chemin dérivé du nom fourni par l'utilisateur : `import_service.lire_fichier(chemin, nom_fichier=...)` sépare strictement le chemin contrôlé par l'application du nom affiché. | Vérifié par test. |
| FICHIER-03 | INFO | Fichiers malformés (Excel vide, CSV vide, ZIP corrompu, extension interdite) refusés avec message clair, jamais de plantage. | Déjà couvert extensivement au module 15 ; revérifié sans régression. |

## 5. ZIP

| ID | Gravité | Description | Statut |
|---|---|---|---|
| ZIP-01 | INFO | Aucun appel à `zipfile.ZipFile.extractall()` n'existe dans le projet — seule `archive_service.extraire_archive_securise` extrait des archives, avec validation explicite de chaque chemin de membre avant écriture. | Vérifié par audit statique (`grep extractall`). |
| ZIP-02 | INFO | Path traversal testé sur des charges `../../../evil.txt`, chemin absolu (`/etc/...`), et style Windows (`..\\..\\evil.txt`) : dans les trois cas, le membre est rejeté et journalisé, jamais extrait hors du dossier de destination. | Vérifié par test. |
| ZIP-03 | INFO | Archive vide et archive corrompue : gérées proprement, sans exception non contrôlée. | Vérifié par test. |

## 6. Base SQLite

| ID | Gravité | Description | Statut |
|---|---|---|---|
| DB-01 | INFO | `PRAGMA integrity_check` retourne `ok` sur une base saine ; le diagnostic système (module 10) détecte correctement une base inexistante ou partiellement dépourvue de tables applicatives sans jamais planter. | Vérifié par test. |
| DB-02 | INFO | Clés étrangères activées systématiquement (`PRAGMA foreign_keys = ON`) sur chaque connexion. | Confirmé par lecture du code (`database/connection.py`). |

## 7. Transactions

| ID | Gravité | Description | Statut |
|---|---|---|---|
| TX-01 | INFO | Rollback d'import massif (module 15) revérifié sans régression : une panne simulée en cours de lot laisse la base exactement dans l'état antérieur, zéro ligne partielle. | Vérifié par test. |

## 8. Documents

| ID | Gravité | Description | Statut |
|---|---|---|---|
| DOC-01 | INFO | Hash SHA-256 recalculé correctement, détection de modification testée (module 14, revérifiée sans régression). | Conforme. |

## 9. Sauvegardes

| ID | Gravité | Description | Statut |
|---|---|---|---|
| BACKUP-01 | INFO | Restauration : fichier inexistant, fichier non-SQLite, et absence de confirmation explicite systématiquement refusés. Après un échec de restauration, la base active reste intacte et pleinement utilisable — vérifié en créant un enseignant, en simulant un échec de restauration, puis en confirmant sa présence après coup. | Vérifié par test. |

## 10. Logs

| ID | Gravité | Description | Statut |
|---|---|---|---|
| LOG-01 | INFO | Aucune colonne `password`/`mot_de_passe` dans `audit_log` ni dans `utilisateurs` (seule une colonne de hash existe). Le mot de passe recherché n'apparaît jamais dans le détail d'audit d'une tentative de connexion, réussie ou échouée. | Vérifié par test. |

## 11. Imports

| ID | Gravité | Description | Statut |
|---|---|---|---|
| IMPORT-01 | INFO | Comportement transactionnel du module 15 revérifié sans régression (voir TX-01). | Conforme. |

## 12. Automatisation

| ID | Gravité | Description | Statut |
|---|---|---|---|
| AUTOM-01 | INFO | Idempotence de la génération massive de bulletins revérifiée avec 3 exécutions successives : toujours exactement un seul document par enseignant, jamais de duplication. | Vérifié par test. |

## 13. Tests de résistance

Voir `docs/robustesse.md` pour le détail des volumes et scénarios testés.

## 14. Résultats

```
Tests avant le module 19 : 779
Nouveaux tests de sécurité : 127 (dont 3 skip légitimes — nom de permission non trouvé dans cette version)
Nouveaux tests de robustesse : 20
Total après le module 19 : 923 passed, 3 skipped
Régressions : AUCUNE
```

## 15. Limites restantes (déclarées explicitement)

- **Aucun test d'exécution concurrente réelle multi-processus** n'a été mis en place (l'environnement de test est mono-processus) — le test de concurrence ajouté (`test_deux_connexions_simultanees_en_ecriture_comportement_sqlite`) démontre le comportement de verrouillage de SQLite avec deux connexions dans le même processus, ce qui est représentatif mais pas un test de charge réel multi-utilisateurs.
- **SQLite n'utilise pas le mode WAL** et n'a pas de `busy_timeout` configuré explicitement (`database/connection.py`) — un deuxième écrivain simultané reçoit une erreur immédiate plutôt que d'attendre quelques centaines de millisecondes. Ce comportement n'a **pas été modifié** dans ce module : le changer tardivement, sans campagne de tests dédiée sur l'ensemble des 923 tests existants, comportait un risque de régression jugé disproportionné par rapport au gain pour une application mono-établissement à faible concurrence. C'est une amélioration candidate pour un futur module, pas une correction de ce module-ci.
- **Aucun test de charge à plusieurs milliers d'enseignants** n'a été exécuté (seulement testé jusqu'à 300, jugé représentatif d'un établissement scolaire réel) — au-delà, le comportement n'est pas garanti et n'a pas été mesuré.
- L'audit n'a pas couvert une revue de sécurité de Streamlit lui-même (framework tiers) ni de l'environnement d'exécution (OS, réseau) — hors périmètre du code applicatif.
