# E05 — Application d'analyse et d'automatisation (mobilité partagée)

Chaîne décisionnelle **Bronze → Silver → Gold**, interface d'analyse, et **chaîne
quotidienne automatisée** qui produit le bulletin de 7 h 30. Poste local, sans
service payant. Tout se régénère depuis le code et les données : l'archive ne
contient ni les données sources, ni les couches produites.

## Contenu
```
E05/
├── README.md
├── requirements.txt
├── code/
│   ├── build.py     # construit l'historique (couches + indicateurs + dossier)
│   ├── jour.py      # chaîne quotidienne : traite une journée jusqu'au bulletin
│   ├── src/         # config, etl, gold, run_backfill, build_dossier,
│   │                #   orchestrateur, run_jour, bulletin
│   └── app/         # interface Streamlit (accueil + pages/)
├── dossier/         # documentation technique (Markdown, régénérée par build.py)
└── preuves/         # journal d'exécution, bulletins produits, rapports
```

## Prérequis
- Python 3.11 ou plus.
- Le dossier `donnees/` fourni par l'épreuve, placé **à côté de `code/`** (racine `E05/`).
  Sinon, définir la variable `MOBICITY_DATA` vers son chemin.

Mis au point avec Python 3.12, duckdb 1.5, streamlit 1.64, pandas 2/3, altair 6.

## Exécution
Depuis la racine `E05/` :
```bash
python -m pip install -r requirements.txt
cd code
python build.py                              # 1) historique : couches + indicateurs + dossier
python jour.py --date 2026-09-14             # 2) traite une journée (bulletin de 7 h 30)
python jour.py --date 2026-09-15             #    (bloquée : dépôt ré-émis, voir ci-dessous)
python -m streamlit run app/streamlit_app.py # 3) interface (accueil + bulletin)
```

## Chaîne quotidienne (Partie 2)
`python jour.py --date AAAA-MM-JJ` déroule : ingestion → transformation → indicateurs
→ contrôle → publication. Options :
- `--dry-run` : simuler sans rien écrire.
- `--depuis <etape>` : reprendre à une étape (ingestion, transformation, indicateurs, controle, publication).
- `--accepter-doublons` : publier malgré une ré-émission confirmée.
- `--force` : retraiter une journée déjà publiée.

Codes de sortie : 0 succès, 2 publication bloquée par la porte qualité, 3 données
manquantes, 4 erreur inattendue.

Exemples de démonstration :
- 14/09 lancé deux fois : la seconde exécution ne duplique rien (idempotence).
- 15/09 : dépôt ré-émis en double → publication bloquée, exploitation prévenue.
  Reprise : `python jour.py --date 2026-09-15 --accepter-doublons`.

Le journal est écrit dans `data/journal/executions.jsonl`, les bulletins dans
`data/bulletins/`.

> Windows / Python du Microsoft Store : utiliser `python build.py` et
> `python jour.py …`. La forme `python -m src.…` peut échouer avec cette variante.

## Notes
- Traitement idempotent : relancer sur les mêmes sources redonne le même résultat.
- Aucune donnée identifiante n'atteint les couches d'analyse ni les bulletins (voir `dossier/05_...`).
