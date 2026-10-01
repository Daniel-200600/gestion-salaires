# Module 08 — Tableau de bord, historique et consultation de la paie

## 1. Objectif

Offrir un espace de **consultation, agrégation et historique** permettant à
l'administrateur de comprendre en un coup d'œil l'état de l'établissement
(enseignants, périodes, masse salariale) sans jamais recalculer la paie :
toutes les valeurs affichées proviennent de `services/paie_service.py`,
déjà validé aux modules 05 à 07.

## 2. Nouvelles fonctionnalités

- Tableau de bord général (indicateurs enseignants + paie de la période)
- Recherche et filtres combinables (statut, sexe, état actif/inactif)
- Fiche détaillée par enseignant (identité, heures, rémunération, retenues, résultat)
- Historique des bulletins déjà générés (lecture du système du module 07, sans nouveau générateur)
- Statistiques par statut et par sexe (strictement descriptives)
- Contrôles de cohérence (détection d'anomalies, aucune modification de données)
- Évolution de la masse salariale (tableau + graphique)
- Historique de paie multi-périodes par enseignant
- Export Excel de la consultation filtrée (réutilise `exports/excel_export.py`)

## 3. Architecture

```
pages/7_Tableau_de_Bord.py   pages/8_Historique_Paie.py
        |                              |
services/dashboard_service.py   services/historique_paie_service.py
        |                              |
        +---------> services/paie_service.py (seule source des formules)
                              |
              services/comptabilite_service.py, periode_service.py,
              enseignant_service.py, bulletin_service.py (lecture seule)
                              |
                     database/repositories/
```

Aucun SQL dans les pages. Aucune formule de paie dans `dashboard_service.py`
ni `historique_paie_service.py` (vérifié par test d'inspection du code
source dans les deux suites de tests).

## 4. Données utilisées

Aucune nouvelle table. Le module s'appuie exclusivement sur les tables et
services existants : `enseignants`, `periodes_paie`, `saisies_heures`,
`elements_remuneration`, `retenues`, et le système de fichiers de
`data/exports/bulletins/` (lecture seule, via `bulletin_service.bulletin_deja_genere`).

## 5. Calculs utilisés

Aucun. Le module 08 est un module de consultation : il appelle
`paie_service.calculer_paie_enseignant` / `calculer_paie_groupe` /
`calculer_totaux_groupe`, déjà testés aux modules 05 et 06.

Le seul « calcul » local est une **agrégation d'affichage** (nombre
d'enseignants, sommes, moyennes descriptives) — jamais une formule de
salaire.

## 6. Nouvelles pages

- `pages/7_Tableau_de_Bord.py`
- `pages/8_Historique_Paie.py`

## 7. Nouveaux services

- `services/dashboard_service.py` *(déjà présent dans le projet fourni — vérifié conforme, aucune duplication de formule)*
- `services/historique_paie_service.py` *(nouveau)*

## 8. Nouveaux tests

- `tests/test_dashboard_service.py` (22 tests)
- `tests/test_historique_paie_service.py` (12 tests)

## 9. Procédure de lancement

```bash
cd salaires_app
pip install -r requirements.txt
streamlit run app.py
```

## 10. Procédure de vérification

```bash
pytest -q
```

Puis navigation manuelle : Accueil -> Enseignants -> Périodes de paie ->
Données de paie -> Calcul de paie -> Génération comptable -> Bulletins de
paie -> Tableau de bord -> Historique de paie.

## 11. Correction — export filtré, suppression enseignant/période

Trois ajustements apportés après la version initiale du module 08,
détaillés dans `docs/suppression_donnees.md` :

1. **Export Excel filtré** (`dashboard_service.exporter_consultation_excel`) :
   accepte désormais une liste `enseignant_ids` reflétant exactement la
   sélection filtrée du tableau de bord, au lieu d'un seul identifiant.
2. **Suppression définitive d'un enseignant** : correction d'un bug de
   détection des bulletins (la vérification ne portait que sur la table
   `bulletins_paie`, jamais alimentée par le module 07 en usage réel) ;
   confirmation renforcée par saisie du nom complet exact.
3. **Suppression définitive d'une période** (nouvelle fonctionnalité) :
   `periode_service.supprimer_periode_definitivement`, restreinte aux
   périodes BROUILLON sans bulletin, transaction SQLite unique, audit.

Tests ajoutés : `tests/test_export_filtre.py` (10), 2 tests dans
`tests/test_suppression_enseignant.py`, `tests/test_suppression_periode.py`
(18).
