"""Page « Architecture ».

Décrit les couches Bronze / Silver / Gold et justifie le choix du Parquet
partitionné par une mesure faite en direct : le temps de lecture d'une journée,
en relisant les fichiers bruts d'un côté, en Parquet partitionné de l'autre.
"""
import pathlib, sys, glob, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import streamlit as st
import _shared as sh

fr, C = sh.fr, sh.C

st.set_page_config(page_title="Architecture", layout="wide")
sh.exiger_entrepot()

st.title("Architecture")

st.write("La chaîne repose sur Python, DuckDB et Streamlit, avec Parquet comme "
         "format de stockage intermédiaire. Tout tient sur un poste local, sans "
         "service payant : DuckDB lit directement les CSV, JSON, fichiers compressés "
         "et Parquet, et il n'y a qu'un seul fichier d'entrepôt à gérer.")

st.write("Les données passent par trois couches, chacune avec un rôle précis :")
st.markdown("""
| Couche | Rôle | Contenu |
|---|---|---|
| Bronze | Ingestion fidèle et tracée | Copie brute des sources, plus le nom du fichier d'origine et l'horodatage |
| Silver | Données propres | Normalisation, déduplication, contrôle d'intégrité, règles de qualité, données personnelles ; stockées en Parquet partitionné par jour |
| Gold | Indicateurs | Tables déjà agrégées, une par question de décision : c'est ce que lit le bulletin |
""")

st.divider()
st.subheader("Pourquoi partitionner : la mesure")
st.write("Le cas qui compte, c'est celui du bulletin du matin : lire la batterie de "
         "tous les engins de la veille. On mesure le temps que cela prend selon la "
         "façon de stocker les données.")

lake = C.LAKE / "silver_telemetrie"
if not lake.exists():
    st.write("Le Parquet partitionné n'a pas encore été généré. Relancer la "
             "construction (`python build.py`) pour activer la mesure.")
else:
    @st.cache_data(show_spinner="Mesure en cours…")
    def mesure_perf():
        """Compare le temps de lecture d'une journée : fichiers bruts vs Parquet.
        La mesure est faite sur la machine et mise en cache pour ne tourner qu'une fois."""
        con = sh.connexion()
        jour = sh.scalaire("SELECT max(jour) FROM silver_telemetrie")
        gz = sorted(glob.glob(str(C.HIST / "telemetrie" / "*.jsonl.gz")))
        liste = "[" + ",".join(f"'{pathlib.Path(p).as_posix()}'" for p in gz) + "]"
        req_brut = (f"SELECT engin_id,batterie_pct FROM read_json_auto({liste}, "
                    f"format='newline_delimited', union_by_name=true) "
                    f"WHERE CAST(ts AS DATE)=DATE '{jour}'")
        req_pq = (f"SELECT engin_id,batterie_pct FROM read_parquet('{lake.as_posix()}/**/*.parquet', "
                  f"hive_partitioning=true) WHERE jour=DATE '{jour}'")

        def chrono(sql, n=3):
            con.execute(sql)
            return min(_mesure_une(con, sql) for _ in range(n)) * 1000

        return jour, chrono(req_brut), chrono(req_pq)

    def _mesure_une(con, sql):
        t = time.perf_counter(); con.execute(sql).fetchall(); return time.perf_counter() - t

    jour, t_brut, t_pq = mesure_perf()
    c1, c2, c3 = st.columns(3)
    c1.metric("En relisant les fichiers bruts", f"{t_brut:.0f} ms")
    c2.metric("En Parquet partitionné", f"{t_pq:.0f} ms")
    c3.metric("Gain", f"×{t_brut/t_pq:.0f}")
    st.write(f"Lecture de la journée du {jour}. Le Parquet ne lit que la partition du "
             "jour demandé ; la relecture des fichiers bruts, elle, décompresse et "
             "analyse tout l'historique à chaque fois.")

st.write("L'intérêt est là : sans partitionnement, le temps de préparation augmente "
         "avec tout l'historique accumulé ; avec, il reste borné à une seule journée. "
         "C'est ce qui permet de tenir le créneau de 7 h 30 sur la durée.")

st.divider()
st.subheader("Tenir la charge de 2027")

nb_jours = sh.scalaire("SELECT date_diff('day', min(jour), max(jour))+1 FROM silver_telemetrie")
tel_total = sh.scalaire("SELECT count(*) FROM silver_telemetrie")
par_jour = tel_total / nb_jours
proj = par_jour * (3000 / 600) * 2   # 5x plus d'engins, relevé 2x plus fréquent
c1, c2 = st.columns(2)
c1.metric("Télémétrie par jour aujourd'hui", fr(par_jour) + " lignes", help="600 engins")
c2.metric("Projection 2027", fr(proj) + " lignes/jour", help="3 000 engins, relevé toutes les 30 s")
st.write("La cible annoncée pour 2027 est de multiplier la flotte par cinq et de "
         "relever la télémétrie deux fois plus souvent. L'architecture y répond sans "
         "être refaite : l'élagage par jour est déjà en place, un découpage "
         "supplémentaire par ville peut être ajouté (la ville est déjà normalisée en "
         "Silver), et le format en colonnes ne lit que les champs utiles au bulletin.")

st.divider()
st.subheader("Deux limites que l'on assume")
st.write("La conversion des horaires depuis l'heure UTC se fait en ajoutant deux "
         "heures, ce qui est exact sur toute la période des données (été, sans "
         "changement d'heure). Pour couvrir l'année entière, il faudrait activer un "
         "vrai fuseau Europe/Paris ; cela ne change rien aux résultats présentés ici.")
st.write("Côté données personnelles, aucune information identifiante ne franchit la "
         "couche Bronze. Silver et Gold, les seules couches lues par l'interface, ne "
         "contiennent que des identifiants pseudonymisés et des attributs qui ne "
         "permettent pas d'identifier une personne.")
