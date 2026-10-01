# Module 16 — Notifications, alertes et surveillance opérationnelle

## 1. Architecture

```
pages/15_Notifications.py           (orchestration UI uniquement)
        |
services/alert_service.py            (cycle de vie : création, déduplication, transitions)
services/alert_detection_service.py  (orchestration : traduit les résultats existants en alertes)
        |
        +-- services/controle_paie_service.py         (module 09, jamais dupliqué)
        +-- services/document_integrity_service.py    (module 14, jamais dupliqué)
        +-- services/diagnostic_service.py             (module 10, jamais dupliqué)
        +-- services/backup_service.py                 (module 10, jamais dupliqué)
        +-- services/periode_service.py                (module 12, jamais contourné)
```

**Séparation stricte des responsabilités** (section 47) :
`alert_service.py` ne détecte rien — il gère uniquement le cycle de
vie d'une alerte déjà décidée. `alert_detection_service.py` ne
contient aucune règle de contrôle propre — il appelle les services
existants et traduit leurs résultats. Le module 16 est une couche
d'orchestration et de notification, jamais un second moteur.

## 2. Modèle d'une alerte

Table `alertes` (additive) : `type_alerte`, `niveau`
(INFO/AVERTISSEMENT/ERREUR/CRITIQUE), `titre`, `message`, `source`,
`cle_deduplication`, `statut`, `date_creation`,
`date_derniere_detection`, `periode_id`/`enseignant_id`/`document_id`/
`import_id` (tous optionnels), `utilisateur_concerne`,
`date_acquittement`/`acquitte_par`, `date_resolution`/`resolue_par`.

`ON DELETE CASCADE` (plutôt que `RESTRICT`) sur les clés étrangères :
une alerte n'a plus de sens une fois l'objet supprimé, et `RESTRICT`
aurait bloqué à tort des suppressions déjà strictement protégées par
ailleurs (modules 08/09) pour la seule raison qu'une alerte les
référence — décision documentée pour ne jamais introduire de
régression sur ces suppressions déjà validées.

## 3. Déduplication (section 13)

Double protection :
1. **Applicative** : `alert_service.creer_ou_mettre_a_jour_alerte` recherche
   d'abord une alerte ACTIVE (ni résolue ni ignorée) portant la même
   `cle_deduplication` (type + période + enseignant + document + import) ;
   si elle existe, seule sa date de dernière détection est rafraîchie.
2. **Base de données** : un index UNIQUE PARTIEL
   (`idx_alertes_dedup_active ... WHERE statut NOT IN ('resolue','ignoree')`)
   empêche physiquement deux alertes actives identiques, même en cas
   d'appel concurrent.

Testé avec un volume de 60 alertes générées deux fois de suite :
toujours exactement 60 lignes, jamais de doublon.

## 4. Statuts et transitions (section 12)

```
NOUVELLE -> LUE -> ACQUITTEE -> RESOLUE
(NOUVELLE | LUE | ACQUITTEE) -> IGNOREE
toute alerte active -> RESOLUE (résolution automatique)
```

Toute transition hors de cette table est explicitement refusée
(`AlertServiceError`) — testé (ex. ACQUITTEE → LUE, RESOLUE → LUE,
IGNOREE → ACQUITTEE).

## 5. Résolution automatique (section 14)

`alert_service.resoudre_alertes_obsoletes(source, cles_encore_actives)` :
pour une source donnée, toute alerte encore active dont la clé
n'apparaît plus parmi les anomalies de la dernière analyse passe à
RESOLUE. **L'historique n'est jamais supprimé** — la ligne reste, avec
sa date de résolution. Testé pour le contrôle de paie (anomalie
corrigée) et les documents (fichier régénéré).

## 6. Catalogue des alertes

| Source | Type | Niveau | Origine |
|---|---|---|---|
| enseignants | TAUX_HORAIRE_NUL | Avertissement | lecture directe |
| periodes | PERIODE_BROUILLON | Info | `periode_service` |
| controle_paie | CONTROLE_{code} | Erreur/Avertissement | `controle_paie_service.controler_periode` |
| documents | DOCUMENT_MANQUANT | Erreur | `document_integrity_service` |
| documents | DOCUMENT_MODIFIE | Avertissement | `document_integrity_service` |
| documents | DOCUMENT_ORPHELIN | Info | `document_integrity_service` |
| administration | AUCUNE_SAUVEGARDE / SAUVEGARDE_ANCIENNE | Avertissement | `backup_service` |
| administration | SYSTEME_ETAT_ROUGE | Critique | `diagnostic_service` |
| import | IMPORT_ANOMALIE | Avertissement/Erreur | synthèse (jamais par ligne) |

Un état normal (période BROUILLON, import pleinement réussi) ne
génère jamais d'ERREUR — au pire une INFO, souvent rien.

## 7. Permissions et audit

`alerte.consulter` (3 rôles), `alerte.gerer` (ADMIN + GESTIONNAIRE_PAIE,
refusée à CONSULTATION) — matrice centrale du module 11. Audit sur
ACQUITTEE/RESOLUE/IGNOREE (`alerte_acquittee`, `alerte_resolue`,
`alerte_ignoree`, `alerte_creee`) ; la simple lecture n'est
volontairement pas auditée (même politique que la consultation de
page ailleurs dans l'application).

## 8. Intégration au module 12 (périodes clôturées)

Une alerte peut informer qu'une période est clôturée, mais aucune
fonction de ce module n'écrit jamais de donnée de paie — vérifié par
test explicite : la détection sur une période clôturée ne modifie
jamais son statut.

## 9. Performance (section 25/42)

Deux niveaux de vérification distincts pour l'intégrité documentaire
(hérités du module 14) : léger (existence de fichier) pour l'affichage
courant, complet (hash) uniquement sur action explicite. La détection
elle-même n'est déclenchée que par une action explicite (bouton
« Analyser maintenant ») ou après une opération significative (import),
jamais à chaque affichage.

## 10. Cas de référence

100 h × 2 000 FCFA → **Net = 208 250 FCFA**, confirmé à travers le
cycle complet (ouverture → saisie → validation → clôture → bulletin →
détection d'alertes).

## 11. Guide utilisateur

1. La page **Notifications** affiche la synthèse par niveau.
2. Cliquer sur **Analyser maintenant** (ADMIN/GESTIONNAIRE_PAIE)
   pour lancer une détection complète.
3. Filtrer par niveau, statut, période, enseignant ou texte libre.
4. Ouvrir une alerte pour voir son contexte complet (quoi, pourquoi,
   où, quand).
5. Marquer lue, acquitter, résoudre ou ignorer selon le cas.
6. Exporter la liste filtrée en Excel si besoin.

## 12. Tests

`tests/test_alert_service.py` (24 : création, déduplication,
transitions, audit, résolution automatique, permissions),
`tests/test_alert_detection_service.py` (20 : intégration avec les
modules 09/10/12/14/15, performance sur volume).
