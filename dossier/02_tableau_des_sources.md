# 02 — Tableau des sources

Historique : 2026-07-20 → 2026-09-13 (56 jours). Volumes comptés dans la couche Bronze.

## Volumes
| Source | Volume (lignes) |
|---|---|
| Trajets | 62 771 |
| Recherches | 84 308 |
| Telemetrie | 1 612 800 |
| Interventions | 11 656 |
| Meteo (releves) | 224 |
| Maintenance (tickets) | 136 |

Référentiels (autorité) : 600 engins, 58 stations, 9 000 clients, 1 contrat.

## Format, sensibilité, criticité
| Source | Format | Sensibilité RGPD | Criticité pour le bulletin |
|---|---|---|---|
| Trajets | CSV (1/jour) | Élevée (client, paiement) | Moyenne — usage réel, panier moyen |
| Recherches | JSONL (1/jour) | Élevée (client + position GPS) | Haute — seule source de la demande non servie |
| Télémétrie | JSONL gzip (1/jour) | Faible (engin) | Critique — batterie = engins à recharger |
| Interventions | CSV « ; » (1/jour) | Moyenne (nom technicien) | Haute — suivi du contrat de recharge |
| Météo | JSON (1/jour) | Nulle | Faible — variable explicative |
| Maintenance | JSON (1/semaine) | Faible | Moyenne — fiabilité des engins |

## Qualité observée (mesurée)
- **Dates trajets au format mélangé** : ISO 47 031, français 9 510,
  epoch Unix 4 380, nulles 1 850. Comparées en texte, ~18 %
  semblent incohérentes ; après normalisation, 0 le sont réellement.
- **Batterie manquante** : normale sur les vélos mécaniques, anormale sur les trottinettes
  (capteur) → traitée au niveau du champ, pas par rejet de ligne.
- **Villes bruitées** (17 variantes en télémétrie) → ville reprise du référentiel.
- **Interventions** : CSV « ; » avec BOM, dates FR, villes MAJUSCULES, clé engin préfixée `MC-`.
