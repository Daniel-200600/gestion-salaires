# Guide utilisateur

Ce guide décrit l'utilisation courante du logiciel **Gestion des Salaires** : enregistrement des enseignants, préparation d'une période de paie, saisie, calcul, contrôle, édition des bulletins et des états, puis clôture. Il s'adresse à toute personne disposant d'un compte, sans connaissance technique préalable.

Les pages et boutons visibles dépendent de votre rôle. Si une fonction décrite ici n'apparaît pas dans votre barre latérale, votre rôle ne vous y donne pas accès : adressez-vous à un administrateur.

| Rôle | Ce que le rôle permet |
|---|---|
| Administrateur | Toutes les fonctions, y compris la gestion des comptes, les sauvegardes, la restauration, les suppressions définitives, la clôture des périodes et la réinitialisation des données. |
| Gestionnaire de paie | Enseignants, périodes, saisie, calcul, contrôle, validation, bulletins, exports, documents, importation, automatisation et notifications. Pas d'administration, pas de suppression définitive, pas de clôture. |
| Consultation | Lecture seule : tableau de bord, enseignants, périodes, calcul, contrôle, bulletins, historique, rapports, statistiques, documents et notifications. Aucune modification. |

## 1. Première connexion

**Création du premier administrateur.** Lors du tout premier lancement, aucun compte n'existe. Après l'écran de présentation, cliquez sur **Continuer vers la connexion** : le formulaire **Première configuration** s'affiche. Renseignez le nom, le prénom, le nom d'utilisateur, le mot de passe (8 caractères minimum) et sa confirmation, puis cliquez sur **Créer le compte administrateur**. Aucun mot de passe n'est fourni par défaut : conservez celui que vous choisissez.

**Connexion.** Saisissez votre nom d'utilisateur et votre mot de passe, puis cliquez sur **Se connecter**. Après cinq tentatives infructueuses, la connexion est temporairement bloquée pendant une minute. Le message d'erreur ne précise volontairement pas si c'est le nom d'utilisateur ou le mot de passe qui est incorrect.

**Déconnexion.** Cliquez sur **Se déconnecter** dans la barre latérale. Sans activité pendant deux heures, la session expire et une nouvelle connexion est demandée. Si un administrateur désactive votre compte ou modifie votre rôle, la modification s'applique dès la page suivante.

**Mot de passe oublié.** Un administrateur peut définir un nouveau mot de passe pour votre compte (Administration › Utilisateurs › Réinitialiser le mot de passe).

## 2. Navigation

La barre latérale regroupe les pages en sept blocs. Chaque page possède une adresse fixe (par exemple `/enseignants`), ce qui permet d'y revenir directement.

| Bloc | Pages |
|---|---|
| Tableau de bord | Tableau de bord, Guide utilisateur, Politique de confidentialité, Conditions d'utilisation |
| Gestion | Enseignants, Périodes de paie |
| Paie | Données de paie, Calcul de paie, Cycle de paie, Bulletins de solde, Génération comptable |
| Contrôle & Historique | Contrôle de la paie, Historique de paie |
| Analyse & Rapports | Rapports comptables, Statistiques |
| Documents & Opérations | Gestion des documents, Importation, Notifications, Automatisation |
| Administration & Sécurité | Administration, Guide administrateur (administrateurs uniquement) |

Le **Tableau de bord** affiche le nombre d'enseignants, les indicateurs de paie de la période choisie, les alertes actives et l'évolution de la masse salariale. Lorsqu'aucune donnée n'existe, la mention « Aucune donnée disponible. » s'affiche à la place des indicateurs.

## 3. Gestion des enseignants

Page **Gestion › Enseignants**.

