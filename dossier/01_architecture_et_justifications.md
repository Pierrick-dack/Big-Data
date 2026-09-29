# 01 — Architecture et justifications

## Pile
Python, DuckDB, Streamlit, Parquet. Poste local, sans service payant. DuckDB lit
nativement CSV/JSON/gzip/Parquet et élague les partitions ; un seul fichier d'entrepôt.

## Couches (medallion)
- **Bronze** — ingestion fidèle et tracée (copie brute + lignage : nom du fichier source, horodatage).
- **Silver** — données propres : normalisation (dates multi-format, fuseau, clé engin, ville via
  référentiel), déduplication sur clé métier, intégrité, règles de qualité (quarantaine + drapeaux),
  RGPD. Matérialisée en Parquet partitionné par jour.
- **Gold** — tables d'indicateurs pré-agrégées, une par décision.

## Justification par la mesure
Cas testé : lire la batterie de tous les engins de la veille (2026-09-13).

| Approche | Temps | Données lues |
|---|---|---|
| Full-scan des fichiers bruts (.jsonl.gz) | 3038 ms | tout l'historique décompressé |
| Parquet partitionné (élagage) | 56 ms | 1 partition |

Accélération mesurée : **×54**. Sans partitionnement, le temps croît avec tout
l'historique ; avec, il reste borné à une journée — c'est ce qui sécurise le créneau du matin.

## Tenue à la charge 2027
Télémétrie actuelle : 28 800 lignes/jour (600 engins). Projection 2027
(3 000 engins, relevé 30 s) : 288 000 lignes/jour. Réponses : élagage par jour déjà en place,
sous-partitionnement par ville activable (ville déjà normalisée), format colonnaire.

## Reproductibilité
Le dossier `data/` (entrepôt, Parquet, rapports) n'est jamais édité à la main : il se
reconstruit intégralement depuis les sources par `run_backfill` puis `gold`.
