"""Backfill de l'historique (20/07 -> 13/09). Construit l'entrepôt DuckDB."""
import glob
from . import config as C
from .etl import Pipeline

def historical_sources():
    return {
        "trajets":       sorted(glob.glob(f"{C.HIST}/trajets/*.csv")),
        "recherches":    sorted(glob.glob(f"{C.HIST}/recherches_app/*.jsonl")),
        "telemetrie":    sorted(glob.glob(f"{C.HIST}/telemetrie/*.jsonl.gz")),
        "interventions": sorted(glob.glob(f"{C.HIST}/interventions_recharge/*.csv")),
        "meteo":         sorted(glob.glob(f"{C.HIST}/meteo/*.json")),
        "maintenance":   sorted(glob.glob(f"{C.HIST}/maintenance/*.json")),
    }

def main():
    p = Pipeline()
    p.init_quarantine()
    print("Référentiels (+ pseudonymisation RGPD)…")
    p.load_referentiels()
    print("Bronze — ingestion fidèle + lignage…")
    p.bronze(historical_sources())
    print("Silver — normalisation + dédup + intégrité + qualité + RGPD…")
    p.run_silver()
    p.write_quality_report()
    print("Parquet — matérialisation partitionnée de la couche Silver…")
    p.export_parquet()
    # Export des livrables qualité (rapport + quarantaine avec motifs).
    # as_posix() -> chemins en '/' pour rester compatibles Windows dans le SQL.
    rapport = (C.REPORTS / "rapport_qualite.csv").as_posix()
    quaran  = (C.QUARANTINE / "quarantaine.csv").as_posix()
    p.sql(f"COPY (SELECT * FROM qualite_rapport ORDER BY source,regle) TO '{rapport}' (HEADER)")
    p.sql(f"COPY (SELECT * FROM quarantaine ORDER BY source,regle) TO '{quaran}' (HEADER)")
    # On n'affiche que des chemins RELATIFS (anonymat : aucun chemin machine dans les logs).
    print("Termine. Entrepot        : data/warehouse.duckdb")
    print("Rapport qualite          : data/rapports/rapport_qualite.csv")
    print("Quarantaine (motifs)     : data/quarantaine/quarantaine.csv")
    print("Parquet Silver partitionne: data/lake/")
    p.con.close()   # libère le verrou pour l'étape suivante (Gold)
    return p

if __name__ == "__main__":
    main()