- **Création** : ouvrez **Ajouter un enseignant**, renseignez le nom, le prénom, le sexe, le statut (permanent ou vacataire) et le taux horaire en FCFA, puis cliquez sur **Enregistrer l'enseignant**. Les champs marqués d'un astérisque sont obligatoires.
- **Recherche et liste** : la liste peut être filtrée par un terme de recherche ; les enseignants désactivés peuvent être affichés ou masqués.
- **Modification** : sélectionnez l'enseignant dans **Actions sur un enseignant**, onglet **Modifier**. Le taux horaire enregistré sur la fiche est celui utilisé par les calculs ; les bulletins déjà figés d'une période validée ou clôturée conservent les montants de leur génération.
- **Changement de statut** : onglet **Changer le statut**. Choisissez le nouveau statut (vacataire ou permanent), cochez la case de confirmation puis cliquez sur **Changer le statut**. Le nouveau statut s'applique aux calculs et aux bulletins produits à partir de ce moment ; un bulletin déjà émis pour une période validée ou clôturée garde le statut qu'il portait. Chaque changement est inscrit au journal d'audit.
- **Désactivation** : onglet **Activer / Désactiver**. Un enseignant désactivé n'est plus proposé pour la saisie des données de paie ; son historique est conservé et il peut être réactivé.
- **Suppression définitive** (administrateurs uniquement) : onglet **Supprimer définitivement**. La suppression est refusée si au moins un bulletin existe pour cet enseignant. Sinon, l'application affiche les données liées (heures, primes, retenues) qui seront supprimées avec lui et demande de saisir exactement le nom complet de l'enseignant pour confirmer.

## 4. Gestion des périodes

Page **Gestion › Périodes de paie**. Une période correspond à un mois de paie et suit toujours le même ordre : **Brouillon → Ouverte → Validée → Clôturée**. Un retour en arrière n'est pas possible.

- **Création** : ouvrez **Créer une période**, choisissez le mois et l'année, puis cliquez sur **Créer la période**. Une seule période peut exister pour un même mois et une même année. Tant qu'elle est au statut Brouillon, son mois et son année peuvent être corrigés.
- **Ouverture** : **Ouvrir cette période**. La saisie des heures, primes, indemnités et retenues n'est possible que sur une période ouverte.
- **Validation** : depuis **Contrôle & Historique › Contrôle de la paie** (voir section 8). La validation gèle les données de paie.
- **Clôture** : depuis la même page, par un administrateur. Une période clôturée ne peut plus être modifiée ni supprimée.
- **Suppression définitive** (administrateurs uniquement) : possible uniquement pour une période au statut Brouillon et sans bulletin.
- **Taux de taxe** : chaque période porte son propre taux de taxe, affiché dans la liste. À la création, elle reçoit le taux par défaut réglé par l'administrateur (section 14). Tant que la période est en brouillon ou ouverte, un administrateur peut l'ajuster (**Appliquer ce taux à la période**) ; dès la validation, il est figé.

La page **Paie › Cycle de paie** affiche l'étape actuelle de la période, sa progression et l'historique de ses changements de statut.

## 5. Saisie de la paie

Page **Paie › Données de paie** (administrateurs et gestionnaires de paie). Choisissez la période : si elle n'est pas ouverte, les données sont affichées en lecture seule.

Pour chaque enseignant :

- **Heures** : nombre d'heures effectuées pour chacune des cinq semaines de la période.
- **Taux** : le taux horaire provient de la fiche de l'enseignant (section 3) ; il n'est pas saisi ici.
- **Primes et indemnités** : prime AP/PP, surveillance et secrétariat, indemnité de suggestion administrative, en FCFA.
- **Retenues** : retenue amicale et dette, en FCFA.

Cliquez sur **Enregistrer les données de paie**. L'enregistrement est global : si une valeur est invalide, aucune donnée n'est enregistrée et le message indique la cause.

L'importation d'un fichier Excel ou CSV permet aussi de saisir ces données en nombre (section 11).

## 6. Calcul

Page **Paie › Calcul de paie**. Choisissez la période puis cliquez sur **Lancer le calcul**. Le calcul est une prévisualisation : il ne génère aucun bulletin et ne modifie aucune donnée.

Le montant net est obtenu ainsi :

1. gain horaire = total des heures × taux horaire ;
2. base taxable = gain horaire + primes et indemnités ;
3. taxe = base taxable × taux de taxe de la période (5 % par défaut) ;
4. net à percevoir = base taxable − taxe − retenues.

Exemple au taux de 5 % : 100 heures à 2 000 FCFA, 35 000 FCFA de primes et indemnités, 15 000 FCFA de retenues donnent une base taxable de 235 000 FCFA, une taxe de 11 750 FCFA et un net de 208 250 FCFA.

Exemple au taux de 5,5 % : 10 heures à 1 800 FCFA donnent 18 000 FCFA, une taxe de 990 FCFA et un net de 17 010 FCFA. Les montants sont arrondis au franc le plus proche.

**Contrôle du résultat** : comparez les totaux affichés avec les données saisies, puis utilisez la page Contrôle de la paie (section 8) avant toute validation.

## 7. Bulletins

Page **Paie › Bulletins de solde**.

