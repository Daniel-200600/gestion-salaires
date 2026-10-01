# Module 13 — Comptabilité, états de paie et rapprochement

## 1. Objectif

Ajouter un véritable module de reporting comptable et financier,
exploitant exclusivement les calculs déjà produits par
`services/paie_service.py` — aucune nouvelle formule de paie.

## 2. Architecture

```
pages/12_Rapports_Comptables.py
        |
services/reporting_paie_service.py   (lecture seule, aucune écriture de paie)
        |
        +-- services/comptabilite_service.preparer_etat_comptable   (module 06)
        +-- services/historique_paie_service.comparer_periodes      (module 08/12)
        |
        v
services/paie_service.py   (seule source des formules)
```

`exports/reporting_export.py` (nouveau, séparé de `exports/excel_export.py`
du module 06 pour ne jamais risquer de le régresser) réutilise les
styles déjà définis pour une apparence cohérente entre tous les
exports Excel de l'application.

## 3. États disponibles

- **État général de la période** : effectif, heures, gains, primes,
  indemnités, base taxable, taxe, retenues, dettes, net — tous
  directement issus de `EtatComptablePeriode.totaux` (module 06).
- **Détail par enseignant** : une ligne par enseignant, colonnes
  conformes aux noms de champs réels du projet.
- **Synthèse par statut / par sexe** : `SyntheseDetailleeGroupe`
  (nouveau, plus complet que `dashboard_service.SyntheseGroupe` du
  module 08, qui reste inchangé et toujours utilisé par le dashboard).
- **Classement** : par gain, base taxable, net ou heures, croissant ou
  décroissant — purement informatif.
- **État des retenues** : une ligne par enseignant, avec totaux.
- **Comparaison entre périodes** : réutilise intégralement
  `historique_paie_service.comparer_periodes` (module 12), sans le
  modifier.

## 4. Rapprochement mathématique

Deux niveaux, tous deux des vérifications d'ADDITION/SOUSTRACTION sur
des valeurs déjà produites par `paie_service` — jamais une nouvelle
dérivation depuis les heures/taux :

- **Individuel** (`rapprocher_enseignant`) :
  `Gain + AP/PP + Surveillance + Indemnité = Base taxable` et
  `Base taxable - Taxe - Retenue amicale - Dette = Net`.
- **Global** (`rapprocher_periode`) : somme des lignes individuelles
  comparée à chaque total déjà affiché par `EtatComptablePeriode.totaux`.

Statuts : `OK` (écart 0), `ÉCART` (écart ≠ 0), `ERREUR` (calcul
impossible). Testé avec un cas volontairement incohérent : l'écart est
correctement détecté et chiffré.

## 5. Analyse des variations

Seuil **explicite et configurable** (`SEUIL_VARIATION_NOTABLE_POURCENT`,
10 % par défaut, `services/reporting_paie_service.py`) — jamais une
valeur arbitraire non documentée. La division par zéro (période de
référence sans donnée) est déjà gérée proprement par
`historique_paie_service.comparer_periodes` (module 12) : une
`ComptabiliteError` claire est levée, jamais un `NaN`/`Infinity` affiché.

## 6. Export Excel

`Etat_Paie_{PERIODE}.xlsx` : feuilles Synthese, Detail_Enseignants,
Par_Statut, Par_Sexe, Retenues, Rapprochement, et Comparaison
(uniquement si une période de comparaison est sélectionnée — omise
proprement sinon). Jamais d'écrasement d'un fichier existant (suffixe
numérique automatique, même mécanisme que le module 06).

## 7. Permissions (module 11, réutilisées)

`reporting.consulter` (ADMIN, GESTIONNAIRE_PAIE, CONSULTATION) et
`reporting.exporter` (ADMIN, GESTIONNAIRE_PAIE uniquement) ajoutées à
la matrice centrale de `services/permission_service.py` — aucun
système parallèle.

## 8. Audit (module 10, réutilisé)

`REPORTING_EXPORTE` (à chaque export Excel) et `RAPPROCHEMENT_EXECUTE`
(à chaque exécution explicite du contrôle de rapprochement depuis la
page). La simple consultation de la page n'est volontairement pas
auditée à chaque affichage (bruit excessif, cohérent avec le reste de
l'application : consulter le tableau de bord n'est pas non plus
audité) — seules les actions réellement sensibles le sont.

## 9. Périodes clôturées

Le reporting est strictement en lecture (aucune fonction de ce module
n'écrit de donnée de paie). Vérifié par test explicite : l'état de
paie complet, le rapprochement et l'export fonctionnent normalement
sur une période clôturée, sans jamais modifier son statut ni ses
données.

## 10. Précision monétaire

Tous les montants manipulés restent des entiers FCFA (`int`), exactement
comme dans `paie_service.py` — aucun flottant introduit dans les
calculs de rapprochement ou d'agrégation.

## 11. Cas de référence

100 h × 2 000 FCFA → **Net = 208 250 FCFA**, retrouvé à l'identique
par le reporting, avec **rapprochement OK (écart 0 FCFA)**, vérifié à
travers le workflow complet (ouverture → saisie → validation →
clôture → reporting → export).

## 12. Tests

`tests/test_reporting_paie_service.py` (31), `tests/test_reporting_export.py` (9),
`tests/test_audit_reporting.py` (2), ajouts à `tests/test_permission_service.py` (2).
