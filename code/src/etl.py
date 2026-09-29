"""
ETL MobiCity — Bronze -> Silver.

Principe : on NORMALISE avant de VALIDER. Beaucoup d'anomalies apparentes
(dates au format FR ou epoch, villes en majuscules, clé engin préfixée)
sont des problèmes de format, pas des données à jeter. Les jeter sans
normaliser ferait perdre ~18 % des trajets et ~40 % de la télémétrie.

Chaque étape est tracée :
  - Bronze : copie fidèle + colonnes de lignage (fichier source, horodatage
    d'ingestion). Aucune transformation.
  - Silver : données normalisées, dédupliquées, contrôlées par les règles de
    qualité, pseudonymisées. Les lignes non conformes partent en quarantaine
    avec leur motif ; on mesure le taux de rejet par source.

Le module fonctionne sur l'historique (backfill) comme sur un dépôt quotidien
(réutilisé en Partie 2) : c'est le paramètre `sources` qui change.
"""
import duckdb
import pathlib
from . import config as C

# Chemin sûr pour l'insertion dans une requête SQL : toujours des '/' (même sous
# Windows), sinon DuckDB interprète les '\' comme des caractères d'échappement.
def _p(chemin) -> str:
    return pathlib.Path(chemin).as_posix()

# Lignage : on ne conserve que le NOM du fichier source (ex. trajets_2026-07-20.csv),
# jamais son chemin complet — pour garder la traçabilité sans exposer d'information
# sur la machine (anonymat du rendu).
_SRCFILE = "regexp_replace(filename, '.*[/\\\\]', '')"

# --- Macros SQL réutilisables -----------------------------------------------

# Normalisation d'un horodatage texte multi-format -> TIMESTAMP heure locale.
# Fenêtre des données = été (CEST, UTC+2, sans changement d'heure) : la
# conversion UTC->local se fait par +2 h. LIMITE documentée : pour généraliser
# hors été il faudrait un vrai fuseau (extension ICU indisponible ici).
def _norm_ts(col: str) -> str:
    return f"""COALESCE(
        TRY_STRPTIME({col}, '%Y-%m-%d %H:%M:%S'),
        TRY_STRPTIME({col}, '%d/%m/%Y %H:%M'),
        CASE WHEN TRY_CAST({col} AS BIGINT) IS NOT NULL
             THEN make_timestamp(CAST({col} AS BIGINT)*1000000) + INTERVAL 2 HOUR END
    )"""

# Pseudonymisation : md5(sel || valeur). En production : HMAC-SHA256 + secret
# hors dépôt ; ici md5 + sel fixe pour la reproductibilité de l'épreuve.
def _pseudo(col: str) -> str:
    return f"CASE WHEN {col} IS NULL THEN NULL ELSE 'PX_' || substr(md5('{C.SALT}' || {col}), 1, 12) END"


