# Guide administrateur

Ce guide décrit les opérations réservées au rôle **Administrateur** : gestion des comptes, rôles et permissions, sauvegarde, restauration, diagnostics, réinitialisation des données et maintenance. Toutes ces opérations se trouvent dans **Administration & Sécurité › Administration**.

Les droits sont vérifiés deux fois : par la page (qui n'affiche pas les fonctions interdites) et par le service qui exécute l'opération, qui relit le rôle du compte dans la base au moment de l'action. Un compte désactivé ou rétrogradé perd donc immédiatement ses droits, même si sa session était ouverte.

## 1. Gestion des comptes

Onglet **Utilisateurs**.

- **Créer un compte** : nom, prénom, nom d'utilisateur (unique, sans distinction de majuscules), rôle, mot de passe de 8 caractères minimum saisi deux fois. Le mot de passe est enregistré sous forme d'empreinte (algorithme scrypt) ; il n'est jamais stocké ni journalisé en clair.
- **Modifier un compte** : nom, prénom et rôle. Le nom d'utilisateur n'est pas modifiable.
- **Activer ou désactiver** : un compte désactivé ne peut plus se connecter ; il reste enregistré avec son historique.
- **Réinitialiser un mot de passe** : définit un nouveau mot de passe sans connaître l'ancien. Communiquez-le à l'utilisateur par un moyen sûr.
- **Changer mon mot de passe** : l'ancien mot de passe est demandé.

Règles de protection :

- l'application conserve toujours au moins un administrateur actif : la désactivation ou la rétrogradation du dernier administrateur actif est refusée ;
- un administrateur ne peut ni modifier son propre rôle ni désactiver son propre compte : ces opérations doivent être faites par un autre administrateur ;
- chaque opération sur un compte (création, modification, changement de rôle, activation, désactivation, réinitialisation ou changement de mot de passe) est enregistrée dans le journal d'audit avec son auteur et sa date, sans aucun mot de passe ni empreinte.

## 2. Rôles

| Rôle | Portée |
|---|---|
| Administrateur | Toutes les fonctions. Seul rôle autorisé à gérer les comptes et les rôles, sauvegarder, restaurer, consulter les diagnostics et les journaux, modifier les paramètres de l'établissement, supprimer définitivement un enseignant ou une période, clôturer une période et réinitialiser les données. |
| Gestionnaire de paie | Opérations de paie courantes : enseignants, périodes (création, ouverture), saisie, calcul, contrôle, validation, bulletins, exports, documents, importation, automatisation, notifications. |
| Consultation | Lecture seule des données autorisées ; aucune modification, aucune génération de bulletin ni d'état comptable. |

## 3. Permissions

Les permissions sont définies à un seul endroit, la matrice de `services/permission_service.py`. La page **Guide administrateur** affiche, sous ce texte, la matrice réellement appliquée par l'application, générée à partir de cette configuration. Une permission absente de la matrice est toujours refusée.

La modification de la matrice est une opération de maintenance du logiciel (modification du code) et non une opération de l'interface.

## 4. Sauvegarde

Onglet **Sauvegarde** : **Créer une sauvegarde maintenant** produit une copie cohérente de la base (`backup_<date>.db`) dans le dossier des sauvegardes, affiché sur la page. La liste indique la date, la taille et l'emplacement de chaque sauvegarde.

Des sauvegardes sont aussi créées automatiquement :

- avant une restauration (`avant_restauration_<date>.db`) ;
- avant une réinitialisation des données (`avant_reinitialisation_<date>.db`, et `Avant_Reinitialisation_<date>.zip` qui contient aussi les fichiers générés).

L'application ne supprime jamais de sauvegarde. Copiez régulièrement le dossier des sauvegardes sur un support externe : une sauvegarde conservée sur le même disque ne protège pas contre la perte de ce disque.

## 5. Restauration

Onglet **Restauration** :

1. choisissez une sauvegarde ; son intégrité est vérifiée et le résultat affiché en toutes lettres ;
2. cliquez sur **Restaurer cette sauvegarde**, saisissez `JE CONFIRME CETTE OPÉRATION`, puis **Confirmer la restauration** ;
3. une sauvegarde de sécurité de la base actuelle est créée, puis la base est remplacée ;
4. si la base restaurée est invalide, l'état précédent est rétabli automatiquement.

Toute restauration est enregistrée dans le journal d'audit. Les comptes présents dans la base restaurée sont ceux qui existaient au moment de la sauvegarde.

## 6. Diagnostics

Onglet **Diagnostic** : état global en toutes lettres, accessibilité et intégrité de la base, présence des tables, nombre d'enseignants, de périodes, de bulletins et d'entrées d'audit, taille des exports, sauvegardes disponibles, présence du modèle de bulletin, comptes et administrateurs actifs, registre des documents (documents manquants).

Onglet **Maintenance** : **Lancer les vérifications** produit un tableau « Conforme / Échec » des contrôles essentiels, sans rien modifier.

Onglet **Journaux** : dernières lignes du journal technique, avec recherche. Ce journal est distinct du journal d'audit.

## 7. Réinitialisation des données

Onglet **Réinitialisation des données**. Cette opération est distincte de la gestion des comptes : **elle ne supprime, ne modifie et ne réinitialise aucun compte utilisateur**.

**Supprimé** : enseignants, périodes, heures, primes et indemnités, retenues, bulletins, registre des documents, fichiers générés (dossier des exports : bulletins, états Excel, archives, packs), journaux d'importation et leurs erreurs, alertes, et entrées du journal d'audit relatives à ces données.

**Conservé à l'identique** : table des comptes (noms d'utilisateur, empreintes de mots de passe, rôles, statuts, dates), permissions, sessions ouvertes, entrées d'audit de sécurité (connexions, gestion des comptes, restaurations, réinitialisations), paramètres de l'établissement, sauvegardes, journaux techniques, modèle de bulletin, schéma de la base et ses règles de protection.

