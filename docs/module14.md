# Module 14 — Gestion documentaire, archivage et recherche

## 1. Architecture documentaire

Aucune restructuration des dossiers existants (`data/exports/`,
`data/exports/bulletins/{periode}/`, conventions de nommage du module
07) — le module 14 ajoute une couche de **traçabilité** par-dessus,
sans rien déplacer.

```
services/document_service.py        (registre : enregistrement, recherche, hash)
services/document_integrity_service.py  (VALIDE / MANQUANT / MODIFIE / ORPHELIN)
services/archive_service.py          (ZIP + manifest, vérification, extraction sécurisée)
        |
        v
database: table `documents` (registre léger, ne duplique pas bulletins_paie)
```

## 2. Registre documentaire

Table `documents` (additive) : `type_document`, `nom_fichier`,
`chemin`, `enseignant_id`, `periode_id`, `date_creation`,
`utilisateur`, `taille`, `hash_fichier`. Ne duplique **jamais** les
données de paie déjà présentes dans `bulletins_paie` (snapshot
immuable, module 12) — cette table référence uniquement
l'emplacement et l'intégrité d'un fichier, jamais son contenu métier.

## 3. Types de documents

`BULLETIN`, `RAPPORT_PAIE`, `ETAT_PAIE`, `EXPORT_EXCEL`
(`models/enums.TypeDocument`). `RAPPORT_PAIE` est défini mais non
encore produit par l'application (aucun générateur de rapport dédié
n'existe à ce stade) — conservé pour un usage futur, conformément à la
liste demandée.

## 4. Nommage et non-écrasement

Convention `Bulletin_NOM_PRENOM_PERIODE.docx` (module 07) conservée à
l'identique. `chemin_sortie_disponible` (déjà existant, modules 06/07)
continue de garantir qu'aucune génération n'écrase silencieusement un
fichier existant — versionnage automatique par suffixe numérique déjà
en place, réutilisé tel quel.

## 5. Hash et intégrité (SHA-256)

`document_service.calculer_hash_fichier` : lecture par blocs de 64 Ko
(jamais tout le fichier en mémoire), calculé à l'enregistrement et
recalculable à la demande. Deux niveaux de vérification, séparés pour
la performance (section 38) :
- `etat_leger` : présence uniquement (utilisé par le diagnostic
  courant du module 10 — jamais de hash recalculé à chaque page).
- `verifier_integrite` : hash complet (réservé au bouton dédié
  « Vérifier l'intégrité maintenant »).

Les 4 statuts (VALIDE / MANQUANT / MODIFIE / ORPHELIN) sont testés
individuellement.

## 6. Câblage dans les générateurs existants

`bulletin_service.generer_bulletin_enseignant`,
`exports/excel_export.generer_fichier_excel`,
`exports/reporting_export.generer_fichier_etat_paie` enregistrent
désormais chaque document produit — **best-effort**, jamais bloquant :
une erreur du registre ne fait jamais échouer une génération déjà
réussie. Paramètres additionnels (`utilisateur`) rétrocompatibles
(valeur par défaut `None`, aucun appelant existant cassé).

L'audit `GENERATION_BULLETIN`, provisionné depuis le module 01 mais
jamais utilisé, est désormais activé à chaque génération de bulletin —
même schéma que la découverte répétée à chaque module précédent
(`CLOTURE_PERIODE`, `VALIDATION_PERIODE`, `RESTAURATION_SAUVEGARDE`).

## 7. Archivage (section 21-25)

`archive_service.archiver_periode` : refuse toute période dont le
statut n'est pas exactement CLOTUREE (testé sur BROUILLON, OUVERTE,
VALIDEE). Produit `Archive_Paie_{PERIODE}.zip` avec sous-dossiers
`Bulletins/`, `Etats/`, `Rapports/` et un `manifest.json` (établissement,
période, statut, date, utilisateur, liste des documents avec hash) —
**aucun mot de passe ni donnée d'authentification**, vérifié par test.
Les documents référencés en base mais absents du disque sont signalés
sans bloquer l'archivage.

`verifier_archive` : ZIP lisible, manifest présent et valide, fichiers
annoncés présents, hash conformes — testé avec une archive
corrompue et avec un fichier falsifié après archivage (hash invalide
détecté).

## 8. Sécurité — protection contre le path traversal (section 26/27)

`extraire_archive_securise` : chaque membre du ZIP est résolu par
rapport au dossier de destination ; tout chemin qui en sortirait
(`../`, chemin absolu) est **rejeté et journalisé**, jamais extrait.
Testé explicitement avec `../../../evil.txt` et un chemin absolu
(`/etc/passwd_faux`) — dans les deux cas, aucun fichier n'est jamais
créé hors du dossier prévu.

## 9. Diagnostic (module 10, étendu)

`nombre_documents`, `documents_manquants`, `taille_documents_octets`
ajoutés à `DiagnosticSysteme` — calcul **léger** uniquement (existence
de fichier, jamais de hash recalculé pour l'ensemble du registre à
chaque ouverture de page). Erreurs documentaires affichées séparément
des erreurs SQLite dans la page Administration.

## 10. Sauvegarde (section 36)

**Important** : `backup_service.creer_sauvegarde()` (module 10) ne
sauvegarde **que** la base SQLite — comportement strictement inchangé
et toujours vrai. Une nouvelle fonction séparée,
`creer_sauvegarde_complete()`, produit `Backup_Complet_{date}.zip`
incluant à la fois la base et les documents, pour les cas où une
sauvegarde complète est explicitement nécessaire.

## 11. Permissions (module 11, réutilisées)

`document.consulter` (3 rôles), `document.archiver` et
`document.exporter` (ADMIN + GESTIONNAIRE_PAIE) — intégrées à la
matrice centrale, aucun système parallèle.

## 12. Audit (réutilisé)

`GENERATION_BULLETIN`, `EXPORT_COMPTABLE` (activés, provisionnés
depuis le module 01), `DOCUMENT_ARCHIVE`, `DOCUMENT_INTEGRITE_VERIFIEE`,
`DOCUMENT_TELECHARGE`, `ARCHIVE_CREEE` (additifs). `DOCUMENT_SUPPRIME`
et `ARCHIVE_RESTAUREE` sont définis mais non déclenchés dans cette
version — voir section 14 ci-dessous.

## 13. Points volontairement hors périmètre de cette version

- **Suppression de document** : aucune fonction de suppression
  physique n'est exposée. Le module 14 privilégie explicitement
  l'archivage (section 29 : « pour les documents associés à une
  période clôturée, privilégier l'archivage plutôt que la
  suppression ») ; implémenter une suppression sûre (permission
  dédiée, confirmation, interaction avec l'immutabilité de
  `bulletins_paie`) est laissé à une itération future plutôt que
  risqué dans cette passe.
- **Réimport d'une archive dans la base** : `extraire_archive_securise`
  restaure les FICHIERS de façon sûre ; la ré-création des lignes
  `documents`/`bulletins_paie` correspondantes n'est pas implémentée,
  pour ne jamais risquer de contourner l'immutabilité stricte de
  `bulletins_paie` (module 12).

## 14. Cas de référence

100 h × 2 000 FCFA → **Net = 208 250 FCFA**, confirmé à travers le
cycle complet incluant génération de bulletin, enregistrement au
registre et archivage.

## 15. Tests

`tests/test_document_service.py` (14), `tests/test_document_integrity_service.py` (11),
`tests/test_archive_service.py` (14, dont path traversal), ajouts aux
tests de permissions (3), audit (8), backup (3), diagnostic (3).
