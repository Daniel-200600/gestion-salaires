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
| Tableau de bord | Tableau de bord, Guide utilisateur, Politique de confidentialité, Conditions d'utilisation, À propos |
| Gestion | Enseignants, Périodes de paie |
| Paie | Données de paie, Import du fichier de paie, Calcul de paie, Cycle de paie, Bulletins de solde, Génération comptable |
| Contrôle & Historique | Contrôle de la paie, Historique de paie |
| Analyse & Rapports | Rapports comptables, Statistiques |
| Documents & Opérations | Gestion des documents, Importation, Notifications, Automatisation |
| Administration & Sécurité | Administration, Guide administrateur (administrateurs uniquement) |

Le **Tableau de bord** affiche le nombre d'enseignants (dont les fiches à compléter), les indicateurs de paie de la période choisie, les alertes actives et l'évolution de la masse salariale. Lorsqu'aucune donnée n'existe, la mention « Aucune donnée disponible. » s'affiche à la place des indicateurs.

La page **À propos** indique la version installée, les nouveautés de chaque version, la licence et le contact de l'auteur. Indiquez ce numéro de version pour toute demande d'assistance.

**Licence.** La licence active (nom de l'établissement) est rappelée en bas de la barre latérale. Si la mention « Mode démonstration » apparaît, aucune licence valide n'est active : l'application est limitée à 5 enseignants et la page Enseignants indique les places restantes. Seul un administrateur peut activer une licence (voir le guide administrateur).

## 3. Gestion des enseignants

Page **Gestion › Enseignants**.

- **Création** : ouvrez **Ajouter un enseignant**, renseignez le nom, le prénom, le sexe, le statut (permanent ou vacataire) et le taux horaire en FCFA, puis cliquez sur **Enregistrer l'enseignant**. Les champs marqués d'un astérisque sont obligatoires.
- **Permanent payé au mois** : pour un permanent qui touche un salaire mensuel fixe, renseignez **Salaire mensuel fixe (FCFA)** ; le taux horaire peut alors rester vide. Ce montant remplace heures × taux horaire dans le calcul ; les heures restent saisies à titre d'information. Le salaire fixe est réservé aux permanents ; pour revenir à un paiement à l'heure, videz ce champ (onglet **Modifier**). La liste indique la rémunération de chacun (« 150 000 FCFA / mois » ou « 1 800 FCFA / h »).
- **Reprise d'une liste existante** : si vous possédez déjà la liste de vos enseignants (Excel, Word ou PDF), inutile de la ressaisir : importez-la depuis **Documents & Opérations › Importation**, type « Enseignants » (voir section 11). Seul le nom est indispensable ; les informations absentes de la liste se complètent ensuite ici.
- **Recherche et liste** : la liste peut être filtrée par un terme de recherche ; les enseignants désactivés peuvent être affichés ou masqués. La colonne **Fiche** indique « Complète » ou les informations qui manquent ; la case **Seulement les fiches à compléter** n'affiche que ces dernières.
- **Fiches à compléter** : une fiche à laquelle il manque le sexe, le statut ou le taux horaire (cas fréquent après l'import d'une liste) est signalée par un message en haut de la page et par la mention « — à compléter » dans la liste de sélection. **Un enseignant dont la fiche est incomplète n'entre pas dans la paie** : il n'est proposé ni pour la saisie des heures, ni pour le calcul, ni pour les bulletins, ni pour l'automatisation, et un message rappelle combien de fiches sont ainsi écartées. Dès que la fiche est complétée, l'enseignant est traité comme les autres.
- **Compléter toutes les fiches en une fois** : ouvrez **Compléter les fiches en une fois**, sous le message des fiches à compléter. Un tableau présente chaque fiche incomplète : choisissez le sexe et le statut dans les listes, saisissez le taux horaire (cliquez deux fois sur une case pour la modifier), puis cliquez sur **Enregistrer les compléments**. Les cases encore inconnues peuvent rester vides. Si une valeur est incorrecte (par exemple un taux négatif), rien n'est enregistré et le message nomme l'enseignant concerné. Les fiches devenues complètes disparaissent du tableau et entrent dans la paie.
- **Faire remplir la liste par quelqu'un d'autre** : **Télécharger la liste à compléter (Excel)** produit un fichier où les informations connues sont déjà remplies et les cases manquantes surlignées en jaune. Faites-le remplir (secrétariat, enseignants), puis réimportez-le dans **Importation**, type « Enseignants », stratégie **Mettre à jour les doublons** (section 11) : seules les cases renseignées sont reprises.
- **Modification et complément d'une fiche** : sélectionnez l'enseignant dans **Actions sur un enseignant**, onglet **Modifier**. Pour une fiche à compléter, les champs manquants affichent « À renseigner » : choisissez le sexe et le statut, saisissez le taux horaire, puis cliquez sur **Enregistrer les modifications**. Une information encore inconnue peut rester vide ; la fiche reste alors « à compléter » et vous pourrez y revenir plus tard. Une information déjà renseignée n'est jamais effacée par un champ laissé vide. Le taux horaire enregistré sur la fiche est celui utilisé par les calculs ; les bulletins déjà figés d'une période validée ou clôturée conservent les montants de leur génération.
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
- **Taux de taxe** : la taxe ne concerne que les **vacataires** ; les permanents n'en paient pas. Chaque période porte son propre taux de taxe, affiché dans la liste (colonne **Taxe**, par exemple « 5,5 %, vacataires »). À la création, elle reçoit le taux par défaut réglé par l'administrateur (section 14). Tant que la période est en brouillon ou ouverte, un administrateur peut l'ajuster (**Appliquer ce taux à la période**) ; dès la validation, il est figé.

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

### Import du fichier de paie

Page **Paie › Import du fichier de paie** (administrateurs et gestionnaires de paie). Si l'établissement prépare déjà sa paie dans un classeur Excel — une feuille des heures (S1 à S5), une feuille des informations de chaque enseignant (sexe, statut, taux horaire, gain, primes, retenues) et une feuille d'état comptable — ce classeur s'importe en une fois.

1. Choisissez la période (elle doit être ouverte), puis déposez le classeur (.xlsx ou .xlsm). Les feuilles sont reconnues par leurs intitulés de colonnes, quel que soit leur nom.
2. **Vérification** : l'application indique les fiches qui seront créées ou mises à jour, les salaires fixes reconnus, les lignes **à vérifier** et les **erreurs**, et compare le net total du fichier au net calculé.
   - Les heures retenues sont celles de la **feuille des heures** ; si la feuille des informations en indique d'autres, l'écart est signalé.
   - Un **permanent** dont le gain est un montant saisi (sans taux horaire) est enregistré avec un **salaire mensuel fixe**.
   - Le net de chaque ligne est recalculé par l'application et comparé à celui de l'état comptable ; un écart est signalé, jamais corrigé en silence (il vient en général d'heures différentes entre les feuilles, de l'arrondi de la taxe ou d'une prime que l'application taxe).
   - Un nom écrit autrement dans deux feuilles, un enseignant déjà enregistré dont la fiche change (taux, statut…) ou un nom proche d'une fiche existante sont aussi signalés.
3. **Compléter ou corriger** : le tableau reprend chaque ligne ; modifiez une case (double-clic), décochez **Importer** pour écarter une ligne, puis cliquez sur **Vérifier à nouveau**. Une ligne en erreur (sexe, statut ou taux manquant, enseignant désactivé…) doit être corrigée ou décochée.
4. **Valider** : cochez la confirmation, puis **Enregistrer dans la période**. Les fiches sont créées ou mises à jour (le nom d'une fiche existante est conservé) et les heures, primes et retenues sont enregistrées dans la période, en une seule opération : en cas d'erreur, rien n'est enregistré. Les données déjà saisies pour ces enseignants dans la période sont remplacées. L'import est inscrit au journal d'audit.
5. Poursuivez avec **Calcul de paie** puis **Contrôle de la paie** (liens proposés après l'enregistrement).

## 6. Calcul

Page **Paie › Calcul de paie**. Choisissez la période puis cliquez sur **Lancer le calcul**. Le calcul est une prévisualisation : il ne génère aucun bulletin et ne modifie aucune donnée.

Le montant net est obtenu ainsi :

1. gain horaire = total des heures × taux horaire ;
2. base taxable = gain horaire + primes et indemnités ;
3. taxe = base taxable × taux de taxe de la période (5,5 % par défaut) pour un **vacataire** ; **aucune taxe pour un permanent** ;
4. net à percevoir = base taxable − taxe − retenues.

Exemple d'un vacataire : 10 heures à 1 800 FCFA donnent 18 000 FCFA, une taxe de 990 FCFA (5,5 %) et un net de 17 010 FCFA.

Exemple : 100 heures à 2 000 FCFA, 35 000 FCFA de primes et indemnités et 15 000 FCFA de retenues donnent une base taxable de 235 000 FCFA. Pour un vacataire, la taxe est de 12 925 FCFA et le net de 207 075 FCFA ; pour un permanent, la taxe est nulle et le net de 220 000 FCFA.

Les montants sont arrondis au franc le plus proche. Le statut pris en compte est celui de la fiche de l'enseignant au moment du calcul (section 3, **Changer le statut**). Sur le bulletin d'un permanent, la ligne Taxe indique 0.

Les périodes validées ou clôturées avant la version 1.6.0 gardent la règle avec laquelle elles ont été calculées (taxe appliquée à tous les enseignants) : leurs montants ne changent pas. La liste des périodes l'indique (« tous les enseignants »).

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

- **Fichiers acceptés** : Excel (.xlsx) ou CSV (.csv), 10 Mo au maximum (un fichier plus lourd est refusé dès l'envoi), pour les quatre types d'import (enseignants, heures, rémunérations, retenues). Pour les **enseignants**, une liste existante en **Word (.docx)** ou en **PDF** est aussi acceptée. Vous pouvez partir du modèle Excel ou CSV proposé, ou importer directement votre propre liste.
- **Importer une liste d'enseignants existante** :
  1. Choisissez le type « Enseignants » et déposez votre fichier. L'application lit les tableaux qu'il contient : feuille Excel, tableaux d'un document Word, tableaux d'un PDF (un tableau qui se poursuit sur plusieurs pages est lu d'un seul tenant). Si le fichier contient plusieurs tableaux, choisissez celui à importer dans **Tableau à importer**.
  2. Ouvrez **Vérifier l'association des colonnes** : l'application reconnaît d'elle-même les intitulés courants (« Nom », « Prénom(s) », « Noms et prénoms », « Sexe », « Statut », « Taux horaire (FCFA) », « Téléphone », « E-mail », « Adresse »…). Corrigez l'association si une colonne a été mal reconnue, ou choisissez « (ignorer) » pour une colonne inutile. Seule une colonne de nom (ou de nom complet) est exigée.
  3. Les valeurs sont interprétées avec souplesse : « M », « Masculin », « Homme » ; « P », « Permanent » ; « V », « Vacataire » ; « 1 500 FCFA » pour un taux. Une valeur absente ou illisible n'empêche pas l'import : la ligne devient une **fiche à compléter**, avec un avertissement qui précise l'information manquante.
  4. La prévisualisation indique le nombre de **Fiches à compléter**. Après l'import, un lien mène directement à la page Enseignants pour les compléter (section 3).
  5. Si un enseignant existe déjà et que vous choisissez la mise à jour des fiches existantes, seules les informations présentes dans le fichier sont reportées : une case vide du fichier n'efface jamais une information déjà enregistrée.
- **Doublons** : un enseignant déjà enregistré est reconnu même si son nom est écrit autrement — dans un autre ordre (« Elise MBARGA » pour « MBARGA Élise »), sans accents ou en minuscules. La **Stratégie face aux doublons** s'applique alors (refuser, ignorer ou mettre à jour) ; une mise à jour conserve le nom tel qu'il est enregistré.
- **Doublons probables** : un nom très proche d'un enseignant existant ou d'une autre ligne du fichier (prénom en plus ou en moins, faute de frappe : « NGONO Marie » et « NGONO Marie Claire ») est signalé après la simulation, avec le nom dont il est proche. Vérifiez la liste : sans autre choix, ces lignes sont créées ; cochez **Écarter les doublons probables** pour ne pas les créer.
- **PDF scannés** : un PDF qui n'est qu'une image (document scanné) ne contient pas de texte lisible ; l'application le signale. Utilisez alors le fichier Word ou Excel d'origine, ou ressaisissez la liste dans le modèle Excel.
- **Imports d'heures, de rémunérations ou de retenues** : une ligne qui concerne un enseignant dont la fiche est incomplète est rejetée avec un message invitant à compléter la fiche d'abord.
- **Prévisualisation** : après l'analyse du fichier, chaque ligne est présentée avec l'action prévue (création, mise à jour, ligne ignorée ou rejetée) et ses éventuelles erreurs.
- **Validation** : **Lancer la simulation** montre le résultat sans rien enregistrer. **Confirmer et importer** enregistre ensuite les données.
- **Rollback** : l'import est exécuté en une seule opération. Si une erreur survient, rien n'est enregistré et le rapport indique « ÉCHEC (annulé intégralement) ». L'historique des imports reste consultable.

## 12. Automatisation

Page **Documents & Opérations › Automatisation** (administrateurs et gestionnaires de paie).

- **Génération groupée** : après vérification des préconditions, **Simuler** affiche ce qui serait produit, sans écriture. **Générer les bulletins** produit les bulletins de tous les enseignants concernés. **Reprendre uniquement les erreurs** relance les seuls bulletins en échec.
- **Exports** : **Vérifier l'intégrité des documents de cette période**, **Créer l'archive de cette période** (période clôturée) et **Créer le pack de paie** (archive ZIP regroupant les documents déjà enregistrés pour la période, avec un inventaire), chacun téléchargeable.

## 13. Notifications

Page **Documents & Opérations › Notifications**. Les alertes signalent un point à traiter : anomalie de paie, document manquant ou modifié, sauvegarde absente ou ancienne, problème d'import, fiches d'enseignants à compléter (une seule alerte indique leur nombre ; elle se résout d'elle-même une fois toutes les fiches complétées). Chaque alerte indique son niveau en toutes lettres (Critique, Erreur, Avertissement, Info).

- **Consultation** : **Analyser maintenant** relance les détections. Filtrez par niveau, statut, période, enseignant ou texte recherché ; exportez la liste filtrée au format Excel.
- **Acquittement** : **Marquer lue** puis **Acquitter** indiquent que l'alerte a été prise en compte.
- **Résolution** : **Résoudre** lorsque la cause est corrigée, ou **Ignorer** lorsque l'alerte ne nécessite pas d'action. Une anomalie corrigée est aussi résolue automatiquement lors de l'analyse suivante.

## 14. Administration

Page **Administration & Sécurité › Administration**, réservée aux administrateurs. Le **Guide administrateur** détaille chaque opération.

- **Utilisateurs** : création des comptes, modification du nom, du prénom et du rôle, activation ou désactivation, réinitialisation du mot de passe.
- **Rôles** : Administrateur, Gestionnaire de paie, Consultation (tableau en début de guide).
- **Paramètres** : informations de l'établissement ; taux de taxe par défaut des vacataires pour les nouvelles périodes (5,5 % au départ), avec la possibilité de l'appliquer aussi aux périodes en brouillon ou ouvertes. Les périodes validées ou clôturées ne changent jamais.
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
