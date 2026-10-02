# Matrice de correspondance — Bulletin de solde

Correspondance entre le bulletin officiel de l'établissement, les champs
calculés par l'application et les balises des modèles de bulletin.
Liste complète et à jour : `utils/balises_bulletin.py` (affichée dans
Administration › Modèles de bulletin).

## Champs variables

| Zone du bulletin officiel | Source | Balise |
|---|---|---|
| Nom et prénoms (bande jaune) | `Enseignant.nom`, `Enseignant.prenom` (majuscules) | `{{NOM_COMPLET}}` (ou `{{NOM}}` `{{PRENOM}}`) |
| Statut: V / P | `Enseignant.statut` ; pour une période validée ou clôturée, statut de l'instantané du bulletin | `{{STATUT}}` (`{{STATUT_LIBELLE}}` : Vacataire / Permanent) |
| Mois (bande verte, en anglais) | `PeriodePaie.mois`, `PeriodePaie.annee` -> « JULY 2026 » | `{{PERIODE}}` (`{{PERIODE_FR}}` : libellé français) |
| Gain Heures : heures, taux, montant | `ResultatPaie.total_heures`, `taux_horaire`, `gain_heures` | `{{TOTAL_HEURES}}`, `{{TAUX_HORAIRE}}`, `{{GAIN_HEURES}}` |
| Prime AP/PP | `ResultatPaie.prime_ap_pp` | `{{PRIME_AP_PP}}` |
| Surveillance/Secretariat | `ResultatPaie.surveillance_secretariat` | `{{SURVEILLANCE_SECRETARIAT}}` |
| Indemnite Suggestion | `ResultatPaie.indemnite_suggestion_admin` | `{{INDEMNITE_SUGGESTION_ADMIN}}` |
| Taxe | `ResultatPaie.taxe_5` = base taxable × taux de la période | `{{TAXE}}` (`{{TAXE_TAUX}}` : « 5,5 % ») |
| Retenue Amicale | `ResultatPaie.retenue_amicale` | `{{RETENUE_AMICALE}}` |
| Dette | `ResultatPaie.dette` | `{{DETTE}}` |
| Total gains / Total retenues | `base_taxable` / `base_taxable − net_a_percevoir` | `{{TOTAL_GAINS}}` / `{{TOTAL_RETENUES}}` |
| NET A PAYER (chiffres, lettres anglaises) | `ResultatPaie.net_a_percevoir` | `{{NET_A_PAYER}}`, `{{NET_EN_LETTRES}}` |
| Semaines 1 à 5 (absentes du bulletin officiel) | `ResultatPaie.semaine_1..5` | `{{SEMAINE_1}}` … `{{SEMAINE_5}}` |
| Date (absente du bulletin officiel : date manuscrite) | date de génération | `{{DATE}}` |

Noms historiques toujours acceptés : `{{TAXE_5}}`, `{{NET_A_PERÇEVOIR}}`,
`{{DATE_GENERATION}}`, `{{BASE_TAXABLE}}`.

Montants : entiers FCFA sans séparateur de milliers (« 18000 »), comme sur
le bulletin officiel. Aucune formule de paie hors de `services/paie_service.py`.

## Éléments fixes du modèle standard

En-tête bilingue (`config/settings.py` : `ETABLISSEMENT_ENTETE_FR/EN`), logo de
l'établissement (`assets/logo_etablissement.png`, fichier local exclu de Git),
intitulés des rubriques, « Done at Yaoundé on the / Fait à Yaoundé le: »
(`LIEU_SIGNATURE`), titre du signataire (`TITRE_SIGNATAIRE_FR/EN`). Le nom du
signataire n'est pas inventé ; la date et la signature restent manuscrites.

## Fichiers

| Fichier | Rôle |
|---|---|
| `templates/build_template.py` | construit les deux modèles standard (dimensions relevées sur le PDF officiel) |
| `templates/bulletin_template.docx` | modèle Word standard (balises historiques) |
| `templates/bulletin_modele_standard.pdf` + `.json` | modèle PDF standard et ses zones |
| `data/modeles_bulletin/` | modèles importés (table `modeles_bulletin`) |
