# Bulletin officiel, modèles de bulletin, taux de taxe, statut — notes techniques

Version 1.1.0 (évolution de la 1.0.0) : aucune formule de paie modifiée hors de
`services/paie_service.py` (le taux y est désormais celui de la période), aucun
module ni bloc de navigation ajouté, aucun test supprimé.

## 1. Bulletin officiel reproduit à l'identique

- `templates/build_template.py` reconstruit le bulletin officiel de l'établissement :
  grille de 7 colonnes et hauteurs de lignes relevées sur le PDF (en points),
  vert `#00B050`, jaune `#FFFF00`, Times New Roman gras 11 (en-tête 7 et 9),
  signature Arial gras, logo `assets/logo_etablissement.png` (fichier local,
  exclu de Git ; seulement avec `--etablissement`),
  mois en anglais, montants sans séparateur, date et signature manuscrites.
- Modèle Word : `templates/bulletin_template.docx` (balises historiques).
- Modèle PDF : `templates/bulletin_modele_standard.pdf` = bulletin rempli de
  valeurs d'exemple (nom générique), converti par LibreOffice sur le poste du
  développeur ; zones dans `bulletin_modele_standard.json`, obtenues par la
  même détection que les bulletins importés.

## 2. Modèles de bulletin importés

| Fichier | Rôle |
|---|---|
| `utils/balises_bulletin.py` | catalogue des balises, alias historiques, contrôle |
| `utils/detection_bulletin.py` | propositions de correspondances (intitulé + position sur la ligne) |
| `exports/word_export.py` | balises partout (tableaux imbriqués, en-têtes), segments, conversion d'un bulletin rempli |
| `exports/pdf_export.py` | segments, zones, effacement réel + réécriture (PyMuPDF) |
| `services/modele_bulletin_service.py` | analyse, construction, essai, import, activation, suppression, repli |
| `services/administration_service.py` | accès ADMIN vérifié côté service |

Table `modeles_bulletin`, fichiers dans `data/modeles_bulletin/`, modèle actif dans
`parametres_paie` (`modele_bulletin_actif`, défaut `standard_docx`). Un bulletin
d'essai complet est produit avant tout enregistrement. Le modèle PDF enregistré
ne conserve pas les valeurs du bulletin envoyé (zones effacées).

Nouvelle dépendance : `pymupdf` (lecture et écriture PDF). Licence AGPL : sans
incidence pour un usage interne ; à examiner si le logiciel était redistribué.

## 3. Taux de taxe paramétrable

- `periodes_paie.taux_taxe` (TEXT, défaut `'0.05'`), ajoutée aux bases
  existantes par `database/migrations.ajouter_colonnes_manquantes` (périodes
  existantes : 5 %, donc résultats identiques).
- Trigger `trg_periodes_paie_taux_fige` : taux non modifiable une fois la
  période validée ou clôturée.
- `parametres_paie` (`taux_taxe_defaut`) : taux recopié à la création d'une
  période ; `services/parametres_paie_service.py` ; permission
  `PARAMETRES_PAIE_GERER` (ADMIN).
- `paie_service._calculer_resultat(..., taux_taxe=...)` ; `ResultatPaie.taux_taxe`.
- Vérifié : 10 h × 1 800 FCFA à 5,5 % -> taxe 990, net 17 010 ;
  cas de référence à 5 % -> 208 250 FCFA inchangé.

## 4. Statut d'un enseignant

`enseignant_service.changer_statut_enseignant` (onglet « Changer le statut »),
journalisé (`statut_enseignant_modifie`), également journalisé lorsqu'il passe par
le formulaire de modification. Pour une période validée ou clôturée, le bulletin
reprend le statut de l'instantané `bulletins_paie` s'il existe.

## 5. Réinitialisation des données

`parametres_paie` et `modeles_bulletin` sont conservées (et les fichiers des
modèles). Entrées d'audit conservées : import / activation / suppression de
modèle, changement du taux par défaut.

## 6. Tests adaptés

`tests/test_bulletin_service.py` : deux assertions attendaient le libellé
français de la période dans le bulletin ; le bulletin officiel l'écrit en
anglais (« SEPTEMBER 2030 »). Nouveaux fichiers : `test_taux_taxe.py`,
`test_modeles_bulletin.py`, `test_statut_enseignant.py`.

## Taxe réservée aux vacataires (version 1.6.0)

- `services/paie_service.py` : taxe = base taxable × taux de la période pour un
  vacataire, 0 pour un permanent (`ResultatPaie.taux_taxe` vaut alors 0).
- Taux par défaut : `config.settings.TAUX_TAXE = Decimal("0.055")`.
- Colonne `periodes_paie.taxe_permanents` : 1 = ancienne règle (taxe pour tous).
  La migration l'ajoute avec la valeur 1 (aucune ligne modifiée, une période
  clôturée ne l'est jamais), puis passe à 0 les périodes en brouillon ou ouvertes.
  Trigger `trg_periodes_paie_regle_taxe_figee` : la règle d'une période validée
  ou clôturée ne change plus.
- Tests : `tests/test_taxe_vacataires.py`.
