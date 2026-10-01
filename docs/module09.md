# Module 09 — Workflow complet du cycle de paie, contrôles, validation et clôture

## 1. Objectif

Faire du cycle **BROUILLON → OUVERTE → VALIDEE → CLOTUREE** un véritable
workflow assisté : détection d'anomalies avant validation, validation et
clôture protégées par un contrôle et une confirmation explicite,
traçabilité complète (audit), et un écran central de préparation de
paie. Aucune formule de salaire n'est dupliquée : tout provient de
`services/paie_service.py`, déjà validé aux modules 05 à 08.

## 2. Ce qui existait déjà (réutilisé, non recréé)

- Cycle de vie des périodes et ses transitions (`services/periode_service.py`).
- Moteur de calcul individuel/groupé (`services/paie_service.py`).
- Contrôle de cohérence arithmétique de base
  (`dashboard_service.controler_coherence_resultats`) — **réutilisé tel
  quel** par le nouveau service de contrôle, jamais réécrit.
- Génération des bulletins Word (module 07) et export Excel (modules 06/08).
- Suppression définitive enseignant/période, audit, transactions.

## 3. Ce que le module 09 ajoute

### 3.1 Service de contrôle — `services/controle_paie_service.py`

`controler_periode(periode_id, enseignant_ids=None)` calcule les résultats
via `paie_service.calculer_paie_groupe` (jamais recalculés) puis détecte
des anomalies structurées (`Anomalie` : niveau / code / enseignant /
message / valeur / recommandation), regroupées dans un `RapportControle`.

**Erreurs bloquantes** (empêchent la validation) : identité manquante/
invalide, heures négatives, total d'heures incohérent, taux horaire
invalide, montant négatif, enseignant non calculable, incohérence
arithmétique du calcul (délégué à `dashboard_service`).

**Avertissements** (n'empêchent pas la validation) : volume d'heures
élevé (> 300h), dette élevée (≥ 100 000 FCFA), retenue amicale élevée
(≥ 50 000 FCFA), aucun élément variable saisi, période sans aucune donnée.

### 3.2 Workflow de validation et de clôture « avec contrôle »

`valider_periode_avec_controle(periode_id, confirmation=True)` et
`cloturer_periode_avec_controle(...)` :

1. vérifient l'existence et le statut de la période ;
2. exécutent `controler_periode` ;
3. refusent si des erreurs bloquantes existent (avertissements affichés
   mais non bloquants) ;
4. exigent `confirmation=True` explicite (garde-fou service, en plus de
   la confirmation côté interface) ;
5. exécutent la transition d'état et l'écriture d'audit dans **une
   seule transaction SQLite** (`ROLLBACK` complet en cas d'échec) ;
6. retournent le rapport de contrôle (avertissements résiduels inclus).

La transition elle-même reste celle déjà validée par
`database/repositories/periode_repository.py` — aucune règle de
transition n'est dupliquée.

### 3.3 Comparaison entre périodes — `services/historique_paie_service.comparer_periodes`

Compare deux périodes sur leurs totaux déjà produits par
`comptabilite_service.preparer_etat_comptable` (nombre d'enseignants,
heures, gains, taxe, retenues, dettes, net) : écart absolu et en
pourcentage. Aucun recalcul de formule.

### 3.4 Nouvelle page — `pages/9_Controle_Paie.py`

Écran central : synthèse de la période (statut, enseignants, complets/
incomplets, masse salariale, moyenne/médiane/min/max du net), tableau
d'anomalies filtrable (Toutes / Erreurs / Avertissements), tableau
récapitulatif complet par enseignant (heures S1-S5, rémunération,
retenues, net, état du contrôle, bulletin disponible), puis validation
ou clôture avec confirmation explicite.

### 3.5 Ajustements des pages existantes

- `pages/2_Periodes_Paie.py` : les actions « Valider »/« Clôturer »
  redirigent désormais vers « Contrôle de la paie » (workflow contrôlé
  obligatoire pour ces opérations sensibles) plutôt que d'appeler
  directement la transition brute.
- `pages/6_Bulletins_Paie.py` : affiche un avertissement informatif
  (anomalies détectées) avant la génération des bulletins, sans jamais
  bloquer la génération elle-même (le contrôle reste au niveau période).
- `pages/8_Historique_Paie.py` : section « Comparaison entre deux
  périodes » ajoutée.

## 4. Base de données

**Additif uniquement**, aucune donnée existante supprimée ou modifiée :
- `models/enums.py` : ajout de `TypeActionAudit.VALIDATION_PERIODE`
  (`CLOTURE_PERIODE` existait déjà mais n'était utilisé par aucun code).
- `database/schema.sql` : ajout de `'validation_periode'` à la
  contrainte `CHECK` de `audit_log.type_action`.
- `database/repositories/periode_repository.py` : `changer_statut` et
  `cloturer` acceptent désormais un paramètre `conn` optionnel (même
  pattern que les autres repositories), nécessaire pour que la
  transition d'état et l'audit appartiennent à la même transaction.

Aucune migration destructive, aucune table supprimée, aucune colonne
retirée.

## 5. Audit et traçabilité

Toute validation et toute clôture (via le workflow contrôlé) sont
journalisées dans `audit_log`, qu'elles réussissent ou échouent en
cours de transaction (dans ce dernier cas, la transaction entière est
annulée : aucune trace d'audit pour une opération qui n'a pas abouti).
Les entrées d'audit existantes (suppression définitive) restent
inchangées et ne sont jamais supprimées par cascade.

## 6. Test de référence conservé

100 h × 2 000 FCFA → Net = 208 250 FCFA, vérifié à travers le workflow
complet (validation puis clôture avec contrôle) dans
`tests/test_controle_paie_service.py::test_cas_reference_100h_2000fcfa_inchange`.
