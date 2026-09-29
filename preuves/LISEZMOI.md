# Preuves

- `execution_pipeline.log` : rejeu complet de la chaîne (build + 14/09 x2 + reprise sur
  erreur + 15/09 bloqué + 15/09 repris). Les codes de sortie y figurent.
- `journal_executions.jsonl` : journal structuré (étape, statut, durée, volumes) de chaque
  exécution, avec l'incident du 15/09 et sa reprise.
- `bulletin_2026-09-14.html`, `bulletin_2026-09-15.html` : bulletins de 7 h 30 produits.
- `rapport_qualite.csv` : règles, gravité, volumes et taux de rejet par source.
- `quarantaine_extrait.csv` : échantillon des lignes écartées, avec la règle en cause.
- `top_stations_non_servies.csv`, `respect_contrat_mensuel.csv`, `indicateurs_apercu.txt` :
  aperçu des indicateurs.
- `captures/` : captures d'écran de l'interface (à compléter).

Toutes ces preuves sont régénérables en rejouant `build.py` puis `jour.py` (voir README).
