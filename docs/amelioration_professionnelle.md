# Amélioration professionnelle — notes techniques

Intervention sur la version existante : aucun nouveau module, aucune formule de paie modifiée, aucune fonctionnalité retirée. Le cas de référence (100 h × 2 000 FCFA, primes 35 000, retenues 15 000 → net 208 250 FCFA) est vérifié par les tests existants et par `tests/test_reinitialisation_donnees.py`.

## 1. Réinitialisation des données métier

Fichier : `services/reinitialisation_service.py` ; interface : Administration › Réinitialisation des données.

Périmètre établi à partir du schéma réel (`database/schema.sql`) :

| Supprimé | Conservé |
|---|---|
| `alertes`, `import_erreurs`, `imports`, `documents`, `bulletins_paie`, `saisies_heures`, `elements_remuneration`, `retenues`, `periodes_paie`, `enseignants` | `utilisateurs` (strictement identique, vérifié par empreinte) |
| entrées d'`audit_log` décrivant ces objets (historique métier) | entrées d'`audit_log` de sécurité : connexions, gestion des comptes, restaurations, réinitialisations |
| contenu du dossier des exports (bulletins, états Excel, archives, packs) | paramètres de l'établissement, sauvegardes, journaux techniques, modèle de bulletin |

Aucune table de paramètres n'existe en base : la configuration est dans `config/settings.py` et `parametres_etablissement.json`, non touchés. Les séquences d'identifiants (`sqlite_sequence`) sont conservées : un nouvel enseignant ou une nouvelle période ne reprend jamais l'identifiant d'un objet supprimé.

Un test (`test_toute_table_du_schema_est_classee`) échoue si une table est ajoutée au schéma sans être classée dans l'une des deux colonnes.

Ordre d'exécution : autorisation relue en base (ADMIN actif) → case de confirmation et phrase `RÉINITIALISER` → contrôle d'intégrité préalable → sauvegarde complète `Avant_Reinitialisation_<date>.zip` (+ `avant_reinitialisation_<date>.db`, restaurable depuis l'onglet Restauration) → mise à l'écart réversible des fichiers → transaction unique (`BEGIN IMMEDIATE`) : suppression temporaire des déclencheurs bloquant les suppressions, suppressions dans l'ordre des dépendances, recréation des déclencheurs à l'identique, vérifications (tables vides, comptes identiques, déclencheurs rétablis, `foreign_key_check`, `integrity_check`), écriture de l'audit, `COMMIT` → vérification finale sur une connexion neuve, restauration automatique de la sauvegarde en cas d'échec.

Nouveaux types d'audit : `reinitialisation_donnees` et `reinitialisation_donnees_echec`, ajoutés à l'énumération et à la contrainte CHECK du schéma ; les bases existantes sont migrées automatiquement au démarrage (`database/migrations.py`, inchangé). Vérifié sur une copie de la base de l'utilisateur : migration effectuée, compte et 25 entrées d'audit conservés.

## 2. Séparation administrateur / autres rôles côté service

- `services/autorisation_service.py` : `exiger_permission_utilisateur(utilisateur_id, permission)` relit le compte en base (existence, statut actif, rôle) au moment de l'opération.
- `services/administration_service.py` : façade des opérations sensibles (comptes, mots de passe, sauvegarde, restauration, paramètres, diagnostic, suppressions définitives), chacune protégée par ce contrôle. Les pages n'appellent plus les fonctions de bas niveau correspondantes (contrôle statique dans `tests/test_separation_privileges.py`).
- Nouvelles protections : un administrateur ne peut ni modifier son propre rôle ni désactiver son propre compte ; les opérations sur les comptes sont désormais journalisées (les valeurs d'audit existaient mais n'étaient pas utilisées), sans mot de passe ni empreinte.
- Matrice inchangée pour les permissions existantes ; ajout de `DONNEES_REINITIALISER` (ADMIN uniquement) et `DOCUMENTATION_CONSULTER` (tous les rôles).

## 3. Interface

- Emojis retirés de tous les libellés, titres, boutons, noms de blocs et des mentions d'avertissement des états Excel générés. Icônes de navigation issues de la bibliothèque Material Symbols fournie par Streamlit.
- Écran de présentation réécrit : texte factuel, plus de dégradé, de slogan ni de cartes décoratives ; accès à la politique de confidentialité et aux conditions d'utilisation avant connexion.
- Thème : bleu institutionnel `#1F3A6E`, gris neutres, angles de 4 px, bouton « Deploy » masqué, liens d'aide externes masqués sous les erreurs. Badges d'état à 3 px d'arrondi, bordure et libellé textuel, contraste supérieur à 6:1. Légendes en gris foncé (contraste 7,5:1). Contour de focus clavier visible.
- Favicon (`assets/favicon.png`, `assets/favicon.ico`) et logo (`assets/logo_horizontal.png`, `assets/logo_symbole.png`) : symbole d'édifice institutionnel généré pour l'application, sans emoji. Utilisés dans l'onglet du navigateur, la barre latérale, l'écran de présentation et l'exécutable (`GestionPaie.spec`).
- Messages « Aucune donnée disponible. » sur les états vides ; le tableau de bord n'affiche plus de cartes à zéro lorsqu'aucun enseignant n'existe.
- Adresses de pages stables (`/enseignants`, `/calcul-paie`...).
- Correction d'un défaut existant : les liens « Aller au contrôle de la paie » (pages Périodes et Cycle de paie) pointaient encore vers l'ancien dossier `pages/`.

## 4. Documentation intégrée

`docs/guide_utilisateur.md` (15 sections), `docs/guide_administrateur.md`, `docs/politique_confidentialite.md`, `docs/conditions_utilisation.md`, affichés par les pages 18 à 21 (dans les blocs existants). Les textes juridiques contiennent des mentions à compléter entre crochets et signalent la validation juridique nécessaire. Un test vérifie que les valeurs citées (8 caractères, 5 tentatives, 2 heures, 5 %, 10 Mo...) correspondent à la configuration.

## 5. Tests modifiés

`tests/test_navigation.py` : noms de blocs sans emoji et prise en compte des 4 pages de documentation ajoutées dans les blocs (les 17 pages fonctionnelles restent vérifiées). Aucun test supprimé ni désactivé.
