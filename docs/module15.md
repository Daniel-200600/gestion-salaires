# Module 15 — Importation massive, validation et qualité des données

## 1. Architecture

```
pages/14_Importation_Donnees.py     (orchestration UI uniquement)
        |
services/import_service.py          (indépendant de Streamlit)
        |
        +-- utils/validators.py             (réutilisées telles quelles — aucune duplication)
        +-- database/repositories/*.py       (creer/mettre_a_jour/upsert, avec support conn)
        +-- services/paie_service.py         (jamais dupliqué, jamais recalculé ici)
```

**Découverte clé à l'inspection préalable** : `utils/validators.py`
contenait déjà toutes les primitives de validation nécessaires
(`valider_sexe`, `valider_statut`, `valider_taux_horaire`,
`valider_heures`, `valider_montant_fcfa`, `verifier_periode_ouverte`).
Le module 15 les réutilise intégralement — **zéro deuxième source de
vérité** pour les règles métier.

## 2. Workflow (pipeline complet, section 2)

```
Fichier → Lecture → Détection format → Analyse colonnes →
Prévisualisation → Validation technique → Validation métier →
Détection doublons → Dry run → Confirmation → Import transactionnel →
Rapport → Audit
```

Chaque étape est une fonction pure/quasi-pure de
`services/import_service.py`, testable indépendamment de Streamlit.

## 3. Formats acceptés

`.xlsx` (toutes feuilles lues, sélection dans l'interface si
plusieurs) et `.csv`. Taille maximale documentée : 10 Mo
(`TAILLE_MAX_OCTETS`). Fichier vide, corrompu, ou d'extension non
autorisée : toujours un message clair, jamais un traceback.

## 4. Colonnes et normalisation

`VARIANTES_COLONNES` (dans `import_service.py`) liste explicitement
les variantes reconnues par type d'import (ex. `NOM`, `Nom
enseignant`, `nom_enseignant` → `nom`). Une colonne absente de cette
liste n'est **jamais** associée par approximation : elle apparaît
telle quelle parmi les colonnes non reconnues, visible par
l'utilisateur.

## 5. Validation

- **Technique** : types (texte, nombre, entier), présence des champs
  obligatoires — via `utils/validators.py`.
- **Métier** : taux/montants non négatifs, sexe/statut valides,
  enseignant existant (pour heures/rémunérations/retenues), **respect
  strict du verrouillage des périodes du module 12** — testé
  explicitement sur les 4 statuts (BROUILLON, OUVERTE, VALIDEE,
  CLOTUREE) : seule OUVERTE autorise l'import.

## 6. Doublons

Détection interne au fichier (même nom/prénom apparaissant deux
fois) et contre la base (une seule requête pour tous les
enseignants existants, jamais une requête par ligne — section 26).
Trois stratégies explicites (`StrategieDoublon`) : REFUSER (défaut),
IGNORER, METTRE_A_JOUR — jamais d'écrasement silencieux.

## 7. Dry Run

`preparer_import_*` ne réalise **aucune écriture** : c'est la même
fonction utilisée pour la simulation et pour préparer l'import réel.
Vérifié par test : deux appels successifs sur le même fichier ne
laissent jamais aucune trace en base.

## 8. Import transactionnel et rollback

Une seule connexion SQLite (`get_connection`) pour l'ensemble des
lignes d'un import ; `COMMIT` uniquement si tout s'est déroulé sans
erreur inattendue, `ROLLBACK` complet sinon — **tout ou rien**,
jamais d'import partiel. Vérifié par test avec une panne simulée au
milieu d'un lot de 3 lignes : zéro ligne n'est restée en base après
le rollback.

Rendu possible par l'ajout **additif** d'un paramètre `conn` optionnel
à `enseignant_repository.creer`/`mettre_a_jour` (les repositories
heures/rémunération/retenues le supportaient déjà depuis les modules
antérieurs).

## 9. Rapport d'import

Table `imports` (compteurs) + `import_erreurs` (une ligne par
anomalie : ligne, champ, valeur, niveau, message) — additif au
schéma, migration idempotente (`CREATE TABLE IF NOT EXISTS`, même
convention que tous les modules précédents ; aucun dossier
`database/migrations/` distinct n'existait dans le projet — ce
module poursuit la convention déjà établie plutôt que d'en créer une
nouvelle).

## 10. Modèles téléchargeables

`exports/import_template_export.py` génère à la volée (jamais de
fichier statique à maintenir) un classeur par type d'import :
colonnes attendues, exemple, feuille Instructions. Génération
également disponible en CSV.

## 11. Permissions et audit

`import.donnees` (ADMIN + GESTIONNAIRE_PAIE, refusée à CONSULTATION)
— matrice centrale du module 11. `IMPORT_DONNEES` / `IMPORT_DONNEES_ECHEC`
déclenchés systématiquement (succès ou échec), incluant fichier,
type, compteurs et statut.

## 12. Sécurité fichiers

Le fichier téléversé est toujours réécrit sous un nom **généré par
l'application** (`tempfile.mkstemp`) — le nom fourni par l'utilisateur
n'est jamais utilisé pour construire un chemin, uniquement conservé
pour l'affichage et la traçabilité.

## 13. Sauvegarde

Aucun système de sauvegarde parallèle créé. Les tables `imports`/
`import_erreurs` sont des tables SQLite ordinaires, automatiquement
incluses dans `backup_service.creer_sauvegarde()` (module 10) comme
le reste de la base.

## 14. Limites connues

- L'import de rémunérations/retenues suit exactement le même
  pipeline que l'import d'heures (validation, verrouillage de
  période, transaction) mais dispose d'une couverture de tests un peu
  moins exhaustive que enseignants/heures, qui ont servi de
  démonstration complète du pipeline.
- Aucune limite de lignes explicite au-delà de la taille de fichier
  (10 Mo) — jugée suffisante pour l'usage d'un établissement scolaire.

## 15. Guide utilisateur

1. Télécharger le modèle (Excel ou CSV) depuis la page Importation.
2. Remplir le fichier avec les données à importer.
3. Le téléverser dans la page.
4. Vérifier les anomalies détectées (colonnes non reconnues, erreurs).
5. Lancer la simulation (Dry Run) pour voir l'effet prévu.
6. Corriger le fichier si nécessaire et relancer la simulation.
7. Confirmer explicitement l'import (résumé affiché, case à cocher).
8. Consulter le rapport et l'historique des imports.

## 16. Cas de référence

100 h × 2 000 FCFA → **Net = 208 250 FCFA**, vérifié après un import
d'enseignant réel suivi du workflow de paie complet.
