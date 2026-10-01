# Module 17 — Statistiques avancées & analyse décisionnelle

## 1. Objectif

Ajouter une couche d'analyse statistique et décisionnelle permettant
au responsable de répondre rapidement à des questions comme « quel
est le taux horaire moyen ? », « quelle différence entre vacataires et
permanents ? », « quelles valeurs sont atypiques ? » — sans jamais
recalculer une formule de paie déjà définie ailleurs.

## 2. Architecture

```
pages/16_Statistiques.py       (orchestration UI uniquement)
        |
services/statistiques_service.py   (indépendant de Streamlit)
        |
        +-- services/comptabilite_service.preparer_etat_comptable   (module 06)
        +-- services/reporting_paie_service.py                       (module 13, réutilisé tel quel)
        +-- services/historique_paie_service.historique_enseignant   (module 08/12)
        |
        v
services/paie_service.py   (seule source des formules — jamais dupliquée)
```

`exports/statistiques_export.py` (nouveau, séparé des autres modules
d'export pour ne jamais risquer de les régresser) réutilise les
styles déjà définis.

## 3. Ce qui est réutilisé sans duplication

- **Synthèses par statut/par sexe** : `reporting_paie_service.synthese_detaillee_par_statut/par_sexe`
  réutilisées telles quelles (module 13). Le module 17 n'ajoute que le
  croisement à deux dimensions (`synthese_croisee_statut_sexe`),
  absent du module 13.
- **Classement des enseignants** : `reporting_paie_service.classer_enseignants`
  réutilisé directement pour tout tri (volume horaire, rémunération, taux).
- **Filtrage** : `reporting_paie_service.filtrer_resultats` réutilisé
  tel quel dans la page.
- **Historique multi-périodes d'un enseignant** : `historique_paie_service.historique_enseignant`
  réutilisé tel quel pour l'analyse individuelle.
- **Résultats de paie** : toujours obtenus via
  `comptabilite_service.preparer_etat_comptable`, jamais recalculés.

## 4. Ce qui est réellement nouveau (module 17)

- Statistique descriptive robuste (moyenne, médiane, écart-type,
  quartiles) via le module standard `statistics` — aucune nouvelle
  dépendance ajoutée (déjà disponible dans l'environnement Python).
- Détection de valeurs atypiques (méthode IQR).
- Analyse d'évolution multi-périodes avec variations sécurisées.
- Croisement statut × sexe.
- Comparaison d'un enseignant à la moyenne de son groupe.

## 5. Méthodes statistiques

**Statistique descriptive** : moyenne, médiane (module `statistics`),
écart-type (`statistics.stdev`, nécessite ≥ 2 observations — `None`
sinon, jamais une exception), quartiles (`statistics.quantiles`,
nécessite ≥ 4 observations).

**Détection d'outliers — IQR** :
`Q1`, `Q3`, `IQR = Q3 - Q1`, bornes à `Q1 - 1,5×IQR` / `Q3 + 1,5×IQR`.
Nécessite au moins 4 observations ; sinon, liste vide plutôt qu'un
faux positif.

## 6. Terminologie prudente sur les valeurs atypiques

**Une valeur atypique n'est jamais présentée comme une erreur
métier.** Le champ `niveau` d'une `ValeurAtypique` est toujours
« À vérifier » — jamais « erreur » ni « anomalie ». Une valeur peut
être parfaitement légitime (ex. un enseignant à très fort volume
horaire). Testé explicitement (`test_outlier_terminologie_prudente`).

## 7. Gestion des données vides et robustesse

Toutes les fonctions du service sont testées sur : liste vide, une
seule observation, valeurs identiques, période sans donnée
exploitable, groupe vide, dénominateur nul (jamais de division par
zéro — vérifié pour les variations de période ET les écarts
individuels).

## 8. Filtres (page)

Période, statut, sexe — combinables, via
`reporting_paie_service.filtrer_resultats` (aucune logique de
filtrage dupliquée).

## 9. Graphiques

Générés à partir des structures déjà calculées par le service
(`st.bar_chart`, `st.line_chart`) — aucun calcul dans la couche
graphique elle-même.

## 10. Export Excel

`Statistiques_{PERIODE}.xlsx` : feuilles Synthese, Enseignants,
Par_Statut, Par_Sexe, Composantes, et Par_Periode/Outliers si
disponibles. Jamais d'écrasement (suffixe numérique automatique).

## 11. Permissions et audit

`statistiques.consulter` (3 rôles), `statistiques.exporter` (ADMIN +
GESTIONNAIRE_PAIE) — matrice centrale du module 11. Le module 17 est
strictement en lecture : aucune écriture de donnée de paie, donc
aucun événement d'audit propre n'est nécessaire (cohérent avec les
autres modules de reporting en lecture seule, ex. module 13).

## 12. Intégration au module 16 (alertes)

Le module 17 **ne crée aucune alerte lui-même** et ne recrée aucun
moteur — une valeur atypique reste une information analytique
affichée sur la page Statistiques. Si une alerte automatique devait
un jour être créée à partir d'une détection statistique, elle
passerait par `alert_service.creer_ou_mettre_a_jour_alerte`, sans
nouveau service parallèle (conformément à la consigne).

## 13. Intégration au module 12 (immutabilité)

Le service est strictement en lecture (aucune fonction n'écrit de
donnée de paie). Une période clôturée peut être analysée normalement,
sans jamais que son statut ou ses données ne soient modifiés.

## 14. Limites statistiques

- L'écart-type et les quartiles ne sont pas définis mathématiquement
  en dessous de 2 (resp. 4) observations : les champs correspondants
  restent `None` plutôt que d'afficher une valeur trompeuse.
- La détection IQR est une heuristique standard, pas un test
  statistique formel de significativité — elle sert à orienter
  l'attention, jamais à conclure automatiquement à une erreur.
- Le module ne calcule pas de projections ni de prévisions futures :
  il documente l'existant et son évolution passée.

## 15. Cas de référence

100 h × 2 000 FCFA → **Net = 208 250 FCFA**, retrouvé à l'identique
dans les statistiques générales et l'export Excel.

## 16. Tests

`tests/test_statistiques_service.py` (11), `tests/test_statistiques_periodes.py` (7),
`tests/test_statistiques_groupes.py` (10), `tests/test_statistiques_export.py` (7).