class Pipeline:
    def __init__(self, db_path=C.WAREHOUSE, con=None):
        # con : connexion existante à réutiliser (l'orchestrateur en fournit une
        # pour éviter deux connexions concurrentes sur le même fichier).
        self.con = con or duckdb.connect(str(db_path))
        self.con.execute("SET TimeZone='UTC';")  # pas d'ICU : on gère l'offset à la main
        self._quar_rows = []   # accumulateur quarantaine
        self._qual_rows = []   # accumulateur rapport qualité

    # -- utilitaires ---------------------------------------------------------
    def sql(self, q):
        return self.con.execute(q)

    def _log_quality(self, source, regle, gravite, n_total, n_concernees):
        taux = round(100 * n_concernees / n_total, 2) if n_total else 0.0
        self._qual_rows.append((source, regle, gravite, n_total, n_concernees, taux))

    # ========================================================================
    #  RÉFÉRENTIELS (avec pseudonymisation + minimisation RGPD)
    # ========================================================================
    def load_referentiels(self):
        self.sql(f"""CREATE OR REPLACE TABLE ref_engins AS
            SELECT engin_id, type_engin, ville_affectation, modele, lot_batterie,
                   CAST(mise_en_service AS DATE) mise_en_service
            FROM read_csv_auto('{_p(C.REF/'engins.csv')}')""")
        self.sql(f"""CREATE OR REPLACE TABLE ref_stations AS
            SELECT station_id, nom, ville, latitude, longitude, capacite,
                   CAST(date_ouverture AS DATE) date_ouverture
            FROM read_csv_auto('{_p(C.REF/'stations.csv')}')""")
        # RGPD — clients : on pseudonymise l'identifiant et on ÉLIMINE toute
        # donnée identifiante (nom, prénom, email, téléphone, naissance).
        # On ne garde que ce qui sert aux analyses agrégées : ville, abonnement.
        self.sql(f"""CREATE OR REPLACE TABLE ref_clients AS
            SELECT {_pseudo('client_id')} AS client_px, ville_residence, abonnement,
                   CAST(date_inscription AS DATE) date_inscription
            FROM read_csv_auto('{_p(C.REF/'clients.csv')}')""")
        self.sql(f"""CREATE OR REPLACE TABLE ref_contrat AS
            SELECT * FROM read_json_auto('{_p(C.REF/'contrat_recharge.json')}')""")

    # ========================================================================
    #  BRONZE — ingestion fidèle + lignage
    # ========================================================================
    def bronze(self, sources: dict):
        """sources = {'trajets': [globs...], 'telemetrie': [...], ...}"""
        g = lambda lst: "[" + ",".join(f"'{_p(p)}'" for p in lst) + "]"

        self.sql(f"""CREATE OR REPLACE TABLE bronze_trajets AS
            SELECT *, {_SRCFILE} AS _source_file, now() AS _ingested_at
            FROM read_csv_auto({g(sources['trajets'])}, union_by_name=true,
                               all_varchar=true, filename=true)""")
        self.sql(f"""CREATE OR REPLACE TABLE bronze_recherches AS
            SELECT *, {_SRCFILE} AS _source_file, now() AS _ingested_at
            FROM read_json_auto({g(sources['recherches'])}, format='newline_delimited',
                                union_by_name=true, filename=true,
                                ignore_errors=true)""")   # ignore_errors : capte les lignes illisibles
        self.sql(f"""CREATE OR REPLACE TABLE bronze_telemetrie AS
            SELECT *, {_SRCFILE} AS _source_file, now() AS _ingested_at
            FROM read_json_auto({g(sources['telemetrie'])}, format='newline_delimited',
                                union_by_name=true, filename=true, ignore_errors=true)""")
        self.sql(f"""CREATE OR REPLACE TABLE bronze_interventions AS
            SELECT *, {_SRCFILE} AS _source_file, now() AS _ingested_at
            FROM read_csv_auto({g(sources['interventions'])}, delim=';',
                               union_by_name=true, all_varchar=true, filename=true)""")
        self.sql(f"""CREATE OR REPLACE TABLE bronze_meteo AS
            SELECT r.ville, CAST(r.date AS DATE) date, r.temp_c, r.pluie_mm, r.vent_kmh,
                   {_SRCFILE} AS _source_file, now() AS _ingested_at
            FROM read_json_auto({g(sources['meteo'])}, union_by_name=true, filename=true) t,
                 UNNEST(t.releves) AS u(r)""")
        if sources.get('maintenance'):
            self.sql(f"""CREATE OR REPLACE TABLE bronze_maintenance AS
                SELECT *, {_SRCFILE} AS _source_file, now() AS _ingested_at
                FROM read_json_auto({g(sources['maintenance'])}, union_by_name=true,
                                    filename=true)""")

    # ========================================================================
    #  SILVER — normalisation + dédup + intégrité + qualité + RGPD
    # ========================================================================
    def silver_trajets(self):
        db, fn = _norm_ts("debut"), _norm_ts("fin")
        # 1. normaliser + dédupliquer sur clé métier trajet_id (garde 1 occurrence)
        self.sql(f"""CREATE OR REPLACE TEMP TABLE _tr AS
            SELECT * FROM (
              SELECT
                trajet_id,
                {_pseudo('client_id')} AS client_px,
                engin_id,
                lower(type_engin) AS type_engin,
                (upper(substr(ville,1,1)) || lower(substr(ville,2))) AS ville,
                station_depart, station_arrivee,
                {db} AS debut, {fn} AS fin,
                TRY_CAST(duree_min AS INT) AS duree_min,
                TRY_CAST(distance_km AS DOUBLE) AS distance_km,
                TRY_CAST(montant_eur AS DOUBLE) AS montant_eur,
                moyen_paiement,
                _source_file,
                row_number() OVER (PARTITION BY trajet_id ORDER BY _ingested_at) AS _rn
              FROM bronze_trajets
            ) WHERE _rn = 1""")
        n_brut = self.con.execute("SELECT count(*) FROM bronze_trajets").fetchone()[0]
        n_dedup = self.con.execute("SELECT count(*) FROM _tr").fetchone()[0]
        self._log_quality("trajets", "R00 déduplication (trajet_id)", "info", n_brut, n_brut - n_dedup)

        # 2. règles de qualité -> quarantaine (bloquantes) / drapeaux (info)
        # Bloquantes : dates inutilisables, montant/durée invalides, incohérence temporelle réelle
        self._quarantine("trajets", "_tr", "trajet_id", [
            ("R01 date début/fin manquante",        "bloquante", "debut IS NULL OR fin IS NULL"),
            ("R02 incohérence temporelle (fin<=début)", "bloquante", "debut IS NOT NULL AND fin IS NOT NULL AND debut >= fin"),
            ("R03 montant absent ou négatif",       "bloquante", "montant_eur IS NULL OR montant_eur < 0"),
            ("R04 durée absente ou nulle",          "bloquante", "duree_min IS NULL OR duree_min <= 0"),
        ])
        # Intégrité référentielle (bloquante engin/station, info client)
        self._quarantine("trajets", "_tr_ok", "trajet_id", [
            ("R05 engin absent du référentiel",   "bloquante", "engin_id NOT IN (SELECT engin_id FROM ref_engins)"),
            ("R06 station absente du référentiel", "bloquante", "station_depart NOT IN (SELECT station_id FROM ref_stations) OR station_arrivee NOT IN (SELECT station_id FROM ref_stations)"),
        ], base_from="_tr")
        # Silver final = conformes, + drapeaux informatifs
        self.sql("""CREATE OR REPLACE TABLE silver_trajets AS
            SELECT t.* REPLACE (e.ville_affectation AS ville),
              (t.client_px NOT IN (SELECT client_px FROM ref_clients)) AS flag_client_inconnu,
              (t.duree_min IS NOT NULL AND abs(date_diff('minute',t.debut,t.fin)-t.duree_min) > 1) AS flag_duree_incoherente,
              CAST(t.debut AS DATE) AS jour, hour(t.debut) AS heure
            FROM _tr_ok t LEFT JOIN ref_engins e ON e.engin_id=t.engin_id""")
        # drapeaux informatifs -> rapport qualité (comptés, non rejetés)
        for regle, cond in [("R07 client absent du référentiel", "flag_client_inconnu"),
                            ("R08 durée déclarée ≠ (fin-début)", "flag_duree_incoherente")]:
            n = self.con.execute(f"SELECT count(*) FROM silver_trajets WHERE {cond}").fetchone()[0]
            tot = self.con.execute("SELECT count(*) FROM silver_trajets").fetchone()[0]
            self._log_quality("trajets", regle, "info", tot, n)

    def silver_recherches(self):
        # Dédup sur recherche_id (capte le renvoi du 15/09). RGPD : la position
        # GPS du client est SUPPRIMÉE (minimisation) ; on ne garde que la station.
        self.sql(f"""CREATE OR REPLACE TEMP TABLE _re AS
            SELECT * FROM (
              SELECT recherche_id,
                     TRY_CAST(ts AS TIMESTAMP) AS ts,
                     {_pseudo('client_id')} AS client_px,
                     (upper(substr(ville,1,1)) || lower(substr(ville,2))) AS ville,
                     station_id,
                     TRY_CAST(nb_engins_affiches AS INT) AS nb_engins_affiches,
                     resultat, trajet_id,
                     row_number() OVER (PARTITION BY recherche_id ORDER BY _ingested_at) AS _rn
              FROM bronze_recherches
            ) WHERE _rn = 1""")
        n_brut = self.con.execute("SELECT count(*) FROM bronze_recherches").fetchone()[0]
        n_dedup = self.con.execute("SELECT count(*) FROM _re").fetchone()[0]
        self._log_quality("recherches", "R00 déduplication (recherche_id)", "info", n_brut, n_brut - n_dedup)

        self._quarantine("recherches", "_re", "recherche_id", [
            ("R10 horodatage illisible", "bloquante", "ts IS NULL"),
            ("R11 résultat hors nomenclature", "bloquante",
             f"resultat NOT IN {C.ENUM_RESULTAT_RECHERCHE}"),
        ])
        self.sql("""CREATE OR REPLACE TABLE silver_recherches AS
            SELECT r.* REPLACE (s.ville AS ville),
              (r.nb_engins_affiches IS NULL) AS flag_nb_engins_absent,
              CAST(r.ts AS DATE) AS jour, hour(r.ts) AS heure
            FROM _re_ok r LEFT JOIN ref_stations s ON s.station_id=r.station_id""")
        n = self.con.execute("SELECT count(*) FROM silver_recherches WHERE flag_nb_engins_absent").fetchone()[0]
        tot = self.con.execute("SELECT count(*) FROM silver_recherches").fetchone()[0]
        self._log_quality("recherches", "R12 nb_engins_affichés absent", "info", tot, n)

    def silver_telemetrie(self):
        # ts en UTC (suffixe Z) -> heure locale (+2h, fenêtre été). Batterie NULL
        # tolérée pour les vélos mécaniques (pas de batterie), rejetée pour les
        # engins électriques (capteur défaillant : trottinettes ~50 % NULL).
        self.sql(f"""CREATE OR REPLACE TEMP TABLE _te AS
            SELECT * FROM (
              SELECT engin_id,
                     CAST(ts AS TIMESTAMP) + INTERVAL 2 HOUR AS ts,  -- UTC -> local (été, +2h)
                     TRY_CAST(lat AS DOUBLE) lat, TRY_CAST(lon AS DOUBLE) lon,
                     TRY_CAST(batterie_pct AS INT) AS batterie_pct,
                     TRY_CAST(vitesse_kmh AS DOUBLE) vitesse_kmh,
                     statut, (upper(substr(ville,1,1)) || lower(substr(ville,2))) AS ville,
                     row_number() OVER (PARTITION BY engin_id, ts ORDER BY _ingested_at) AS _rn
              FROM bronze_telemetrie
            ) WHERE _rn = 1""")
        n_brut = self.con.execute("SELECT count(*) FROM bronze_telemetrie").fetchone()[0]
        n_dedup = self.con.execute("SELECT count(*) FROM _te").fetchone()[0]
        self._log_quality("telemetrie", "R00 déduplication (engin_id,ts)", "info", n_brut, n_brut - n_dedup)

        # jointure type d'engin pour la règle batterie conditionnelle
        self.sql("""CREATE OR REPLACE TEMP TABLE _te2 AS
            SELECT t.* REPLACE (e.ville_affectation AS ville), e.type_engin,
                   (e.type_engin IN """ + str(C.TYPES_ELECTRIQUES) + """) AS est_electrique
            FROM _te t LEFT JOIN ref_engins e USING(engin_id)""")
        # Seule règle BLOQUANTE : statut hors nomenclature (ligne inexploitable).
        self._quarantine("telemetrie", "_te2", "engin_id || '@' || ts", [
            ("R22 statut hors nomenclature", "bloquante",
             f"statut NOT IN {C.ENUM_STATUT_TELEMETRIE}"),
        ])
        # La QUALITÉ BATTERIE est traitée AU NIVEAU DU CHAMP, pas de la ligne :
        # position/statut restent valides pour le rééquilibrage. On neutralise la
        # batterie douteuse (mise à NULL) et on pose un drapeau ; les indicateurs
        # de recharge filtrent sur batterie_fiable.
        self.sql(f"""CREATE OR REPLACE TABLE silver_telemetrie AS
            SELECT engin_id, ts, lat, lon,
              CASE WHEN batterie_pct < {C.BATTERIE_MIN} OR batterie_pct > {C.BATTERIE_MAX}
                   THEN NULL ELSE batterie_pct END AS batterie_pct,
              (NOT (batterie_pct IS NULL AND est_electrique)
                   AND NOT (batterie_pct < {C.BATTERIE_MIN} OR batterie_pct > {C.BATTERIE_MAX})
                   OR NOT est_electrique) AS batterie_fiable,
              vitesse_kmh, statut, ville, type_engin, est_electrique,
              CAST(ts AS DATE) jour, hour(ts) heure
            FROM _te2_ok""")
        # règles batterie -> rapport qualité en INFORMATIF (mesurées, non rejetées)
        tot = self.con.execute("SELECT count(*) FROM _te2 WHERE est_electrique").fetchone()[0]
        n20 = self.con.execute(f"SELECT count(*) FROM _te2 WHERE batterie_pct < {C.BATTERIE_MIN} OR batterie_pct > {C.BATTERIE_MAX}").fetchone()[0]
        n21 = self.con.execute("SELECT count(*) FROM _te2 WHERE est_electrique AND batterie_pct IS NULL").fetchone()[0]
        self._log_quality("telemetrie", "R20 batterie hors [0,100] (neutralisée)", "info", tot, n20)
        self._log_quality("telemetrie", "R21 batterie absente sur engin électrique (signalée)", "info", tot, n21)

    def silver_interventions(self):
        # Nouvelle source, format "sale" : sépar. ';', BOM, clé MC-, ville MAJ,
        # date FR, accents. On normalise pour la faire rejoindre le référentiel.
        da, di = "TRY_STRPTIME(date_alerte,'%d/%m/%Y %H:%M')", "TRY_STRPTIME(date_intervention,'%d/%m/%Y %H:%M')"
        self.sql(f"""CREATE OR REPLACE TEMP TABLE _iv AS
            SELECT * FROM (
              SELECT id_intervention,
                     replace(ref_engin, 'MC-', '') AS engin_id,   -- clé normalisée
                     (upper(substr(ville,1,1)) || lower(substr(ville,2))) AS ville,
                     {da} AS date_alerte, {di} AS date_intervention,
                     TRY_CAST(batterie_avant AS INT) batterie_avant,
                     TRY_CAST(batterie_apres AS INT) batterie_apres,
                     resultat,
                     {_pseudo('technicien')} AS technicien_px,   -- RGPD : nom pseudonymisé
                     row_number() OVER (PARTITION BY id_intervention ORDER BY _ingested_at) AS _rn
              FROM bronze_interventions
            ) WHERE _rn = 1""")
        n_brut = self.con.execute("SELECT count(*) FROM bronze_interventions").fetchone()[0]
        n_dedup = self.con.execute("SELECT count(*) FROM _iv").fetchone()[0]
        self._log_quality("interventions", "R00 déduplication (id_intervention)", "info", n_brut, n_brut - n_dedup)

        self._quarantine("interventions", "_iv", "id_intervention", [
            ("R30 date d'alerte illisible", "bloquante", "date_alerte IS NULL"),
            ("R31 engin absent du référentiel", "bloquante",
             "engin_id NOT IN (SELECT engin_id FROM ref_engins)"),
        ])
        self.sql("""CREATE OR REPLACE TABLE silver_interventions AS
            SELECT i.* REPLACE (e.ville_affectation AS ville),
              (i.date_intervention IS NULL) AS flag_non_realisee,
              (i.batterie_apres IS NOT NULL AND i.batterie_avant IS NOT NULL
                 AND i.batterie_apres < i.batterie_avant) AS flag_batterie_incoherente,
              CAST(i.date_alerte AS DATE) AS jour
            FROM _iv_ok i LEFT JOIN ref_engins e ON e.engin_id=i.engin_id""")
        for regle, cond in [("R32 batterie après < avant", "flag_batterie_incoherente")]:
            n = self.con.execute(f"SELECT count(*) FROM silver_interventions WHERE {cond}").fetchone()[0]
            tot = self.con.execute("SELECT count(*) FROM silver_interventions").fetchone()[0]
            self._log_quality("interventions", regle, "info", tot, n)

    def silver_meteo(self):
        self.sql("""CREATE OR REPLACE TABLE silver_meteo AS
            SELECT (upper(substr(ville,1,1)) || lower(substr(ville,2))) ville, date AS jour, temp_c, pluie_mm, vent_kmh
            FROM (SELECT *, row_number() OVER (PARTITION BY ville,date ORDER BY _ingested_at) rn
                  FROM bronze_meteo) WHERE rn=1""")

    def silver_maintenance(self):
        if not self.con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='bronze_maintenance'").fetchone()[0]:
            return
        self.sql("""CREATE OR REPLACE TABLE silver_maintenance AS
            SELECT ticket_id, engin_id, CAST(date_ouverture AS DATE) date_ouverture,
                   TRY_CAST(date_cloture AS DATE) date_cloture,
                   type_panne, priorite, TRY_CAST(cout_eur AS DOUBLE) cout_eur
            FROM (SELECT *, row_number() OVER (PARTITION BY ticket_id ORDER BY _ingested_at) rn
                  FROM bronze_maintenance) WHERE rn=1""")

    # -- moteur de quarantaine ----------------------------------------------
    def _quarantine(self, source, table, cle_expr, regles, base_from=None):
        """Applique des règles bloquantes : les lignes qui matchent partent en
        quarantaine (avec motif), les autres passent dans <table>_ok."""
        base = base_from or table
        esc = lambda s: s.replace("'", "''")   # échappe les apostrophes SQL
        # accumuler les rejets avec motif
        for regle, gravite, cond in regles:
            self.sql(f"""INSERT INTO quarantaine
                SELECT '{esc(source)}' AS source, CAST({cle_expr} AS VARCHAR) AS cle,
                       '{esc(regle)}' AS regle, '{esc(gravite)}' AS gravite, current_date AS traite_le
                FROM {base} WHERE {cond}""")
            n = self.con.execute(f"SELECT count(*) FROM {base} WHERE {cond}").fetchone()[0]
            tot = self.con.execute(f"SELECT count(*) FROM {base}").fetchone()[0]
            self._log_quality(source, regle, gravite, tot, n)
        # conformes = lignes ne matchant AUCUNE règle bloquante
        conds = " OR ".join(f"({c})" for _, g, c in regles if g == "bloquante")
        conds = conds or "FALSE"
        self.sql(f"CREATE OR REPLACE TEMP TABLE {table}_ok AS SELECT * FROM {base} WHERE NOT ({conds})")

    # ========================================================================
    #  Orchestration
    # ========================================================================
    def init_quarantine(self):
        self.sql("""CREATE OR REPLACE TABLE quarantaine
            (source VARCHAR, cle VARCHAR, regle VARCHAR, gravite VARCHAR, traite_le DATE)""")

    def write_quality_report(self):
        self.sql("DROP TABLE IF EXISTS qualite_rapport")
        self.sql("""CREATE TABLE qualite_rapport
            (source VARCHAR, regle VARCHAR, gravite VARCHAR,
             n_total BIGINT, n_concernees BIGINT, taux_pct DOUBLE)""")
        self.con.executemany("INSERT INTO qualite_rapport VALUES (?,?,?,?,?,?)", self._qual_rows)

    def run_silver(self):
        self.silver_trajets()
        self.silver_recherches()
        self.silver_telemetrie()
        self.silver_interventions()
        self.silver_meteo()
        self.silver_maintenance()

    def export_parquet(self):
        """Matérialise les tables Silver en Parquet partitionné par jour.
        C'est le stockage analytique de la couche Silver : compressé, colonnaire,
        et surtout partitionné pour ne relire qu'une journée (base de la lecture
        élaguée du bulletin de 7 h 30)."""
        import shutil
        for table in ("silver_trajets", "silver_recherches",
                      "silver_telemetrie", "silver_interventions"):
            dossier = C.LAKE / table
            if dossier.exists():
                shutil.rmtree(dossier)          # COPY refuse d'écrire dans un dossier existant
            self.sql(f"""COPY (SELECT * FROM {table})
                         TO '{_p(dossier)}' (FORMAT parquet, PARTITION_BY (jour))""")
