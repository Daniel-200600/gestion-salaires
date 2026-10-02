# À propos de Gestion des Salaires

Gestion des Salaires est un logiciel de gestion de la paie des enseignants : saisie des heures et des éléments de rémunération, calcul du net à payer, bulletins de solde au format Word ou PDF, états comptables, contrôle puis clôture des périodes de paie. Il fonctionne entièrement sur l'ordinateur où il est installé : aucune donnée n'est envoyée sur Internet.

## Nouveautés de la version 1.5.0

- **Clé de licence** : le logiciel s'active avec une clé délivrée par l'auteur pour l'ordinateur de l'établissement (Administration › Licence). La clé est signée : elle ne peut être ni fabriquée, ni modifiée, ni utilisée sur un autre ordinateur.
- **Mode démonstration** : sans licence, l'application reste utilisable avec 5 enseignants au maximum ; les données déjà enregistrées ne sont jamais bloquées.

## Version 1.4.0

- **Compléter les fiches en une fois** : un tableau sur la page Enseignants permet de renseigner le sexe, le statut et le taux horaire de toutes les fiches incomplètes, puis de tout enregistrer d'un clic.
- **Liste à compléter en Excel** : à télécharger, faire remplir (cases manquantes surlignées), puis réimporter ; aucune information déjà enregistrée n'est effacée.
- **Doublons mieux détectés à l'import** : un nom écrit dans un autre ordre est reconnu ; un nom très proche (prénom en plus ou en moins, faute de frappe) est signalé et peut être écarté.
- **Taille des fichiers** : la limite affichée lors de l'envoi correspond désormais à la limite réelle (10 Mo, 2 Mo pour le logo).

## Version 1.3.0

- **Reprise d'une liste d'enseignants existante** : importez directement votre liste en Excel, CSV, Word ou PDF (Documents & Opérations › Importation) ; les intitulés de colonnes courants sont reconnus et l'association des colonnes peut être corrigée avant l'import.
- **Fiches à compléter** : seul le nom est obligatoire à l'import. Le sexe, le statut ou le taux horaire manquants se complètent plus tard dans Gestion › Enseignants ; une fiche incomplète est signalée partout et reste hors de la paie tant qu'elle n'est pas complétée.
- **Tableau de bord et notifications** : nouvel indicateur « Fiches à compléter », avec un lien vers la page Enseignants, et une alerte qui en indique le nombre.
- **Ré-import sans perte** : la mise à jour d'enseignants existants par import ne remplace jamais une information enregistrée par une case vide.

## Version 1.2.0

- **Sauvegarde automatique quotidienne** : une sauvegarde de la base est créée chaque jour à la première utilisation ; les 30 plus récentes sont conservées (Administration › Sauvegarde).
- **Modèles de bulletin inclus dans les sauvegardes** : chaque sauvegarde emporte les modèles importés, remis en place lors d'une restauration.
- **Alerte sur le modèle de bulletin** : si le modèle choisi n'est plus disponible, un message l'indique sur les pages Bulletins, Automatisation et Administration, avec la marche à suivre.
- **En-tête et logo de l'établissement** : la région, les délégations, le nom de l'établissement, le lieu de signature, le titre du signataire et le logo se règlent dans Administration › Paramètres ; l'application produit elle-même ses modèles de bulletin.
- **Journal d'audit conservé en entier** : la réinitialisation des données ne supprime plus l'historique des calculs, validations et exports.
- **Droits renforcés** : désactiver ou réactiver un enseignant est réservé aux comptes autorisés à modifier les enseignants.
- **Sécurité réseau** : l'application n'est accessible que depuis l'ordinateur où elle tourne, jamais depuis le réseau de l'établissement.
- **Démarrage et arrêt** : un second double-clic sur l'icône rouvre l'application déjà lancée ; le bouton « Quitter l'application » l'arrête proprement.
- **Installateur Windows** : installation, raccourcis et désinstallation standard ; les données sont conservées lors d'une mise à jour ou d'une désinstallation.

## Version 1.1.0

- Bulletins de solde au format Word et PDF, fidèles au modèle de l'établissement ; import de modèles (à balises ou bulletin déjà rempli).
- Taux de taxe réglable par l'administrateur, propre à chaque période et figé à sa validation.
- Changement de statut d'un enseignant (vacataire ou permanent), inscrit au journal d'audit.

## Vos données

La base de données, les sauvegardes, les modèles de bulletin et les documents produits sont enregistrés sur cet ordinateur, dans le dossier de données de l'application. Ils appartiennent à l'établissement qui utilise le logiciel. Copiez régulièrement le dossier des sauvegardes sur un support externe (clé USB, disque externe) : une sauvegarde conservée sur le même disque ne protège pas contre la panne de ce disque.

## Licence

Logiciel propriétaire, tous droits réservés. Son utilisation est réservée aux établissements titulaires d'un contrat de licence écrit avec l'auteur, dans les limites de ce contrat. Il est interdit de le copier, de le revendre, de le prêter ou de le redistribuer sans autorisation écrite.

Chaque licence est délivrée pour un ordinateur, sous la forme d'une clé d'activation (Administration › Licence). La licence active est indiquée en haut de cette page ; sans elle, le logiciel fonctionne en mode démonstration.

## Assistance

Les coordonnées de l'auteur sont affichées en haut de cette page. Pour toute question, indiquez le numéro de version installée.
