# Module 11 — Authentification, utilisateurs, rôles et permissions

## 1. Authentification

Écran de connexion (`utils/session_auth.py`, affiché depuis `app.py`
et depuis chaque page via `exiger_authentification()`/`exiger_permission()`) :
nom d'utilisateur + mot de passe. Message d'erreur générique unique
(« Nom d'utilisateur ou mot de passe incorrect. »), qu'il s'agisse d'un
nom d'utilisateur inconnu, d'un mot de passe erroné ou d'un compte
désactivé — aucune information n'est révélée à un attaquant.

Session stockée dans `st.session_state` : uniquement `authenticated`,
`user_id`, `username`, `nom_complet`, `role`, `derniere_activite`.
**Jamais** le mot de passe ni son hash.

Expiration de session après inactivité (`SESSION_TIMEOUT_SECONDES`,
2 heures par défaut, `config/settings.py`) : toute activité (chaque
page protégée visitée) prolonge la session ; en cas d'expiration, la
session est purgée et l'écran de connexion réapparaît.

## 2. Mots de passe

Hachés avec `hashlib.scrypt` (`utils/security.py`) — fonction de
dérivation de clé memory-hard, standard Python, aucune dépendance
externe. Format auto-descriptif (`scrypt$n$r$p$sel$hash`). Jamais MD5,
SHA1, ni SHA256 seul. Comparaison en temps constant
(`hmac.compare_digest`).

Politique (`services/utilisateur_service.py`) : longueur minimale
`PASSWORD_MIN_LENGTH` (8 caractères, `config/settings.py`), jamais
vide. Volontairement simple — pas de règle de complexité artificielle.

## 3. Rôles et permissions

Trois rôles (`models/enums.RoleUtilisateur`) : `ADMIN`,
`GESTIONNAIRE_PAIE`, `CONSULTATION`.

Matrice centralisée dans `services/permission_service.py`
(`a_permission(role, permission)`) — aucune condition `if role ==`
dispersée dans les pages. Une permission inconnue est toujours
refusée par défaut.

Point d'ambiguïté tranché : la matrice fournie laissait le choix pour
la clôture de période côté `GESTIONNAIRE_PAIE` (« Oui ou selon règle
existante »). La règle la plus restrictive a été conservée : la
clôture, opération irréversible, est réservée à `ADMIN`.

## 4. Protection des pages

`utils/session_auth.py` est le seul module qui connaît à la fois
Streamlit et l'authentification. Chaque page appelle
`exiger_permission(...)` (ou `exiger_authentification()`) tout en haut
du script, avant toute logique métier — empêche l'accès direct à une
page par son URL, puisque Streamlit ré-exécute intégralement le script
de la page à chaque navigation. Les boutons d'action sensibles
(modifier, supprimer, valider, clôturer, générer, exporter) sont en
plus individuellement vérifiés à l'intérieur des pages qui mélangent
plusieurs niveaux d'accès (ex. consultation + modification).

## 5. Protection côté service

La sécurité ne repose jamais uniquement sur l'interface. Les
protections métier déjà existantes (modules 08/09) restent
inchangées et actives indépendamment de la couche de permissions :
- `enseignant_service.supprimer_enseignant_definitivement` : bulletin
  bloquant, confirmation, transaction, audit, rollback — intacts.
- `periode_service.supprimer_periode_definitivement` : BROUILLON
  uniquement, bulletin bloquant, transaction, audit, rollback — intacts.

## 6. Administration des utilisateurs

`pages/10_Administration.py`, onglet **Utilisateurs** (réservé à
`ADMIN`) : création, modification (nom/prénom/rôle), activation/
désactivation, réinitialisation de mot de passe par un administrateur,
et changement de son propre mot de passe (exige l'ancien mot de
passe).

## 7. Initialisation du premier compte ADMIN

**Aucun mot de passe par défaut n'est jamais créé automatiquement.**
Tant qu'aucun utilisateur n'existe en base, `exiger_authentification()`
affiche un formulaire d'initialisation (nom, prénom, nom d'utilisateur,
mot de passe + confirmation) : c'est la personne ayant un accès
physique à l'application qui choisit elle-même les identifiants du
premier ADMIN. Ce compte est immédiatement utilisable (aucun
changement de mot de passe forcé n'est nécessaire, puisqu'aucune
valeur par défaut n'a jamais existé).

## 8. Protection du dernier ADMIN actif

`services/utilisateur_service.py` refuse toute désactivation ou tout
changement de rôle qui laisserait zéro ADMIN actif (`DernierAdminError`).
Un utilisateur désactivé reste conservé en base et dans
l'historique/audit — jamais supprimé.

## 9. Limitation des tentatives de connexion

`services/auth_service.py` : compteur en mémoire de processus
(`MAX_LOGIN_ATTEMPTS` = 5 tentatives, `LOGIN_LOCKOUT_SECONDES` = 60,
`config/settings.py`). Volontairement simple — pas de système
anti-bruteforce complexe, adapté à un usage local. Limite documentée :
réinitialisé si l'application redémarre.

## 10. Audit de sécurité

Réutilise intégralement l'audit métier existant
(`database/repositories/audit_log_repository.py`), désormais alimenté
avec le champ `utilisateur` (déjà prévu depuis le module 01, jamais
utilisé jusqu'ici). Nouveaux types d'action (additifs) :
`connexion_reussie`, `connexion_echouee`, `deconnexion`,
`utilisateur_cree`, `utilisateur_modifie`, `utilisateur_desactive`,
`utilisateur_active`, `mot_de_passe_modifie`,
`mot_de_passe_reinitialise`, `role_modifie`. Le mot de passe n'est
jamais journalisé, ni en cas de succès ni en cas d'échec.

## 11. Base de données

Migration additive (`database/schema.sql`) : table `utilisateurs`
(`id, nom, prenom, username UNIQUE, password_hash, role CHECK,
actif CHECK, date_creation, date_modification, derniere_connexion`),
trigger de mise à jour automatique de `date_modification` (même
convention que `enseignants`), index sur `username`. Extension de la
contrainte CHECK de `audit_log.type_action`. Aucune table existante
modifiée destructivement.

## 12. Diagnostic (module 10)

`services/diagnostic_service.py` affiche désormais le nombre
d'utilisateurs, d'utilisateurs actifs et d'administrateurs actifs
(jamais de mot de passe ni de hash). L'état global passe à 🔴 Rouge
si des utilisateurs existent mais qu'aucun ADMIN actif n'est détecté
(ne devrait normalement jamais se produire, protégé en amont).

## 13. Sauvegarde/restauration (module 10)

Aucune modification nécessaire : les utilisateurs vivent dans la même
base SQLite que le reste des données, donc automatiquement inclus par
`services/backup_service.py`. Vérifié explicitement par test.

## 14. Procédure de première connexion

1. Lancer `streamlit run app.py`.
2. Aucun utilisateur n'existe encore → le formulaire d'initialisation
   s'affiche automatiquement.
3. Renseigner nom, prénom, nom d'utilisateur, mot de passe (8
   caractères minimum) et sa confirmation.
4. Se connecter avec ces identifiants — le compte créé est ADMIN.
5. Depuis Administration → Utilisateurs, créer les comptes
   `GESTIONNAIRE_PAIE`/`CONSULTATION` nécessaires.
