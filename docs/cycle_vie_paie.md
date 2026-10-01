# Cycle de vie d'une période de paie

```
BROUILLON  →  OUVERTE  →  VALIDEE  →  CLOTUREE
                  |            |
                  |            └── (les bulletins sont générés ici)
                  └── (saisie des heures / primes / retenues)
```

Les transitions sont **strictement séquentielles** : impossible de revenir
en arrière, de sauter une étape (ex: BROUILLON → CLOTUREE interdit), ou de
modifier une période CLOTUREE. Ces règles sont appliquées par des triggers
SQLite (`database/schema.sql`) *et* par le service (`periode_service.py`,
une fonction dédiée par transition) — une tentative de contournement en
base ou via un appel direct au repository échoue également.

## BROUILLON (état initial)

La période vient d'être créée. C'est la seule étape où le **mois et
l'année peuvent encore être corrigés** (avant que la période ne soit
mise en circulation).

| Élément | Modifiable ? |
|---|---|
| `periodes_paie` (mois, année, libellé) | Oui |
| `saisies_heures` / `elements_remuneration` / `retenues` | **Non** — la saisie n'a pas encore commencé |
| `bulletins_paie` | Ne peut pas encore exister |
| Suppression de la période | Autorisée |

## OUVERTE

La période est ouverte à la saisie de la paie du mois.

| Élément | Modifiable ? |
|---|---|
| `periodes_paie` (mois, année) | Non — pour éviter de déplacer une période déjà en cours de saisie |
| `saisies_heures` | Oui (insertion, modification, suppression) |
| `elements_remuneration` | Oui |
| `retenues` | Oui |
| `bulletins_paie` | Ne peut pas encore exister |
| Suppression de la période | Interdite |

C'est ici, et **uniquement ici**, que l'on corrige une erreur de saisie
(heures, prime, retenue) avant de figer quoi que ce soit.

## VALIDEE

Les données de paie sont considérées comme validées et prêtes pour le
calcul définitif.

| Élément | Modifiable ? |
|---|---|
| `periodes_paie` (statut) | Peut évoluer vers CLOTUREE uniquement |
| `saisies_heures` / `elements_remuneration` / `retenues` | **Non** — gelées (trigger) |
| `bulletins_paie` | Génération autorisée (INSERT uniquement) |
| Suppression de la période | Interdite |

Si une erreur est découverte après validation, elle ne doit **pas** être
corrigée en modifiant les données sources (c'est techniquement bloqué).
La correction se fera via un mécanisme de régularisation dédié, à
concevoir au moment du `paie_service.py` — hors périmètre actuel.

## CLOTUREE

État terminal. La période entière devient figée. `date_cloture` est
renseignée automatiquement à cette transition (garanti par une
contrainte `CHECK` en base : `date_cloture` est non nulle si et
seulement si `statut = 'cloturee'`).

| Élément | Modifiable ? |
|---|---|
| `periodes_paie` (tout champ, y compris statut) | **Non** — figée (trigger) |
| `saisies_heures` / `elements_remuneration` / `retenues` | Non (déjà gelées depuis VALIDEE) |
| `bulletins_paie` | Non (immuables depuis leur création) |

## Bulletins de paie : immutabilité inconditionnelle

Un bulletin (`bulletins_paie`) n'existe que pour une période déjà
**VALIDEE**. Une fois inséré :

- **UPDATE** : bloqué en toutes circonstances (trigger `RAISE(ABORT, ...)`)
- **DELETE** : bloqué en toutes circonstances (trigger `RAISE(ABORT, ...)`)

Il n'y a pas de condition d'exception : un bulletin généré est un fait
historique. Toute correction nécessaire après génération implique de
produire un nouveau document (avenant, régularisation), jamais de
réécrire un bulletin existant.