- **Génération** : choisissez la période, puis les enseignants (tous ou une sélection), vérifiez la prévisualisation et cliquez sur **Générer les bulletins**. Sur une période encore ouverte, les bulletins sont provisoires. Les anomalies bloquantes détectées sur la sélection sont signalées avant la génération.
- **Consultation** : chaque bulletin reproduit le bulletin officiel de l'établissement (en-tête bilingue et logo, bandes vertes et jaune, rubriques numérotées de 1 à 7, total, net à payer en chiffres et en lettres, zone « Fait à Yaoundé le : » laissée vierge pour la date et la signature). Il est produit au format du modèle actif, Word (.docx) ou PDF, choisi par l'administrateur (section 14). Le nom du modèle utilisé est rappelé en haut de la page. Les bulletins sont enregistrés dans le registre des documents (section 10).
- **Export** : téléchargez un bulletin individuel ou l'archive ZIP de tous les bulletins générés.

Pour une période clôturée, un bulletin déjà existant n'est jamais régénéré ni écrasé.

## 8. Contrôle

Page **Contrôle & Historique › Contrôle de la paie**.

- **Anomalies** : la page liste les erreurs bloquantes (par exemple heures négatives, taux horaire invalide, montant négatif, total d'heures incohérent) et les avertissements à examiner (par exemple volume d'heures élevé, dette ou retenue élevée). Chaque ligne indique son niveau en toutes lettres.
- **Validation** : **Valider cette période**, puis **Confirmer la validation**. La validation est refusée tant qu'une erreur bloquante subsiste.
- **Clôture** (administrateurs) : **Clôturer cette période**, puis **Confirmer la clôture**. La clôture est définitive.

La page **Historique de paie** présente, pour un enseignant, les montants de chaque période et permet de comparer deux périodes.

## 9. Rapports et statistiques

- **Consultation** : **Analyse & Rapports › Rapports comptables** présente l'état général de la période, le détail par enseignant, le classement, les synthèses par groupe, l'état des retenues, le rapprochement et la comparaison entre périodes. **Statistiques** présente la vue générale, les heures, les rémunérations, les groupes, l'évolution dans le temps, les composantes, les valeurs atypiques et l'analyse individuelle.
- **Filtres** : période, statut (permanent ou vacataire) et sexe ; critère et ordre de classement ; période de comparaison. Si aucun enregistrement ne correspond, la page l'indique.
- **Exports** : **Générer l'état de paie Excel** (rapports) et **Générer l'export Excel** (statistiques), puis téléchargez le fichier produit. Les montants exportés sont ceux du moteur de calcul, sans recalcul.

## 10. Documents

Page **Documents & Opérations › Gestion des documents**.

- **Gestion** : recherchez un document généré (bulletin, état comptable, rapport) par période, enseignant, type de document ou nom de fichier, puis téléchargez-le.
- **Intégrité** : **Vérifier l'intégrité maintenant** compare chaque fichier avec l'empreinte enregistrée lors de sa génération. Chaque document est qualifié en toutes lettres : Valide, Manquant, Modifié ou Orphelin.
- **Archivage** : pour une période clôturée, **Archiver cette période** produit une archive ZIP de ses documents, téléchargeable.

## 11. Importation

Page **Documents & Opérations › Importation** (administrateurs et gestionnaires de paie). La procédure est découpée en huit étapes numérotées.

- **Fichiers acceptés** : Excel (.xlsx) ou CSV (.csv), 10 Mo au maximum. Types d'import : enseignants, heures, rémunérations, retenues. Téléchargez d'abord le modèle Excel ou CSV correspondant au type choisi.
- **Prévisualisation** : après l'analyse du fichier, chaque ligne est présentée avec l'action prévue (création, mise à jour, ligne ignorée ou rejetée) et ses éventuelles erreurs.
- **Validation** : **Lancer la simulation** montre le résultat sans rien enregistrer. **Confirmer et importer** enregistre ensuite les données.
- **Rollback** : l'import est exécuté en une seule opération. Si une erreur survient, rien n'est enregistré et le rapport indique « ÉCHEC (annulé intégralement) ». L'historique des imports reste consultable.

## 12. Automatisation

Page **Documents & Opérations › Automatisation** (administrateurs et gestionnaires de paie).

