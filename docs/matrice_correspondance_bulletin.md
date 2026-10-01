# Matrice de correspondance — Bulletin de solde Word (Module 07)

Correspondance exacte entre le modèle de bulletin de l'établissement, les
classes/champs réels du projet, et les placeholders du template.

## Champs variables

| Champ du modèle | Source (classe.champ réel) | Service intermédiaire | Placeholder Word |
|---|---|---|---|
| Nom | `Enseignant.nom` | `ResultatPaie.nom` (via `paie_service.calculer_paie_enseignant`) | `{{NOM}}` |
| Prénom | `Enseignant.prenom` | `ResultatPaie.prenom` | `{{PRENOM}}` |
| Statut (V/P) | `Enseignant.statut` (`StatutEnseignant`, déjà `"V"`/`"P"` en base — aucune conversion de valeur, uniquement lecture de `.value`) | `ResultatPaie.statut` | `{{STATUT}}` |
| Période | `PeriodePaie.libelle` | lu directement depuis `periode_repository.obtenir_par_id` dans `bulletin_service` | `{{PERIODE}}` |
| Semaine 1 à 5 | `SaisieHeures.heures_effectuees` (par `numero_semaine`) | `ResultatPaie.semaine_1` … `semaine_5` | *(non affichées individuellement — voir note ci-dessous)* |
| Total heures | dérivé des 5 semaines, jamais stocké séparément | `ResultatPaie.total_heures` | `{{TOTAL_HEURES}}` |
| Taux horaire | `Enseignant.taux_horaire` | `ResultatPaie.taux_horaire` | `{{TAUX_HORAIRE}}` |
| Gain Heures / Hourly Wage | `total_heures × taux_horaire` (calculé **uniquement** dans `paie_service`) | `ResultatPaie.gain_heures` | `{{GAIN_HEURES}}` |
| Prime AP/PP / Incentive HOD/CM | `ElementRemuneration` (`type_element='prime_ap_pp'`) | `ResultatPaie.prime_ap_pp` | `{{PRIME_AP_PP}}` |
| Surveillance/Secretariat / Invigilation | `ElementRemuneration` (`type_element='surveillance_secretariat'`) | `ResultatPaie.surveillance_secretariat` | `{{SURVEILLANCE_SECRETARIAT}}` |
| Indemnite Suggestion / Duty Post Allowance | `ElementRemuneration` (`type_element='indemnite_suggestion_admin'`) | `ResultatPaie.indemnite_suggestion_admin` | `{{INDEMNITE_SUGGESTION_ADMIN}}` |
| Taxe / Tax | `base_taxable × TAUX_TAXE` (calculé **uniquement** dans `paie_service`) | `ResultatPaie.taxe_5` | `{{TAXE_5}}` |
| Retenue Amicale / Social Deduction | `Retenue` (`type_retenue='retenue_amicale'`) | `ResultatPaie.retenue_amicale` | `{{RETENUE_AMICALE}}` |
| Dette / Debt | `Retenue` (`type_retenue='dette'`) | `ResultatPaie.dette` | `{{DETTE}}` |
| Total (ligne agrégée) | — | `base_taxable` / `base_taxable − net_a_percevoir` (soustraction entre deux résultats déjà finaux, pas une formule de paie) | `{{TOTAL_GAINS}}` / `{{TOTAL_RETENUES}}` |
| NET A PAYER | `paie_service` (formule officielle unique) | `ResultatPaie.net_a_percevoir` | `{{NET_A_PERÇEVOIR}}` |
| Montant en lettres | dérivé de `net_a_percevoir`, jamais d'un autre montant | `utils.montant_en_lettres.montant_en_lettres(resultat.net_a_percevoir)` | `{{NET_EN_LETTRES}}` |
| Date (signature) | date de génération du bulletin (aucune date officielle dédiée sur `PeriodePaie`) | `datetime.now()` au moment de la génération | `{{DATE_GENERATION}}` |

**Note semaines 1 à 5** : le modèle officiel ne comporte pas de ligne dédiée par
semaine (une seule ligne "Gain Heures / Hourly Wage" avec heures, taux, gain).
Conformément à la consigne explicite du module 07 ("ne pas déformer le modèle
pour les ajouter"), les 5 semaines ne sont pas affichées individuellement,
mais restent disponibles sur `ResultatPaie.semaine_1..5` pour un usage futur
(export détaillé, audit).

## Champs fixes (texte institutionnel, non variables)

Reproduits tels quels dans `templates/build_template.py`, désormais lus
depuis `config/settings.py` (`ETABLISSEMENT_ENTETE_FR/EN`,
`LIEU_SIGNATURE`, `TITRE_SIGNATAIRE_FR/EN`) plutôt que codés en dur :
République du Cameroun / Republic of Cameroon, devises bilingues, région,
délégations régionale et départementale, nom de l'établissement,
BULLETIN DE SOLDE / PAYSLIP, intitulés
de rubriques bilingues, bloc signature.

## Champs absents de la base (non inventés)

| Champ | Source actuelle | Disponible | Solution retenue |
|---|---|---|---|
| Logo de l'établissement | Aucune | NON | Espace réservé dans l'en-tête (cellule centrale), laissé vide plutôt que d'inventer un graphique. Un chemin d'image pourra être ajouté en configuration si le fichier est fourni. |
| Nom du signataire ("Coordonateur Général") | Aucune | NON | Seul le **titre de fonction** (déjà présent dans le modèle) est reproduit ; aucun nom n'est inventé. Zone de signature laissée vide pour signature manuscrite. |
| Adresse / téléphone de l'établissement | Aucune | NON | Non présents dans le modèle officiel fourni ; non ajoutés (rien à reproduire ni à inventer). |
| Date administrative dédiée à la période | `PeriodePaie` n'a que `mois`/`annee`/`libelle` | NON | Date de génération du bulletin utilisée à la place, comme explicitement autorisé par la consigne d'origine du module 07. |