Déroulement :

1. l'onglet affiche la liste chiffrée de ce qui sera supprimé et conservé ;
2. l'administrateur coche la case de confirmation et saisit `RÉINITIALISER` (ou `REINITIALISER`) ;
3. le service vérifie que le compte qui agit est un administrateur actif ; toute tentative refusée est journalisée ;
4. l'intégrité de la base est contrôlée, puis une sauvegarde complète est créée ; si elle échoue, rien n'est supprimé ;
5. les fichiers générés sont mis à l'écart, puis les données sont supprimées dans une transaction unique ;
6. avant validation, l'application vérifie que les tables métier sont vides, que la table des comptes est strictement identique, que les règles de protection de la base sont rétablies, que les clés étrangères et l'intégrité SQLite sont correctes ; sinon tout est annulé ;
7. après validation, une vérification finale est faite ; en cas d'échec, la sauvegarde est restaurée automatiquement ;
8. le résultat (auteur, date, sauvegarde utilisée, nombre d'éléments supprimés par catégorie, nombre de comptes conservés) est enregistré dans le journal d'audit et affiché.

Pour revenir à l'état antérieur, restaurez `avant_reinitialisation_<date>.db` depuis l'onglet Restauration. Les fichiers générés se trouvent dans l'archive `Avant_Reinitialisation_<date>.zip`, dossier `documents/`.

## 8. Maintenance

- Consultez régulièrement **Notifications** : les alertes signalent notamment une sauvegarde absente ou ancienne et des documents manquants ou modifiés.
- Consultez **Diagnostic** en cas de doute ; un état « problème détecté » doit être traité avant toute nouvelle opération de paie.
- Emplacement des données : en développement, dossier `data/` du projet ; sous Windows, dossier `data\` placé à côté de `GestionPaie.exe` s'il existe, sinon `%APPDATA%\GestionPaie\`. Les emplacements exacts sont affichés dans **Paramètres › Emplacements de stockage**.
- Protégez l'accès physique et le compte système du poste qui héberge l'application : la base de données n'est pas chiffrée par l'application.

### Réinitialisation complète des comptes (hors interface)

À ne pas confondre avec la réinitialisation des données. Pour ramener une installation à l'état « première configuration » en conservant toutes les données métier, un administrateur technique peut exécuter :

```python
from services import utilisateur_service
utilisateur_service.reinitialiser_tous_les_comptes(confirmation=True)
```

Tous les comptes sont supprimés ; les données métier et le journal d'audit sont conservés ; toute session ouverte devient invalide. Cette fonction n'est volontairement accessible par aucun bouton de l'interface.
