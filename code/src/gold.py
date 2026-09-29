"""
Gold — tables d'indicateurs, une par question de décision.
Chaque table a une maille explicite et une définition écrite (voir docs/).
Elles sont petites et pré-agrégées : c'est ce que lit le bulletin de 7 h 30.
"""
import duckdb
from . import config as C


def build_gold(db_path=C.WAREHOUSE, con=None):
    proprietaire = con is None          # ne fermer que si on a ouvert la connexion ici
    con = con or duckdb.connect(str(db_path))

    # ------------------------------------------------------------------ #
    # I1 — Demande non servie   (maille : station × jour × heure)
    #   Déf : part des recherches sans engin disponible.
    #   taux_non_service = aucun_engin / total_recherches
    # ------------------------------------------------------------------ #
    con.execute("""CREATE OR REPLACE TABLE gold_non_service AS
        SELECT r.station_id, s.nom AS station, s.ville, r.jour, r.heure,
               count(*) AS recherches,
               count(*) FILTER (WHERE r.resultat='aucun_engin')   AS sans_engin,
               count(*) FILTER (WHERE r.resultat='abandon')       AS abandons,
               count(*) FILTER (WHERE r.resultat='trajet_demarre')AS servies,
               round(100.0*count(*) FILTER (WHERE r.resultat='aucun_engin')/count(*),1) AS taux_non_service_pct
        FROM silver_recherches r
        LEFT JOIN ref_stations s ON s.station_id=r.station_id
        GROUP BY 1,2,3,4,5""")

    # I2 — Demande non servie agrégée par station (ranking + valorisation)
    #   Déf : trajets perdus estimés = recherches 'aucun_engin' (proxy),
    #   valorisés au panier moyen observé sur la période.
    panier = con.execute(
        "SELECT round(avg(montant_eur),2) FROM silver_trajets WHERE montant_eur>0").fetchone()[0]
    con.execute(f"""CREATE OR REPLACE TABLE gold_non_service_station AS
        SELECT r.station_id, s.nom AS station, s.ville,
               count(*) AS recherches,
               count(*) FILTER (WHERE r.resultat='aucun_engin') AS trajets_perdus_estimes,
               round(100.0*count(*) FILTER (WHERE r.resultat='aucun_engin')/count(*),1) AS taux_non_service_pct,
               round({panier} * count(*) FILTER (WHERE r.resultat='aucun_engin'),2) AS manque_a_gagner_eur
        FROM silver_recherches r
        LEFT JOIN ref_stations s ON s.station_id=r.station_id
        GROUP BY 1,2,3 ORDER BY trajets_perdus_estimes DESC""")

    # ------------------------------------------------------------------ #
    # I3 — Respect du contrat VoltaService  (maille : intervention)
    #   Règle contrat : le délai court dès l'alerte ; une alerte hors plage
    #   07:00–21:00 court à l'ouverture de la plage suivante.
    #   hors_delai si (intervention - début_délai) > 4 h.
    # ------------------------------------------------------------------ #
    con.execute(f"""CREATE OR REPLACE TABLE gold_sla_interventions AS
        WITH base AS (
          SELECT id_intervention, engin_id, ville, jour, date_alerte, date_intervention,
                 resultat, batterie_avant, batterie_apres, technicien_px,
                 CASE
                   WHEN date_alerte::TIME <  TIME '{C.PLAGE_DEBUT}'
                        THEN date_trunc('day',date_alerte) + INTERVAL {int(C.PLAGE_DEBUT.split(':')[0])} HOUR
                   WHEN date_alerte::TIME >= TIME '{C.PLAGE_FIN}'
                        THEN date_trunc('day',date_alerte) + INTERVAL 1 DAY + INTERVAL {int(C.PLAGE_DEBUT.split(':')[0])} HOUR
                   ELSE date_alerte
                 END AS debut_delai
          FROM silver_interventions
        )
        SELECT *,
          date_intervention IS NULL AS non_realisee,
          CASE WHEN date_intervention IS NOT NULL
               THEN round(date_diff('minute',debut_delai,date_intervention)/60.0,2) END AS delai_h,
          CASE WHEN date_intervention IS NOT NULL
               THEN date_diff('minute',debut_delai,date_intervention)/60.0 > {C.DELAI_MAX_H} END AS hors_delai
        FROM base""")

    # I3b — SLA agrégé par mois (décision de la directrice)
    con.execute(f"""CREATE OR REPLACE TABLE gold_sla_mensuel AS
        SELECT date_trunc('month',jour)::DATE AS mois,
               count(*) AS interventions,
               count(*) FILTER (WHERE non_realisee) AS engins_introuvables,
               count(*) FILTER (WHERE hors_delai)   AS hors_delai,
               round(100.0*count(*) FILTER (WHERE hors_delai=FALSE AND non_realisee=FALSE)
                     / nullif(count(*) FILTER (WHERE non_realisee=FALSE),0),1) AS taux_respect_pct,
               round({C.PENALITE_EUR}    * count(*) FILTER (WHERE hors_delai), 2) AS penalites_dues_eur,
               round({C.REMUNERATION_EUR}* count(*) FILTER (WHERE non_realisee=FALSE), 2) AS remuneration_eur
        FROM gold_sla_interventions GROUP BY 1 ORDER BY 1""")

    # ------------------------------------------------------------------ #
    # I4 — État de la flotte au réveil  (maille : engin × jour)
    #   Déf : dernière mesure batterie fiable avant 07:00 ; engin en alerte
    #   (<20 %) ou inutilisable (<15 %). C'est la base du bulletin de Karim.
    # ------------------------------------------------------------------ #
    con.execute(f"""CREATE OR REPLACE TABLE gold_flotte_reveil AS
        WITH avant7 AS (
          SELECT engin_id, ville, type_engin, jour, batterie_pct, statut, ts,
                 row_number() OVER (PARTITION BY engin_id,jour ORDER BY ts DESC) rn
          FROM silver_telemetrie
          WHERE est_electrique AND batterie_fiable AND heure < 7
        )
        SELECT jour, ville, engin_id, type_engin, batterie_pct, statut,
               batterie_pct < {C.SEUIL_ALERTE_PCT}      AS en_alerte,
               batterie_pct < {C.SEUIL_UTILISABLE_PCT}  AS inutilisable
        FROM avant7 WHERE rn=1""")

    con.execute("""CREATE OR REPLACE TABLE gold_flotte_synthese AS
        SELECT jour, ville,
               count(*) AS engins_elec_suivis,
               count(*) FILTER (WHERE en_alerte)     AS a_recharger,
               count(*) FILTER (WHERE inutilisable)  AS inutilisables,
               count(*) FILTER (WHERE statut='hors_service') AS hors_service
        FROM gold_flotte_reveil GROUP BY 1,2 ORDER BY 1,2""")

    # ------------------------------------------------------------------ #
    # I5 — Fiabilité des engins / lots de batterie  (décision flotte)
    #   Déf : tickets de maintenance et part de temps hors service par engin,
    #   rattachés au lot de batterie pour repérer un lot défectueux.
    # ------------------------------------------------------------------ #
    con.execute("""CREATE OR REPLACE TABLE gold_fiabilite_engin AS
        WITH tickets AS (
          SELECT engin_id, count(*) n_tickets,
                 count(*) FILTER (WHERE type_panne='batterie') n_tickets_batterie
          FROM silver_maintenance GROUP BY 1),
        hs AS (
          SELECT engin_id, avg((statut='hors_service')::INT) part_hors_service
          FROM silver_telemetrie GROUP BY 1)
        SELECT e.engin_id, e.type_engin, e.ville_affectation AS ville, e.modele, e.lot_batterie,
               COALESCE(t.n_tickets,0) n_tickets,
               COALESCE(t.n_tickets_batterie,0) n_tickets_batterie,
               round(100.0*COALESCE(hs.part_hors_service,0),1) part_hors_service_pct
        FROM ref_engins e
        LEFT JOIN tickets t USING(engin_id)
        LEFT JOIN hs USING(engin_id)""")

    con.execute("""CREATE OR REPLACE TABLE gold_fiabilite_lot AS
        SELECT lot_batterie, count(*) engins,
               sum(n_tickets_batterie) tickets_batterie,
               round(avg(part_hors_service_pct),1) part_hors_service_moy_pct
        FROM gold_fiabilite_engin WHERE lot_batterie IS NOT NULL
        GROUP BY 1 ORDER BY tickets_batterie DESC""")

    # ------------------------------------------------------------------ #
    # I6 — Météo × non-service  (cause : maille ville × jour)
    #   Déf : croise pluie/température et taux de non-service pour expliquer
    #   les pics de demande non servie.
    # ------------------------------------------------------------------ #
    con.execute("""CREATE OR REPLACE TABLE gold_meteo_nonservice AS
        SELECT m.ville, m.jour, m.pluie_mm, m.temp_c, m.vent_kmh,
               ns.recherches, ns.sans_engin,
               round(100.0*ns.sans_engin/nullif(ns.recherches,0),1) taux_non_service_pct
        FROM silver_meteo m
        LEFT JOIN (SELECT ville, jour, sum(recherches) recherches, sum(sans_engin) sans_engin
                   FROM gold_non_service GROUP BY 1,2) ns
          ON ns.ville=m.ville AND ns.jour=m.jour
        ORDER BY m.jour, m.ville""")

    if proprietaire:
        con.close()
    return db_path


if __name__ == "__main__":
    build_gold()
    print("Gold construit.")
