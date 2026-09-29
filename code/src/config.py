"""
Configuration centrale du pipeline MobiCity E05.
Tout paramètre chiffré (seuils contrat, bornes qualité, fuseau) est défini ici
et nulle part ailleurs : un seul endroit à défendre devant le jury, un seul
endroit à modifier si le contrat change.
"""
import os
from pathlib import Path

# --- Chemins -----------------------------------------------------------------
BASE = Path(__file__).resolve().parents[1]   # racine du projet (là où sont src/, app/…)

# Sources brutes (lecture seule) = le dossier "donnees" du projet MobiCity_E05.
# On cherche automatiquement, dans l'ordre :
#   1. la variable d'environnement MOBICITY_DATA (si définie)
#   2. <projet>/donnees            (code déposé DANS MobiCity_E05)
#   3. <projet>/../donnees         (code dans un sous-dossier du projet)
#   4. <projet>/../MobiCity_E05/donnees   (projet voisin)
def _find_data_src():
    if os.environ.get("MOBICITY_DATA"):
        return Path(os.environ["MOBICITY_DATA"])
    for c in (BASE / "donnees",
              BASE.parent / "donnees",
              BASE.parent / "MobiCity_E05" / "donnees"):
        if c.exists():
            return c
    return BASE / "donnees"   # défaut : à la racine du projet

DATA_SRC = _find_data_src()
HIST      = DATA_SRC / "historique"
REF       = DATA_SRC / "referentiels"
DEPOTS    = DATA_SRC / "depots_quotidiens"

WAREHOUSE = BASE / "data" / "warehouse.duckdb"           # entrepôt DuckDB
LAKE      = BASE / "data" / "lake"                        # Parquet partitionné (bronze/silver)
QUARANTINE= BASE / "data" / "quarantaine"                # lignes rejetées + motif
REPORTS   = BASE / "data" / "rapports"                    # rapports qualité (csv/json)
# Livrable 3 : documentation technique, générée à côté de code/ dans l'archive E05.
DOSSIER   = BASE.parent / "dossier"
# Partie 2 : sorties de la chaîne quotidienne.
BULLETINS = BASE / "data" / "bulletins"    # bulletins de 7 h 30 (HTML)
JOURNAL   = BASE / "data" / "journal"       # journal d'exécution structuré (JSONL)
for d in (LAKE, QUARANTINE, REPORTS, BULLETINS, JOURNAL, WAREHOUSE.parent):
    d.mkdir(parents=True, exist_ok=True)

# --- Fuseau ------------------------------------------------------------------
# La télémétrie est en UTC (suffixe 'Z'). Trajets et recherches sont en heure
# locale naïve. On ramène tout à Europe/Paris, référence des décisions de Karim.
TZ_LOCAL = "Europe/Paris"

# --- Contrat VoltaService (contrat_recharge.json) ----------------------------
SEUIL_ALERTE_PCT      = 20     # batterie déclenchant l'alerte
SEUIL_UTILISABLE_PCT  = 15     # en-dessous : engin inutilisable
DELAI_MAX_H           = 4      # délai contractuel d'intervention
PLAGE_DEBUT           = "07:00"
PLAGE_FIN             = "21:00"
PENALITE_EUR          = 12.0   # par intervention hors délai
REMUNERATION_EUR      = 6.5    # par intervention

# --- Bornes de qualité -------------------------------------------------------
BATTERIE_MIN, BATTERIE_MAX = 0, 100
ENUM_RESULTAT_RECHERCHE = ("trajet_demarre", "aucun_engin", "abandon")
ENUM_STATUT_TELEMETRIE  = ("disponible", "en_course", "hors_service")
# Types d'engins dotés d'une batterie (pour qui une batterie NULL est un défaut).
# 'velo' = vélo mécanique : batterie NULL est normale, pas une erreur.
TYPES_ELECTRIQUES = ("velo_elec", "trottinette")

# --- RGPD --------------------------------------------------------------------
# Sel de pseudonymisation. En production il vient d'un secret hors dépôt ;
# ici il est fixe pour rendre les résultats reproductibles pendant l'épreuve.
SALT = "mobicity-e05-sel-demo"
