# Gestion des Salaires — v1.6.0

[![tests](https://github.com/Daniel-200600/gestion-salaires/actions/workflows/tests.yml/badge.svg)](https://github.com/Daniel-200600/gestion-salaires/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-propri%C3%A9taire-lightgrey)

Application de gestion de la paie des enseignants, développée en Python (Streamlit + SQLite) pour les établissements scolaires au Cameroun.

## Présentation

Couvre l'intégralité du cycle de paie : gestion des enseignants et des périodes, saisie des heures et éléments de rémunération, calcul de paie, contrôle, validation et clôture, génération de bulletins Word, reporting et rapprochement comptable, gestion documentaire et archivage, import massif, notifications et alertes, statistiques avancées, automatisation, ainsi que l'authentification, les permissions, la sauvegarde/restauration et le diagnostic système.

## Fonctionnalités

- Authentification et rôles (ADMIN, GESTIONNAIRE_PAIE, CONSULTATION)
- Gestion des enseignants et des périodes de paie (cycle BROUILLON → OUVERTE → VALIDEE → CLOTUREE)
- Calcul de paie (source unique : `services/paie_service.py`)
- Contrôle de paie, validation, clôture
- Bulletins de solde identiques au bulletin officiel de l'établissement, en Word ou en PDF
- Modèles de bulletin importables (Word ou PDF, bulletin rempli ou modèle à balises)
- Taxe réservée aux vacataires, taux paramétrable (5,5 % par défaut, figé par période à la validation)
- Changement de statut d'un enseignant (vacataire / permanent), journalisé
- Licence d'utilisation par clé signée, liée à l'ordinateur (mode démonstration limité à 5 enseignants sans licence) ; les clés sont créées par l'auteur avec `outils/generer_licence.py`, à partir d'une clé privée conservée hors du projet
- Reprise d'une liste d'enseignants existante (Excel, CSV, Word ou PDF), détection des doublons probables ; les informations manquantes se complètent plus tard, une par une ou toutes ensemble, les fiches incomplètes restant hors de la paie
- Exports comptables (Excel)
- Historique et reporting multi-périodes
- Gestion documentaire (registre, intégrité, archivage sécurisé)
- Import massif Excel/CSV avec validation, doublons, dry-run, transaction
- Notifications et alertes opérationnelles
- Statistiques avancées et analyse décisionnelle
- Automatisation et génération massive
- Sauvegarde/restauration, diagnostics, audit
- Réinitialisation des données métier (administrateurs uniquement), sans effet sur les comptes utilisateurs
- Documentation intégrée : guide utilisateur, guide administrateur, politique de confidentialité, conditions d'utilisation

## Architecture générale

```
app.py                 Point d'entrée Streamlit (navigation en 7 blocs, favicon, logo)
launcher.py             Point d'entrée pour l'exécutable Windows (module 20)
config/                 Paramètres centralisés (chemins, version, sécurité)
models/                 Structures de données
database/               Schéma SQL, connexion, repositories (accès SQL exclusif)
services/                Logique métier (aucun accès SQL direct hors repositories)
exports/                Génération Excel/Word/ZIP (pure présentation)
ui_pages/               Pages Streamlit internes (orchestration UI uniquement — regroupées
                        en 7 blocs de navigation par utils/navigation.py + app.py)
utils/                  Validation, formatage, sécurité, session, documentation intégrée
assets/                Favicon (PNG, ICO) et logos de l'application
tests/                  Suite de tests (voir ci-dessous)
docs/                   Documentation (les quatre documents affichés dans l'application y sont aussi)
templates/              Modèles de bulletin standard (Word, PDF) et script de construction
```

Principe respecté dans tout le projet : **Page Streamlit → Service → Repository → SQLite**, jamais d'accès SQL direct depuis une page, jamais de logique métier dans l'interface.

## Installation (développement)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Au premier lancement, aucun utilisateur n'existe : un formulaire de création du premier compte administrateur s'affiche automatiquement. Aucun mot de passe par défaut n'est jamais créé.

## Installation (Windows, utilisateur final)

Voir `docs/installation_windows.md`.

## Configuration

Tous les paramètres sont centralisés dans `config/settings.py` et `config/paths.py` — jamais de chemin codé en dur ailleurs dans le projet. Les données utilisateur (base SQLite, sauvegardes, documents, logs) sont toujours séparées des fichiers du programme (voir `config/paths.py`), y compris une fois l'application empaquetée.

## Sauvegarde et restauration

Sauvegarde via l'API native SQLite (`sqlite3.Connection.backup()`), jamais une simple copie de fichier. La restauration crée automatiquement une sauvegarde de sécurité de la base active avant tout remplacement, et revient en arrière automatiquement en cas d'échec de vérification. Voir Administration → Sauvegarde dans l'application.

## Dépannage

- **La page affiche « Accès refusé »** : contactez un administrateur pour vérifier votre rôle.
- **Diagnostic système en orange/rouge** : consultez Administration → Diagnostic pour le détail.
- **Restauration refusée** : le fichier n'est pas une base SQLite valide, ou la confirmation n'a pas été cochée.

## Version

**1.6.0** — voir `config/settings.py` (`VERSION`), source unique du numéro de version.

## Tests

```bash
python -m pytest -q
```

Résultat de référence : **1588 passed, 3 skipped** (version 1.6.0 ; voir `docs/bulletins_taxe_statut.md`).

## Licence

Logiciel propriétaire, tous droits réservés (voir [LICENSE](LICENSE)). Le code
est visible à titre de présentation ; toute utilisation, copie, modification
ou distribution requiert une licence écrite de l'auteur. Les versions publiées
avant ce changement l'avaient été sous licence MIT.
