# 08 — Automatisation : tâche, gain et chaîne

## Tâche automatisée
Le bulletin d'exploitation du matin, préparé jusqu'ici à la main à partir de plusieurs exports.
La chaîne le produit automatiquement à partir du dépôt de 5 h.

## Gain
- Temps : d'environ 45 minutes de travail manuel à quelques secondes d'exécution automatique.
- Mise à disposition : bulletin prêt bien avant 7 h 30, sans intervention.
- Fiabilité : traitement idempotent, contrôles bloquants avant publication, reprise automatique
  sur erreur transitoire, journal horodaté de chaque exécution.

## Étapes de la chaîne
`ingestion → transformation → indicateurs → controle → publication` : chaque étape dépend de la
précédente. Pilotage en ligne de commande (journée à traiter, reprise à une étape, simulation),
détaillé dans la documentation d'exploitation.

## Porte qualité (contrôle bloquant avant publication)
- Couverture : les trois sources critiques du jour (télémétrie, trajets, recherches) sont présentes.
- Doublons du dépôt : au-delà de 30 %, la chaîne suspecte une ré-émission en double, bloque la
  publication et prévient l'exploitation ; reprise avec `--accepter-doublons` après confirmation.
- Cohérence : le nombre d'engins suivis ne dépasse pas la flotte du référentiel.

## Journées de démonstration
- 14/09 traité deux fois : la seconde exécution ne duplique rien et ne refait aucun travail.
- 15/09 : dépôt ré-émis (environ 51 % de doublons) → publication bloquée, exploitation prévenue,
  reprise après confirmation. Le journal `data/journal/executions.jsonl` conserve la trace des
  exécutions, de l'incident et de la reprise.

## Branchement de l'interface
Chaque exécution reconstruit les couches lues par l'interface : le tableau de bord se met donc à
jour à chaque passage. La page d'accueil affiche la fraîcheur (dernière journée publiée) et le
périmètre, et chaque indicateur est comparé à la moyenne de l'historique.
