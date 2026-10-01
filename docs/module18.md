# Module 18 — Automatisation & génération massive

## 1. Architecture

```
pages/17_Automatisation.py       (orchestration UI uniquement)
        |
services/automatisation_service.py   (indépendant de Streamlit)
        |
        +-- services/controle_paie_service.py          (module 09 — préconditions, jamais dupliqué)
        +-- services/bulletin_service.py                (module 07 — génération, jamais dupliqué)
        +-- services/document_service.py                (module 14 — registre, idempotence)
        +-- services/document_integrity_service.py      (module 14 — intégrité)
        +-- services/archive_service.py                 (module 14 — archive CLOTUREE)
        +-- services/alert_service.py                   (module 16 — notification, jamais dupliqué)
        |
        v
services/paie_service.py   (seule source des formules — jamais dupliquée)
```

Le module 18 est **strictement une couche d'orchestration**. Aucune
nouvelle table SQL : le suivi d'une opération (`OperationAutomatisation`)
est un objet en mémoire retourné à l'appelant ; sa trace durable passe
par l'audit déjà existant (module 11) et, pour les opérations
produisant des fichiers, un `Manifest.json` — même convention que
`archive_service.py` (module 14). Ce choix architectural évite une
deuxième persistance parallèle et reste cohérent avec la structure
existante du projet, qui n'a jamais eu de dossier `database/migrations/`
séparé.

## 2. Workflow principal

```
Sélection période → Préconditions → Dry run → Génération massive →
Vérification d'intégrité → Archive/Pack → Rapport d'exécution
```

Chaque étape est une fonction indépendante du service, appelable
séparément.

## 3. Préconditions

`verifier_preconditions` réutilise intégralement
`controle_paie_service.controler_periode` (aucune règle de contrôle
dupliquée) et vérifie la présence du template Word déjà utilisé par
`bulletin_service`. Une erreur bloquante du contrôle de paie bloque
l'automatisation ; un avertissement ne bloque pas.

## 4. Dry run (aperçu)

`analyser_generation_bulletins` **n'écrit jamais rien** — vérifié par
test. Classifie chaque enseignant en `pret` / `deja_existant` /
`erreur_potentielle`, à partir d'une seule requête groupée sur le
registre documentaire (jamais une requête par enseignant — section 30).

**Limite documentée honnêtement** : `calculer_paie_enseignant`
(module 03/06) est volontairement permissif — un enseignant sans
aucune donnée saisie ne lève pas d'erreur, il produit un résultat à
zéro. La classification `erreur_potentielle` se déclenche donc
rarement en pratique (période/enseignant introuvable, période
BROUILLON) ; ce n'est pas un défaut du module 18 mais un
comportement hérité, volontairement non modifié pour ne rien casser.

## 5. Génération massive et idempotence (section 10)

`generer_bulletins_massif` vérifie, pour chaque enseignant, si un
bulletin est **déjà enregistré au registre documentaire** pour cette
période : si oui, il est **ignoré par défaut** — jamais de création
aveugle de `Bulletin_X_2.docx`. Testé et confirmé : une génération
relancée deux fois sur les mêmes données produit toujours exactement
le même nombre de fichiers.

Avec `forcer_regeneration=True`, le comportement habituel de
`bulletin_service` reprend la main (versionnement automatique pour
une période modifiable, refus pur et simple si la période est
CLOTUREE — règle des modules 07/12, jamais contournée).

## 6. Isolation des erreurs (section 9)

Chaque enseignant est traité dans son propre bloc `try/except` : une
panne sur l'un n'interrompt jamais le traitement des autres — testé
explicitement avec une panne simulée au milieu d'un lot.

## 7. Reprise ciblée (section 25)

`reprendre_erreurs` ne retraite que les enseignants en erreur de
l'opération précédente — jamais les succès déjà obtenus. Lève
`AutomatisationError` si aucune erreur n'est à reprendre (testé).

## 8. Pack de paie (section 13/14)

`creer_pack_paie` assemble un ZIP à partir des documents **déjà
enregistrés** au registre (bulletins, exports, rapports groupés en
sous-dossiers), avec un `Manifest.json` et un `README.txt` — ne
génère ni ne recalcule rien de nouveau. Jamais d'écrasement (suffixe
numérique automatique), jamais de mot de passe dans le manifeste
(vérifié par test).

## 9. Archive massive et vérification d'intégrité

Délégations directes, sans aucune logique propre :
- `archiver_periode_massif` → `archive_service.archiver_periode` (module 14) : période CLOTUREE strictement exigée, testé.
- `verifier_integrite_periode` → `document_integrity_service.verifier_integrite_complete` (module 14).

## 10. Alertes (section 22)

En cas d'erreurs lors d'une génération massive, une alerte
`AUTOMATISATION_ERREURS` est créée via `alert_service.creer_ou_mettre_a_jour_alerte`
(module 16) — aucun moteur d'alertes parallèle. Aucune alerte n'est
créée pour un traitement pleinement réussi (testé), pour ne pas
transformer chaque opération normale en notification.

## 11. Audit (section 21)

`AUTOMATISATION_PREPAREE` et `GENERATION_MASSIVE_BULLETINS` déclenchés
systématiquement, via le système d'audit existant (module 11) —
testé pour les deux événements.

## 12. Permissions

`automatisation.executer` (ADMIN + GESTIONNAIRE_PAIE, refusée à
CONSULTATION, testé) — matrice centrale du module 11.

## 13. Annulation — limite documentée

**Aucune annulation en cours d'exécution n'est proposée.** Chaque
bulletin est généré et enregistré individuellement (déjà
transactionnel au niveau ligne par `bulletin_service`), donc une
interruption n'entraîne jamais d'état incohérent — mais il n'existe
pas de bouton « annuler » qui stopperait un traitement en cours.
Documenté plutôt que simulé, conformément à la consigne du cahier
des charges.

## 14. Performance (section 30)

Chargement groupé des enseignants et des documents existants (deux
requêtes au total, jamais une par enseignant) avant la boucle de
traitement.

## 15. Cas de référence

100 h × 2 000 FCFA → **Net = 208 250 FCFA**, confirmé à travers une
génération massive de bout en bout.

## 16. Guide utilisateur

1. Choisir la période dans la page **Automatisation**.
2. Vérifier les préconditions affichées.
3. Cliquer sur **Simuler** pour un aperçu sans écriture.
4. Cliquer sur **Générer les bulletins** — les documents déjà
   existants sont automatiquement ignorés.
5. En cas d'erreurs, cliquer sur **Reprendre uniquement les erreurs**.
6. Vérifier l'intégrité, créer l'archive (période clôturée) ou le
   pack de paie complet selon le besoin.

## 17. Tests

`tests/test_automatisation_service.py` (25 tests) : préconditions,
dry run, idempotence, isolation d'erreur, reprise ciblée, alertes,
audit, pack de paie, archive massive, permissions, cas de référence.
