# Suppression de données — désactivation vs suppression définitive

## Deux mécanismes bien distincts

| | Désactivation | Suppression définitive |
|---|---|---|
| Portée | Enseignant uniquement | Enseignant **ou** période |
| Réversible | Oui (réactivation) | **Non** |
| Effet | `actif = 0`, ligne conservée | Ligne physiquement retirée de la base |
| Historique | Toujours consultable | Bloquée si un historique existe (bulletin) |

La désactivation reste, dans les deux cas, la voie normale pour retirer
un enseignant ou figer une période sans perdre son historique.

## Suppression définitive d'un enseignant

`services/enseignant_service.supprimer_enseignant_definitivement(enseignant_id, confirmation=True)`

**Autorisée si** : aucun bulletin n'a jamais été généré pour cet
enseignant, toutes périodes confondues.

**Interdite si** : au moins un bulletin existe. Message :
> Cet enseignant possède un historique de paie. Pour préserver la
> traçabilité des salaires, il ne peut pas être supprimé
> définitivement. Vous pouvez le désactiver.

**Détection des bulletins** : combine deux sources — `bulletins_paie`
(table SQL, prévue pour une persistance future non encore alimentée
par le module 07 actuel) et le système de fichiers réel
(`services/bulletin_service.enseignant_a_des_bulletins`, qui inspecte
`data/exports/bulletins/*/`). *Correction apportée lors de cette
session* : ne vérifier que la table SQL laissait passer tous les
bulletins réellement générés par le module 07 (qui produit des
fichiers `.docx`, jamais de ligne en base) — ce bug est désormais
corrigé et couvert par deux tests dédiés.

**Transaction** : heures, rémunérations et retenues de l'enseignant
sont supprimées, puis l'enseignant lui-même, dans une seule
transaction SQLite. Toute erreur déclenche un `ROLLBACK` complet.

**Confirmation** : `confirmation=True` obligatoire côté service ; côté
interface (`pages/1_Enseignants.py`), l'administrateur doit **taper le
nom complet exact** de l'enseignant avant que le bouton de
confirmation ne s'active.

**Audit** : une entrée `SUPPRESSION_DEFINITIVE` est journalisée dans
`audit_log`, qu'elle aboutisse ou soit refusée (nom, prénom, résultat).

## Suppression définitive d'une période

`services/periode_service.supprimer_periode_definitivement(periode_id, confirmation=True)`

**Autorisée si et seulement si** :
- la période est au statut **BROUILLON**, **et**
- aucun bulletin n'a jamais été généré pour cette période (tout
  enseignant confondu).

**Interdite dans tous les autres cas**, notamment :
- au moins un bulletin existe (quel que soit le statut) ;
- la période est OUVERTE, VALIDEE ou CLOTUREE.

Ce choix s'appuie sur une propriété déjà garantie par l'architecture
existante : la saisie de données de paie (heures, rémunérations,
retenues) exige que la période soit OUVERTE — une période BROUILLON ne
peut donc, par construction, jamais avoir accumulé la moindre donnée
de paie (vérifié par test : une tentative d'INSERT direct en SQL sur
une période BROUILLON échoue déjà au niveau du trigger). Restreindre
la suppression au seul statut BROUILLON revient ainsi à ne jamais
autoriser la suppression d'une période ayant servi à une paie réelle,
ce qui satisfait pleinement l'exigence de protection de l'historique —
y compris pour OUVERTE, refusée par prudence même si elle a pu
recevoir des données depuis sa création.

Cette règle est appliquée **à deux niveaux** (défense en profondeur) :
- au niveau service (message clair, contrôlé avant toute écriture) ;
- au niveau base de données, via le trigger déjà présent
  `trg_periodes_paie_suppression_limitee` (fondation du module 03),
  qui rejette toute suppression d'une période dont le statut n'est pas
  `brouillon` — même en cas de bug applicatif, la donnée reste protégée.

**Transaction** : suppression des heures, rémunérations et retenues de
**tous les enseignants** liés à la période, puis de la période
elle-même, dans une seule transaction SQLite. `ROLLBACK` complet en
cas d'erreur à n'importe quelle étape (vérifié par test, y compris via
l'API publique du service).

**Confirmation** : `confirmation=True` obligatoire côté service ; côté
interface (`pages/2_Periodes_Paie.py`), l'administrateur doit taper
exactement `SUPPRIMER <LIBELLÉ DE LA PÉRIODE EN MAJUSCULES>`.

**Audit** : entrée `SUPPRESSION_DEFINITIVE` journalisée (libellé de la
période, résultat), qu'elle réussisse ou soit refusée.

## Ce qui n'est jamais supprimé automatiquement

Un bulletin généré (fichier `.docx` sur disque) n'est **jamais**
supprimé par cascade, ni par la suppression d'un enseignant, ni par
celle d'une période — c'est précisément la raison pour laquelle sa
présence bloque ces deux suppressions.

## Export filtré du tableau de bord

`services/dashboard_service.exporter_consultation_excel(periode_id, enseignant_ids=...)`

Corrige un comportement où un export avec plusieurs enseignants
filtrés retombait silencieusement sur l'export complet de la période
(l'ancienne signature n'acceptait qu'un seul `enseignant_id`, jamais
une liste). Désormais :
- `enseignant_ids=None` : aucun filtre actif, export complet.
- une liste d'un identifiant : export nominatif
  (`Consultation_Paie_{NOM}_{PRENOM}_{periode}.xlsx`).
- une liste de plusieurs identifiants : export limité à cette
  sélection (`Consultation_Paie_Filtree_{periode}.xlsx`).
- une liste vide : erreur explicite, aucun fichier généré.
