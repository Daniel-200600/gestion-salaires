# Rapport de robustesse — Module 19

## 1. Volumes testés

| Scénario | Volume | Résultat |
|---|---|---|
| Aucun enseignant | 0 | Statistiques à zéro observation, jamais de plantage. |
| Un seul enseignant | 1 | Écart-type/quartiles correctement `None` (non définis mathématiquement). |
| Effectif réaliste | 300 enseignants, sexe et statut variés | Chargement groupé confirmé (pas de N+1 requêtes), résultats corrects. |
| Aucune période | 0 | Liste vide, aucune fonction ne plante. |
| Montant élevé | Taux horaire 999 999 FCFA, 200h/mois | Résultat toujours un entier (jamais de float pour un montant monétaire). |
| Taux horaire nul | 0 FCFA | Gain à zéro, net calculé sans erreur. |

## 2. Scénarios de panne simulée

- **Import massif** : panne au 2ᵉ enregistrement sur 3 → rollback complet, zéro ligne en base après coup (revérifié, module 15).
- **Génération massive de bulletins** : exécutée 3 fois de suite sur les mêmes données → toujours exactement 1 document par enseignant (idempotence confirmée, module 18).
- **Restauration de sauvegarde** : fichier inexistant, fichier non-SQLite, absence de confirmation → tous refusés proprement ; la base active reste intacte et interrogeable après chaque échec (vérifié en créant une donnée avant l'incident puis en confirmant sa présence après).

## 3. Comportement transactionnel

Toutes les opérations sensibles auditées (import, génération massive, restauration) suivent le principe **tout ou rien** : soit l'opération complète réussit et est journalisée, soit elle échoue et la base reste dans son état antérieur exact — jamais d'état intermédiaire visible.

## 4. Limites SQLite (documentées, non modifiées)

SQLite n'autorise qu'un seul écrivain actif à la fois. Avec la configuration actuelle du projet (`database/connection.py`, aucun `busy_timeout` explicite, journal en mode par défaut), une seconde connexion tentant d'écrire pendant qu'une transaction est ouverte sur une première reçoit une erreur `sqlite3.OperationalError` immédiate plutôt que d'attendre — testé et confirmé (`tests/robustness/test_transactions_and_recovery.py::test_deux_connexions_simultanees_en_ecriture_comportement_sqlite`). Aucune corruption ni écriture silencieusement perdue n'a été observée : l'échec est toujours explicite. Ce comportement est adapté à l'usage réel de l'application (un établissement scolaire, un nombre limité d'utilisateurs simultanés) et n'a pas été modifié dans ce module — voir `docs/security_audit.md`, section 15, pour la justification de ce choix.

## 5. Comportement des exports et archives

- Aucun export ni archive testé ne laisse de fichier partiellement écrit après un échec (les échecs surviennent avant l'écriture, ou l'écriture elle-même est atomique côté `openpyxl`/`zipfile`).
- Les archives ZIP (module 14/18) rejettent systématiquement les chemins dangereux (path traversal, chemins absolus, style Windows) et ne créent jamais de fichier hors du dossier de destination prévu — revalidé au module 19.

## 6. Performance observée

Aucune dégradation notable constatée jusqu'à 300 enseignants avec données de paie complètes sur une période (chargement groupé confirmé — jamais de requête SQL par enseignant dans les chemins critiques testés : statistiques, automatisation, import). Aucun test au-delà de ce volume n'a été exécuté ; le comportement à plusieurs milliers d'enseignants n'est pas garanti par ce rapport.

## 7. Non-régression

```
Tests avant le module 19 : 779
Tests après le module 19 : 923 passed, 3 skipped
Régressions : AUCUNE
```

Aucun test existant n'a été supprimé, désactivé, ni modifié pour masquer un problème. Les 3 tests "skip" concernent uniquement des noms de permission recherchés par un test paramétré qui n'existent pas sous ce nom exact dans la matrice actuelle — comportement voulu (le test vérifie une propriété de sécurité quand la permission existe, sans supposer sa présence).
