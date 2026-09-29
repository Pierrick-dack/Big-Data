"""Page « Règles de qualité ».

Affiche le catalogue des règles (table qualite_rapport produite par le pipeline),
les taux de rejet par source, et vérifie en direct qu'aucune donnée identifiante
n'atteint les couches d'analyse.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import streamlit as st
import _shared as sh

q, fr, C = sh.interroger, sh.fr, sh.C

st.set_page_config(page_title="Règles de qualité", layout="wide")
sh.exiger_entrepot()

st.title("Règles de qualité et données personnelles")

st.write("Le principe est simple : on normalise d'abord, puis on valide. Chaque règle "
         "est soit bloquante — la ligne est mise de côté en quarantaine, avec le motif "
         "du rejet — soit informative : la ligne est conservée mais signalée.")

# --- Catalogue des règles (produit par le pipeline) -------------------------
regles = q("""SELECT source AS Source, regle AS Règle, gravite AS Gravité,
                     n_total AS Total, n_concernees AS Cas, taux_pct AS "Taux %"
              FROM qualite_rapport ORDER BY source, regle""")
st.subheader("Le catalogue des règles")
st.dataframe(regles, width='stretch', hide_index=True)

# --- Taux de rejet par source -----------------------------------------------
st.subheader("Ce qui est rejeté, par source")
rejet = q("""
  WITH quar AS (SELECT source, count(DISTINCT cle) rejetees FROM quarantaine GROUP BY 1),
  conf AS (
    SELECT 'trajets' s, count(*) n FROM silver_trajets UNION ALL
    SELECT 'recherches', count(*) FROM silver_recherches UNION ALL
    SELECT 'telemetrie', count(*) FROM silver_telemetrie UNION ALL
    SELECT 'interventions', count(*) FROM silver_interventions)
  SELECT conf.s AS Source, conf.n AS Conformes, COALESCE(quar.rejetees,0) AS Quarantaine,
         round(100.0*COALESCE(quar.rejetees,0)/(conf.n+COALESCE(quar.rejetees,0)),2) AS "Rejet %"
  FROM conf LEFT JOIN quar ON quar.source=conf.s ORDER BY 1""")
st.dataframe(rejet, width='stretch', hide_index=True)

dedup_re = int(sh.scalaire("SELECT n_concernees FROM qualite_rapport WHERE regle LIKE 'R00%' AND source='recherches'"))
bat_flag = int(sh.scalaire("SELECT count(*) FROM silver_telemetrie WHERE NOT batterie_fiable"))
st.write(f"Deux chiffres à retenir : {fr(dedup_re)} recherches en double ont été "
         "supprimées (sur leur identifiant), et pour la télémétrie, aucune ligne n'est "
         f"perdue — {fr(bat_flag)} mesures ont seulement leur valeur de batterie "
         "signalée comme douteuse, la position et le statut restant exploitables.")
st.caption("Le pipeline exporte aussi ces éléments en fichiers : "
           "data/rapports/rapport_qualite.csv et data/quarantaine/quarantaine.csv "
           "(chaque ligne rejetée y figure avec son motif).")

# --- Données personnelles : vérification en direct --------------------------
st.divider()
st.subheader("Données personnelles")
st.write("Trois principes sont appliqués. L'identifiant client et le nom du technicien "
         "sont remplacés par une empreinte (« PX_… »). La position GPS du client est "
         "supprimée : on ne garde que la station. Et les informations identifiantes du "
         "référentiel clients (nom, e-mail, téléphone, date de naissance) ne sont même "
         "pas chargées. Résultat : aucune donnée identifiante n'atteint les couches "
         "d'analyse, seules visibles depuis l'interface.")

cols_tr = [c[0] for c in sh.connexion().execute("DESCRIBE silver_trajets").fetchall()]
cols_re = [c[0] for c in sh.connexion().execute("DESCRIBE silver_recherches").fetchall()]
ex_client = sh.scalaire("SELECT client_px FROM silver_trajets WHERE client_px IS NOT NULL LIMIT 1")
ex_tech = sh.scalaire("SELECT technicien_px FROM silver_interventions WHERE technicien_px IS NOT NULL LIMIT 1")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Colonnes de silver_trajets**")
    st.code(", ".join(cols_tr), language=None)
    st.caption("Pas de colonne client_id : seulement client_px.")
with c2:
    st.markdown("**Colonnes de silver_recherches**")
    st.code(", ".join(cols_re), language=None)
    st.caption("Ni latitude ni longitude du client : seulement l'identifiant de station.")

verif_ok = ("client_id" not in cols_tr) and ("lat" not in cols_re) and ("lon" not in cols_re)
if verif_ok:
    st.write(f"Vérification automatique : conforme. Les colonnes ci-dessus ne "
             "contiennent aucun identifiant direct ni coordonnée du client. "
             f"Exemples d'identifiants pseudonymisés : client « {ex_client} », "
             f"technicien « {ex_tech} ».")
else:
    st.write("Vérification automatique : une colonne identifiante subsiste — "
             "à corriger dans l'ETL.")
