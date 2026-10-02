# Politique de confidentialité

> **Document à adapter et à faire valider.** Ce texte décrit le fonctionnement réel du logiciel. Il ne constitue pas un avis juridique et ne garantit pas, à lui seul, la conformité à une réglementation. L'établissement qui exploite le logiciel doit le compléter (mentions entre crochets) et le faire valider par la personne ou le service compétent en matière juridique et de protection des données avant toute utilisation officielle.

## 1. Objet

Ce document explique quelles données le logiciel **Gestion des Salaires** traite, pourquoi, où elles sont stockées, comment elles sont protégées, qui peut y accéder et comment les sauvegardes sont gérées.

Responsable de l'exploitation : [nom de l'établissement, à compléter].
Contact pour toute question relative aux données : [fonction et coordonnées, à compléter par l'établissement].

## 2. Données traitées

**Enseignants**

- identité : nom, prénom, sexe ;
- situation : statut (permanent ou vacataire), taux horaire, compte actif ou désactivé ;
- coordonnées facultatives : adresse électronique, téléphone, adresse ;
- données de paie par période : heures effectuées par semaine, primes et indemnités, retenues (retenue amicale, dette), montants calculés (gain, base taxable, taxe, net à percevoir) ;
- documents générés : bulletins de solde, états comptables, rapports, archives.

**Utilisateurs du logiciel**

- nom, prénom, nom d'utilisateur, rôle, statut du compte, date de dernière connexion ;
- mot de passe, conservé uniquement sous forme d'empreinte non réversible (algorithme scrypt).

**Traçabilité**

- journal d'audit : date, nom d'utilisateur, nature de l'opération et description (par exemple le nom d'un enseignant pour la génération d'un bulletin). Le journal ne contient jamais de mot de passe ni d'empreinte de mot de passe ;
- journal technique : événements de fonctionnement (erreurs, sauvegardes, restaurations).

**Paramètres de l'établissement** : nom, adresse, téléphone, adresse électronique, année scolaire, responsable.

## 3. Finalités

Ces données sont utilisées exclusivement pour :

- calculer la rémunération des enseignants et éditer les bulletins de solde ;
- produire les états comptables, rapports et statistiques de paie ;
- contrôler, valider et clôturer les périodes de paie ;
- contrôler l'accès au logiciel et tracer les opérations sensibles.

Le logiciel ne contient aucune fonction de publicité, de profilage ou de transmission commerciale des données.

## 4. Lieu de stockage

Toutes les données sont enregistrées **sur le poste qui exécute le logiciel**, dans un dossier de données :

- la base de données (fichier SQLite `app.db`) ;
- les fichiers générés (dossier `exports`) ;
- les sauvegardes (dossier `backups`) ;
- les journaux techniques (dossier `logs`) ;
- les paramètres de l'établissement (fichier `parametres_etablissement.json`).
- les modèles de bulletin importés par un administrateur (dossier `modeles_bulletin`). Lorsqu'un bulletin déjà rempli est envoyé comme modèle, les valeurs reconnues (nom, statut, montants...) sont effacées ou remplacées par des balises avant l'enregistrement ; un texte que l'administrateur laisse en « texte fixe » est en revanche conservé tel quel.

Sous Windows, ce dossier est `data\` à côté de l'exécutable s'il existe, sinon `%APPDATA%\GestionPaie\`. L'emplacement exact est affiché dans Administration › Paramètres › Emplacements de stockage.

Le logiciel n'envoie aucune donnée à un service extérieur : il n'utilise aucun service en ligne et l'envoi de statistiques d'utilisation de la bibliothèque d'interface (Streamlit) est désactivé. Le logiciel est consulté au moyen d'un navigateur web ; selon la configuration du poste et du réseau, il peut être joignable depuis d'autres postes du réseau local. [L'établissement précise ici s'il autorise un tel accès et comment il le restreint.]

## 5. Protection des données

Mesures intégrées au logiciel :

- accès uniquement par compte nominatif et mot de passe ; aucun compte ni mot de passe par défaut ;
- mots de passe conservés sous forme d'empreinte scrypt ;
- blocage temporaire après cinq tentatives de connexion infructueuses ;
- expiration de la session après deux heures d'inactivité ;
- droits attribués par rôle et revérifiés dans la base à chaque page et à chaque opération sensible ;
- journal d'audit des connexions, des opérations sur les comptes et des opérations de paie ;
- périodes clôturées et bulletins figés non modifiables ;
- contrôle d'intégrité des documents générés et de la base de données ;
- sauvegarde automatique avant toute restauration ou réinitialisation.

Limites à connaître : la base de données et les fichiers générés ne sont **pas chiffrés** par le logiciel. La protection du poste (accès physique, session Windows protégée, chiffrement du disque, antivirus, mises à jour) et des copies de sauvegarde relève de l'établissement. [Mesures organisationnelles de l'établissement, à compléter.]

## 6. Accès selon les rôles

| Rôle | Accès aux données |
|---|---|
| Administrateur | Toutes les données et fonctions, y compris les comptes, les sauvegardes, la restauration, les journaux et la réinitialisation des données. |
| Gestionnaire de paie | Données des enseignants et de paie : consultation, saisie, calcul, contrôle, validation, bulletins, exports, documents, importation. Pas d'accès à l'administration. |
| Consultation | Consultation des données de paie, bulletins, rapports, statistiques, documents et notifications, sans modification. |

Les comptes sont créés par un administrateur. [L'établissement précise ici les personnes habilitées pour chaque rôle.]

## 7. Sauvegardes

- Les sauvegardes sont des copies complètes de la base de données ; celles réalisées avant une réinitialisation contiennent aussi les fichiers générés. Elles contiennent donc les mêmes données personnelles que la base et doivent être protégées de la même manière.
- Elles sont créées à la demande d'un administrateur, et automatiquement avant une restauration ou une réinitialisation des données.
- Le logiciel ne supprime jamais de sauvegarde. [Durée de conservation des sauvegardes et procédure de copie externe, à définir par l'établissement.]

## 8. Durée de conservation

Le logiciel ne supprime aucune donnée automatiquement. Un enseignant peut être désactivé (son historique est conservé) ; sa suppression définitive n'est possible qu'en l'absence de bulletin. La réinitialisation des données supprime l'ensemble des données de paie. [Durées de conservation applicables aux données de paie, à définir par l'établissement selon ses obligations.]

## 9. Demandes relatives aux données

Lorsque la réglementation applicable le prévoit, une personne concernée peut demander des informations sur les données la concernant, leur rectification ou, le cas échéant, leur suppression, auprès de : [contact à compléter par l'établissement].

Fonctions du logiciel utiles pour répondre à une demande :

- consulter la fiche d'un enseignant (Gestion › Enseignants) et la corriger ;
- consulter l'historique de paie d'un enseignant (Contrôle & Historique › Historique de paie) ;
- retrouver et télécharger ses bulletins (Gestion des documents) ;
- exporter des données au format Excel (Tableau de bord, Rapports comptables, Statistiques).

## 10. Évolution de ce document

Ce document doit être mis à jour lorsque le fonctionnement du logiciel ou l'organisation de l'établissement change. Version du logiciel décrite : 1.3.0. [Date de validation par l'établissement, à compléter.]
