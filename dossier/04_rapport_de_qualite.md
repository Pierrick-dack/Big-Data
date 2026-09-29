# 04 — Rapport de qualité

Deux gravités : **bloquante** (ligne mise en quarantaine avec motif) et **informative**
(ligne conservée mais signalée). Généré depuis la table `qualite_rapport`.

## Catalogue des règles
| Source | Regle | Gravite | Total | Cas | Taux % |
|---|---|---|---|---|---|
| interventions | R00 déduplication (id_intervention) | info | 11656 | 0 | 0.0 |
| interventions | R30 date d'alerte illisible | bloquante | 11656 | 0 | 0.0 |
| interventions | R31 engin absent du référentiel | bloquante | 11656 | 0 | 0.0 |
| interventions | R32 batterie après < avant | info | 11656 | 0 | 0.0 |
| recherches | R00 déduplication (recherche_id) | info | 84308 | 16250 | 19.27 |
| recherches | R10 horodatage illisible | bloquante | 68058 | 1 | 0.0 |
| recherches | R11 résultat hors nomenclature | bloquante | 68058 | 0 | 0.0 |
| recherches | R12 nb_engins_affichés absent | info | 68057 | 0 | 0.0 |
| telemetrie | R00 déduplication (engin_id,ts) | info | 1612800 | 0 | 0.0 |
| telemetrie | R20 batterie hors [0,100] (neutralisée) | info | 1268736 | 4800 | 0.38 |
| telemetrie | R21 batterie absente sur engin électrique (signalée) | info | 1268736 | 309120 | 24.36 |
| telemetrie | R22 statut hors nomenclature | bloquante | 1612800 | 0 | 0.0 |
| trajets | R00 déduplication (trajet_id) | info | 62771 | 741 | 1.18 |
| trajets | R01 date début/fin manquante | bloquante | 62030 | 3630 | 5.85 |
| trajets | R02 incohérence temporelle (fin<=début) | bloquante | 62030 | 0 | 0.0 |
| trajets | R03 montant absent ou négatif | bloquante | 62030 | 469 | 0.76 |
| trajets | R04 durée absente ou nulle | bloquante | 62030 | 471 | 0.76 |
| trajets | R05 engin absent du référentiel | bloquante | 62030 | 0 | 0.0 |
| trajets | R06 station absente du référentiel | bloquante | 62030 | 255 | 0.41 |
| trajets | R07 client absent du référentiel | info | 57519 | 312 | 0.54 |
| trajets | R08 durée déclarée ≠ (fin-début) | info | 57519 | 322 | 0.56 |

## Taux de rejet par source
| Source | Conformes | Quarantaine | Rejet % |
|---|---|---|---|
| interventions | 11656 | 0 | 0.0 |
| recherches | 68057 | 0 | 0.0 |
| telemetrie | 1612800 | 0 | 0.0 |
| trajets | 57519 | 4758 | 7.64 |

Fichiers : `data/rapports/rapport_qualite.csv`, `data/quarantaine/quarantaine.csv`
(chaque ligne rejetée avec source, clé, règle, gravité).
