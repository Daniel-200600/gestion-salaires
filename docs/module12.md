# Module 12 — Cycle de paie avancé, clôture et immutabilité des données

## 1. Objectif

Garantir formellement le cycle BROUILLON → OUVERTE → VALIDEE →
CLOTUREE, et s'assurer qu'une période clôturée devient effectivement
non modifiable — pas seulement affichée comme telle.

## 2. Ce qui existait déjà (audité, réutilisé sans duplication)

L'audit préalable a montré que le projet protégeait déjà, depuis les
modules 03/04/08/09, l'essentiel de ce que ce module demande :
- **INSERT/UPDATE bloqués** sur `saisies_heures`, `elements_remuneration`,
  `retenues` sauf statut exactement `ouverte`, à la fois au niveau
  service (`utils.validators.verifier_periode_ouverte`) et au niveau
  trigger SQL — double protection déjà en place.
- **Aucune fonction de suppression individuelle** exposée par les
  services de saisie : la seule suppression possible passe par les
  cascades déjà protégées de `enseignant_service`/`periode_service`.
- **Suppression de période** déjà restreinte à BROUILLON sans
  bulletin (modules 08/09), inchangée ici.
- **Table `bulletins_paie`** : présente depuis la fondation du projet
  avec un schéma de snapshot complet et des triggers d'immutabilité
  totale (`UPDATE`/`DELETE` interdits), mais **jamais réellement
  alimentée** par le module 07. C'est exactement le mécanisme de
  snapshot demandé en section 11 — il ne manquait que le câblage.

## 3. Machine à états — `services/periode_service.py` (additif)

- `est_modifiable(periode)` / `verifier_periode_modifiable(periode)` /
  `est_cloturee(periode)` : source de vérité unique, exposée sous un
  nom explicite, mais reflétant exactement la même règle que
  `utils.validators.verifier_periode_ouverte` (documenté en
  commentaire croisé pour ne jamais diverger).
- `transition_autorisee(statut_actuel, statut_cible)` /
  `TRANSITIONS_AUTORISEES` : formalise la machine à états déjà
  appliquée par `ouvrir_periode`/`valider_periode`/`cloturer_periode`
  et par le trigger SQL `trg_periodes_paie_transition_invalide`.

## 4. Workflow avec audit complet — `services/controle_paie_service.py`

- `ouvrir_periode_avec_audit(periode_id, utilisateur=None)` (nouveau) :
  transition BROUILLON → OUVERTE, journalisée (`PERIODE_OUVERTE`).
- `valider_periode_avec_controle` / `cloturer_periode_avec_controle`
  (module 09, étendues ici) : journalisent désormais aussi les
  **refus** (`VALIDATION_REFUSEE`/`CLOTURE_REFUSEE`, avec le motif),
  et acceptent un paramètre `utilisateur` propagé à chaque entrée
  d'audit — auparavant, seuls les succès étaient tracés, et jamais
  avec l'utilisateur ayant agi.

## 5. Instantané immuable des bulletins — section 11/13

`database/repositories/bulletin_repository.enregistrer_snapshot()` :
- N'insère que si la période est VALIDEE ou CLOTUREE (imposé par le
  trigger SQL déjà existant `trg_bulletins_paie_requiert_periode_validee`) —
  silencieusement ignoré sinon (la génération de bulletin pour une
  période OUVERTE reste possible comme depuis le module 07, mais ne
  produit alors aucun instantané).
- Idempotent : un second appel pour le même couple
  (enseignant, période) est silencieusement ignoré — le premier
  instantané fait foi (contrainte `UNIQUE`).
- Totalement immuable une fois créé (`UPDATE`/`DELETE` interdits par
  trigger, vérifié par test).
- Colonne additive `utilisateur_generation` : trace qui a généré le
  bulletin.

`services/bulletin_service.generer_bulletin_enseignant`/`generer_bulletins_groupe`
acceptent désormais un paramètre `utilisateur` optionnel, propagé
depuis `pages/6_Bulletins_Paie.py` (session du module 11).

## 6. Contrôle avant validation/clôture

Inchangé : `controler_periode()` (module 09) reste l'unique source de
détection d'anomalies, réutilisée telle quelle avant toute validation
ou clôture — aucune duplication.

## 7. Permissions (module 11, réutilisées sans changement)

`PERIODE_GERER` (ouverture), `PAIE_VALIDER`, `PAIE_CLOTURER` (réservée
à ADMIN — la matrice fournie laissait le choix pour
GESTIONNAIRE_PAIE ; la règle la plus restrictive a été conservée,
conformément à la consigne en cas d'ambiguïté).

## 8. Nouvelle page — `pages/11_Cycle_Paie.py`

État actuel, progression visuelle (✓/●/○), actions disponibles selon
permissions (ouverture directe ; validation/clôture redirigent vers
« Contrôle de la paie » du module 09, pour ne jamais dupliquer cet
écran de confirmation), aperçu des totaux avant clôture, historique
du cycle reconstruit depuis l'audit existant.

## 9. Dashboard et historique (légèrement enrichis)

- Tableau de bord : liste compacte du statut de toutes les périodes.
- Historique de paie : colonnes Statut et Date de clôture ajoutées au
  tableau existant, sans toucher à la comparaison entre périodes.

## 10. Base de données (additif uniquement)

- 3 types d'audit (`periode_ouverte`, `validation_refusee`,
  `cloture_refusee`).
- Colonne `utilisateur_generation` sur `bulletins_paie`.
- Aucune table supprimée, aucune donnée existante affectée.

## 11. Point d'attention documenté (aucune régression introduite)

La suppression définitive d'un enseignant (module 08, inchangée ici)
purge toutes ses données, y compris sur une période clôturée, **tant
qu'aucun bulletin n'a été généré pour lui** — c'est la même règle
qu'avant ce module. Ce n'est pas une brèche nouvelle : c'est un choix
déjà fait et testé au module 08, que le module 12 ne modifie pas
(modifier cette règle aurait risqué de casser la cascade de
suppression déjà validée par de nombreux tests).

## 12. Cas de référence

100 h × 2 000 FCFA → **Net = 208 250 FCFA**, vérifié à travers le
cycle complet (ouverture → saisie → validation → clôture), avec
traçabilité utilisateur à chaque étape.
