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

Onglet **Diagnostic** : état global en toutes lettres, accessibilité et intégrité de la base, présence des tables, nombre d'enseignants, de périodes, de bulletins et d'entrées d'audit, taille des exports, sauvegardes disponibles, présence du modèle Word standard, nombre de bulletins Word et PDF, comptes et administrateurs actifs, registre des documents (documents manquants).

Onglet **Maintenance** : **Lancer les vérifications** produit un tableau « Conforme / Échec » des contrôles essentiels, sans rien modifier.

Onglet **Journaux** : dernières lignes du journal technique, avec recherche. Ce journal est distinct du journal d'audit.

## 7. Taux de taxe

Onglet **Paramètres**, rubrique **Paramètres de paie**.

- **Taux par défaut** : saisissez le taux en pourcentage (par exemple `5,5` pour 5 % d'impôt et 10 % de centimes additionnels), puis **Enregistrer le taux**. Tant qu'il n'a jamais été modifié, il vaut 5 %. Il est recopié sur chaque période créée ensuite ; il ne modifie aucune période existante.
- **Appliquer aussi aux périodes en brouillon ou ouvertes** : case à cocher du même formulaire ; les périodes validées ou clôturées ne sont jamais touchées.
- **Taux d'une période** : page **Gestion › Périodes de paie**, période sélectionnée, **Appliquer ce taux à la période** (brouillon ou ouverte uniquement).
- **Figé à la validation** : une fois la période validée, son taux ne peut plus changer, ni depuis l'interface ni par une modification directe de la base (règle de protection SQL). Un bulletin validé ou clôturé est donc toujours recalculé à l'identique.

Le taux est saisi entre 0 et 50 %, avec au plus deux décimales. Chaque modification (taux par défaut ou taux d'une période) est inscrite au journal d'audit avec l'ancien et le nouveau taux. Seul un administrateur peut modifier un taux ; la vérification est faite par le service, pas seulement par l'interface.

## 8. Modèles de bulletin

Onglet **Modèles de bulletin**.

**Modèles standard** : « Bulletin officiel » en Word (.docx) et en PDF. Ils reproduisent le bulletin de solde officiel de l'établissement : en-tête bilingue avec le logo, bande verte « BULLETIN DE SOLDE / PAYSLIP » et mois en anglais, bande jaune nom / statut, rubriques 1 à 7 (gain heures avec heures, taux et montant ; prime AP/PP ; surveillance/secrétariat ; indemnité ; taxe ; retenue amicale ; dette), lignes Total et NET A PAYER (en chiffres et en lettres), « Fait à Yaoundé le : » et titre du signataire. Les montants sont écrits sans séparateur de milliers, comme sur l'original. Tant qu'aucun choix n'a été fait, le modèle actif est le modèle Word standard.

L'en-tête réel (région, délégations, nom de l'établissement) et le logo ne sont pas livrés avec l'application : ils sont décrits dans `config/etablissement_local.py` (à créer à partir de `config/etablissement_local.example.py`, logo dans `assets/logo_etablissement.png`). La commande `python templates/build_template.py --etablissement --pdf` produit alors les modèles de l'établissement dans le dossier `modeles_etablissement` du dossier de données ; l'application les utilise à la place des modèles neutres (« NOM DE L'ETABLISSEMENT ») livrés dans `templates/`.

**Activer un modèle** : choisissez-le puis **Activer ce modèle**. Les bulletins générés ensuite sont produits dans son format (Word ou PDF). Les fichiers déjà produits ne sont pas modifiés. **Produire un bulletin d'essai** crée un bulletin rempli de valeurs d'exemple, affiché en image pour un PDF et téléchargeable dans tous les cas.

**Ajouter un modèle** (Word .docx ou PDF, 10 Mo maximum) :

1. *Bulletin déjà rempli* — par exemple un bulletin d'un mois précédent exporté en PDF depuis Excel. L'application repère les textes du document et propose, pour chacun, le champ correspondant (nom, période, statut, heures, taux, montants, totaux, net en chiffres et en lettres) à partir des intitulés de la même ligne. Vérifiez la colonne **Champ**, corrigez si besoin (choisissez « texte fixe » pour un texte à conserver tel quel) et, pour un PDF, l'alignement de chaque valeur. Le nom et le net à payer sont obligatoires.
2. *Modèle à balises* — un document où chaque valeur variable est remplacée par une balise, par exemple `{{NOM_COMPLET}}`, `{{PERIODE}}`, `{{NET_A_PAYER}}`. La liste complète est affichée dans l'onglet. Dans un PDF, `{{NET_A_PAYER|centre}}` ou `|droite` règle l'alignement ; une balise doit tenir sur une seule ligne. Le modèle Word standard, téléchargeable depuis l'onglet, sert de point de départ.

Avant tout enregistrement, **Produire un bulletin d'essai** montre le résultat ; **Enregistrer le modèle** refait l'essai et n'enregistre rien s'il échoue. Un PDF numérisé (image sans texte) est refusé : exportez le bulletin en PDF depuis Excel ou Word.

Dans un modèle PDF, les textes remplacés sont réellement effacés puis réécrits dans la même police (famille, taille, graisse, couleur), sur la même ligne ; le fond, les traits, le logo et les textes fixes restent inchangés. Les polices utilisées pour les valeurs sont les polices standard du PDF (Times ou Helvetica).

Le modèle enregistré ne conserve pas les valeurs du bulletin envoyé : dans un PDF, elles sont effacées ; dans un document Word, elles sont remplacées par des balises. Seuls les textes laissés en « texte fixe » restent tels quels.

Les modèles importés sont conservés dans le dossier `modeles_bulletin` du dossier de données ; chaque sauvegarde de la base en emporte une copie, remise en place à la restauration. Un modèle actif ne peut pas être supprimé ; les modèles standard ne peuvent pas l'être. Si le fichier du modèle actif disparaît, les bulletins sont produits avec le modèle Word standard. Import, activation et suppression sont inscrits au journal d'audit.

## 9. Réinitialisation des données

Onglet **Réinitialisation des données**. Cette opération est distincte de la gestion des comptes : **elle ne supprime, ne modifie et ne réinitialise aucun compte utilisateur**.

**Supprimé** : enseignants, périodes, heures, primes et indemnités, retenues, bulletins, registre des documents, fichiers générés (dossier des exports : bulletins, états Excel, archives, packs), journaux d'importation et leurs erreurs, alertes.

**Conservé à l'identique** : table des comptes (noms d'utilisateur, empreintes de mots de passe, rôles, statuts, dates), permissions, sessions ouvertes, journal d'audit complet (connexions, gestion des comptes, restaurations, réinitialisations, mais aussi calculs, validations et exports : l'historique de ce qui a été fait n'est jamais effacé), paramètres de l'établissement, sauvegardes, journaux techniques, taux de taxe par défaut, modèles de bulletin et modèle actif, schéma de la base et ses règles de protection.

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

## 10. Maintenance

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