- **Génération groupée** : après vérification des préconditions, **Simuler** affiche ce qui serait produit, sans écriture. **Générer les bulletins** produit les bulletins de tous les enseignants concernés. **Reprendre uniquement les erreurs** relance les seuls bulletins en échec.
- **Exports** : **Vérifier l'intégrité des documents de cette période**, **Créer l'archive de cette période** (période clôturée) et **Créer le pack de paie** (archive ZIP regroupant les documents déjà enregistrés pour la période, avec un inventaire), chacun téléchargeable.

## 13. Notifications

Page **Documents & Opérations › Notifications**. Les alertes signalent un point à traiter : anomalie de paie, document manquant ou modifié, sauvegarde absente ou ancienne, problème d'import. Chaque alerte indique son niveau en toutes lettres (Critique, Erreur, Avertissement, Info).

- **Consultation** : **Analyser maintenant** relance les détections. Filtrez par niveau, statut, période, enseignant ou texte recherché ; exportez la liste filtrée au format Excel.
- **Acquittement** : **Marquer lue** puis **Acquitter** indiquent que l'alerte a été prise en compte.
- **Résolution** : **Résoudre** lorsque la cause est corrigée, ou **Ignorer** lorsque l'alerte ne nécessite pas d'action. Une anomalie corrigée est aussi résolue automatiquement lors de l'analyse suivante.

## 14. Administration

Page **Administration & Sécurité › Administration**, réservée aux administrateurs. Le **Guide administrateur** détaille chaque opération.

- **Utilisateurs** : création des comptes, modification du nom, du prénom et du rôle, activation ou désactivation, réinitialisation du mot de passe.
- **Rôles** : Administrateur, Gestionnaire de paie, Consultation (tableau en début de guide).
- **Paramètres** : informations de l'établissement ; taux de taxe par défaut des nouvelles périodes (par exemple 5,5 %), avec la possibilité de l'appliquer aussi aux périodes en brouillon ou ouvertes. Les périodes validées ou clôturées ne changent jamais.
- **Modèles de bulletin** : choix du modèle actif (bulletin officiel en Word ou en PDF, ou modèle importé) ; ajout d'un modèle en envoyant un bulletin déjà rempli (Word ou PDF) ou un modèle à balises ; bulletin d'essai avant enregistrement.
- **Sauvegardes** : création d'une copie horodatée de la base de données.
- **Restauration** : remplacement de la base par une sauvegarde, après vérification du fichier et création d'une sauvegarde de sécurité.
- **Diagnostics** : état de la base, des tables, des dossiers, des comptes administrateurs et du registre des documents.

## 15. Réinitialisation des données

Onglet **Administration › Réinitialisation des données**, réservé aux administrateurs. Cette fonction remet l'application dans l'état d'une installation neuve **du point de vue des données de paie**, par exemple avant une mise en service réelle après une période d'essai.

**Ce qui est supprimé** : enseignants, périodes de paie, heures, primes et indemnités, retenues, bulletins, registre des documents, fichiers générés (bulletins, exports Excel, archives, packs), historique des importations, alertes. Les statistiques et rapports, calculés à partir de ces données, redeviennent vides.

**Ce qui est conservé** : tous les comptes utilisateurs, leurs noms d'utilisateur, mots de passe, rôles et statuts ; les permissions ; votre session en cours ; le journal d'audit complet (connexions, gestion des comptes, sauvegardes, réinitialisations, calculs, validations, exports) ; les paramètres de l'établissement ; le taux de taxe par défaut ; les modèles de bulletin et le modèle actif ; les sauvegardes existantes ; les journaux techniques.

**Les comptes ne sont PAS supprimés.** Après l'opération, chacun se connecte avec les mêmes identifiants qu'auparavant.

**Confirmation** : l'onglet affiche la liste chiffrée de ce qui sera supprimé et conservé. Il faut cocher la case de confirmation, puis saisir `RÉINITIALISER` en majuscules (`REINITIALISER` sans accent est accepté) avant que le bouton **Réinitialiser toutes les données métier** devienne actif.

**Sauvegarde préalable** : avant toute suppression, l'application crée automatiquement une sauvegarde complète (base de données et fichiers générés). Son nom (`Avant_Reinitialisation_<date>.zip`) et son emplacement sont affichés à la fin de l'opération. La base seule (`avant_reinitialisation_<date>.db`) apparaît dans l'onglet Restauration et permet de revenir à l'état antérieur.

Si une vérification échoue pendant l'opération, les suppressions sont annulées ou la sauvegarde est restaurée automatiquement, et un message d'erreur explique la situation : aucune donnée n'est perdue.
