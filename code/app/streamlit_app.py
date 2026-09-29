"""
MobiCity — Interface d'analyse (page d'accueil : exploration interactive).

Un onglet par question de décision, chaque onglet nommant son destinataire et
la maille de l'indicateur. Les pages du menu de gauche présentent, elles, la
partie rédigée (cartographie, architecture, qualité, indicateurs, constats),
avec des chiffres calculés en direct depuis l'entrepôt.

Lancement :  streamlit run app/streamlit_app.py
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # rend _shared importable

import pandas as pd
import altair as alt
import streamlit as st
import _shared as sh
from _shared import interroger as q      # raccourci : q(...) au lieu de sh.interroger(...)
C = sh.C

st.set_page_config(page_title="MobiCity — Analyse", layout="wide")
sh.exiger_entrepot()   # message clair + arrêt si l'entrepôt n'existe pas encore


def villes_clause(villes):
    """Construit la clause SQL de filtre par ville (et ses paramètres)."""
    if not villes:
        return "TRUE", []
    trous = ",".join("?" * len(villes))
    return f"ville IN ({trous})", list(villes)

# --- Barre latérale : filtres -----------------------------------------------
st.sidebar.title("MobiCity")
st.sidebar.caption("Interface d'analyse")

bornes = q("SELECT min(jour) a, max(jour) b FROM gold_non_service")
jmin, jmax = bornes.a[0], bornes.b[0]
villes_all = q("SELECT DISTINCT ville FROM gold_non_service ORDER BY 1").ville.tolist()

villes = st.sidebar.multiselect("Villes", villes_all, default=villes_all)
periode = st.sidebar.date_input("Période", (jmin, jmax), min_value=jmin, max_value=jmax)
if isinstance(periode, tuple) and len(periode) == 2:
    d1, d2 = periode
else:
    d1, d2 = jmin, jmax
st.sidebar.markdown("---")
st.sidebar.caption(
    f"Seuils contrat : alerte < {C.SEUIL_ALERTE_PCT} %, inutilisable < "
    f"{C.SEUIL_UTILISABLE_PCT} %, délai < {C.DELAI_MAX_H} h.\n\n"
)

vclause, vparams = villes_clause(villes)
base_params = vparams + [d1, d2]

# --- En-tête + fraîcheur/périmètre ------------------------------------------
st.title("Analyse d'exploitation — MobiCity")

# Fraîcheur : dernière publication de la chaîne quotidienne (si elle a tourné).
def derniere_publication():
    existe = q("SELECT count(*) n FROM information_schema.tables WHERE table_name='_publication'").n[0]
    if not existe:
        return None
    p = q("SELECT max(date_traitee) d FROM _publication")
    if p.d[0] is None:
        return None
    return q("SELECT date_traitee, horodatage FROM _publication ORDER BY date_traitee DESC LIMIT 1")

pub = derniere_publication()
couv = q("SELECT min(jour) a, max(jour) b, count(DISTINCT jour) n FROM gold_non_service")
nb_villes = q(f"SELECT count(DISTINCT ville) n FROM gold_non_service WHERE {vclause}", tuple(vparams)).n[0]
if pub is not None:
    st.caption(f"Dernière journée publiée : {pub.date_traitee[0]} "
               f"(chaîne exécutée le {pub.horodatage[0]:%d/%m/%Y à %H:%M}). "
               f"Périmètre chargé : du {couv.a[0]} au {couv.b[0]}, {int(couv.n[0])} jours, {nb_villes} villes.")
else:
    st.caption(f"Périmètre chargé : du {couv.a[0]} au {couv.b[0]}, {int(couv.n[0])} jours, {nb_villes} villes. "
               "La chaîne quotidienne n'a pas encore été exécutée.")

# --- KPIs, avec un point de comparaison (période filtrée vs moyenne historique)
kpi = q(f"""SELECT sum(recherches) rech, sum(sans_engin) sans,
    round(100.0*sum(sans_engin)/nullif(sum(recherches),0),1) taux
  FROM gold_non_service WHERE {vclause} AND jour BETWEEN ? AND ?""", tuple(base_params))
sla = q(f"""SELECT count(*) FILTER(WHERE non_realisee=FALSE) realisees,
         count(*) FILTER(WHERE hors_delai) hd,
         round(100.0*count(*) FILTER(WHERE hors_delai=FALSE AND non_realisee=FALSE)
               /nullif(count(*) FILTER(WHERE non_realisee=FALSE),0),1) taux,
         round({C.PENALITE_EUR}*count(*) FILTER(WHERE hors_delai),0) pen
  FROM gold_sla_interventions WHERE {vclause} AND jour BETWEEN ? AND ?""", tuple(base_params))
# Référence de comparaison : la moyenne sur tout l'historique (toutes villes).
ref_ns = q("SELECT round(100.0*sum(sans_engin)/nullif(sum(recherches),0),1) t FROM gold_non_service").t[0]
ref_sla = q("""SELECT round(100.0*count(*) FILTER(WHERE hors_delai=FALSE AND non_realisee=FALSE)
               /nullif(count(*) FILTER(WHERE non_realisee=FALSE),0),1) t
             FROM gold_sla_interventions""").t[0]

st.caption("Chaque encart compare la période filtrée à la moyenne de tout l'historique.")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Recherches", f"{int(kpi.rech[0]):,}".replace(",", " "))
c2.metric("Taux de non-service", f"{kpi.taux[0]} %",
          delta=f"{round(kpi.taux[0]-ref_ns,1)} pt vs moyenne", delta_color="off")
c3.metric("Respect du contrat", f"{sla.taux[0]} %",
          delta=f"{round(sla.taux[0]-ref_sla,1)} pt vs moyenne", delta_color="off")
c4.metric("Pénalités dues", f"{int(sla.pen[0]):,} €".replace(",", " "))

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Demande non servie", "Contrat de recharge", "Flotte au réveil",
    "Fiabilité flotte", "Météo"])

# ============================================================ ① NON-SERVICE
with tab1:
    st.subheader("Où et quand la demande n'est pas servie")
    st.caption("Destinataires : Karim (rééquilibrage) et la direction (dimensionnement). "
               "Maille : station × jour × heure. Définition : recherches « aucun_engin » / total.")

    stations = q(f"""
      SELECT station, ville, sum(recherches) recherches, sum(sans_engin) perdus,
             round(100.0*sum(sans_engin)/nullif(sum(recherches),0),1) taux_pct,
             round({q('SELECT round(avg(montant_eur),2) m FROM silver_trajets WHERE montant_eur>0').m[0]}
                   *sum(sans_engin),0) manque_eur
      FROM gold_non_service WHERE {vclause} AND jour BETWEEN ? AND ?
      GROUP BY station, ville ORDER BY perdus DESC LIMIT 15""", tuple(base_params))

    colA, colB = st.columns([3, 2])
    with colA:
        st.markdown("**Top stations — trajets perdus estimés**")
        ch = alt.Chart(stations.head(10)).mark_bar().encode(
            x=alt.X("perdus:Q", title="Trajets perdus (estim.)"),
            y=alt.Y("station:N", sort="-x", title=None),
            color=alt.Color("ville:N", legend=alt.Legend(title="Ville")),
            tooltip=["station", "ville", "recherches", "perdus", "taux_pct", "manque_eur"])
        st.altair_chart(ch, width='stretch')
    with colB:
        st.markdown("**Profil horaire**")
        heures = q(f"""SELECT heure, sum(recherches) rech, sum(sans_engin) sans,
                       round(100.0*sum(sans_engin)/nullif(sum(recherches),0),1) taux
                     FROM gold_non_service WHERE {vclause} AND jour BETWEEN ? AND ?
                     GROUP BY heure ORDER BY heure""", tuple(base_params))
        ch2 = alt.Chart(heures).mark_area(opacity=0.4, line=True).encode(
            x=alt.X("heure:O", title="Heure"),
            y=alt.Y("taux:Q", title="Non-service %"),
            tooltip=["heure", "rech", "sans", "taux"])
        st.altair_chart(ch2, width='stretch')

    st.markdown("**Détail par station** (trié par manque à gagner)")
    st.dataframe(stations.sort_values("manque_eur", ascending=False),
                 width='stretch', hide_index=True)

# ============================================================ ② SLA CONTRAT
with tab2:
    st.subheader("Respect du contrat de recharge VoltaService")
    st.caption("Destinataire : direction des opérations (renouvellement / pénalités au 31/12). "
               "Maille : intervention → agrégée par mois. Règle : délai < 4 h dès l'alerte, "
               "une alerte hors 07 h–21 h court à l'ouverture suivante.")

    mens = q(f"""
      SELECT date_trunc('month',jour)::DATE mois,
             count(*) FILTER(WHERE non_realisee=FALSE) interventions,
             count(*) FILTER(WHERE hors_delai) hors_delai,
             round(100.0*count(*) FILTER(WHERE hors_delai=FALSE AND non_realisee=FALSE)
                   /nullif(count(*) FILTER(WHERE non_realisee=FALSE),0),1) respect_pct,
             round({C.PENALITE_EUR}*count(*) FILTER(WHERE hors_delai),0) penalites_eur
      FROM gold_sla_interventions WHERE {vclause} AND jour BETWEEN ? AND ?
      GROUP BY 1 ORDER BY 1""", tuple(base_params))

    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Taux de respect mensuel** (cible : 100 %)")
        ch = alt.Chart(mens).mark_bar().encode(
            x=alt.X("mois:T", title=None),
            y=alt.Y("respect_pct:Q", title="Respect %", scale=alt.Scale(domain=[0, 100])),
            tooltip=["mois", "interventions", "hors_delai", "respect_pct"])
        rule = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(strokeDash=[4, 4], color="green").encode(y="y")
        st.altair_chart(ch + rule, width='stretch')
    with colB:
        st.markdown("**Pénalités dues par mois**")
        ch = alt.Chart(mens).mark_bar(color="#c0392b").encode(
            x=alt.X("mois:T", title=None), y=alt.Y("penalites_eur:Q", title="€"),
            tooltip=["mois", "hors_delai", "penalites_eur"])
        st.altair_chart(ch, width='stretch')

    hv = q(f"""SELECT ville, count(*) FILTER(WHERE non_realisee=FALSE) interventions,
                 count(*) FILTER(WHERE hors_delai) hors_delai,
                 round(100.0*count(*) FILTER(WHERE hors_delai=FALSE AND non_realisee=FALSE)
                       /nullif(count(*) FILTER(WHERE non_realisee=FALSE),0),1) respect_pct
               FROM gold_sla_interventions WHERE {vclause} AND jour BETWEEN ? AND ?
               GROUP BY ville ORDER BY respect_pct""", tuple(base_params))
    st.markdown("**Respect par ville**")
    st.dataframe(hv, width='stretch', hide_index=True)

# ============================================================ ③ FLOTTE
with tab3:
    st.subheader("État de la flotte au réveil")
    st.caption("Destinataire : Karim (engins à recharger avant le premier départ). "
               "Maille : engin × jour. Définition : dernière batterie fiable avant 07 h ; "
               f"alerte < {C.SEUIL_ALERTE_PCT} %, inutilisable < {C.SEUIL_UTILISABLE_PCT} %.")

    eng = q(f"""SELECT jour, ville, sum(a_recharger) a_recharger, sum(inutilisables) inutilisables
               FROM gold_flotte_synthese WHERE {vclause} AND jour BETWEEN ? AND ?
               GROUP BY 1,2 ORDER BY 1""", tuple(base_params))
    st.markdown("**Engins à recharger chaque matin, par ville**")
    ch = alt.Chart(eng).mark_line(point=True).encode(
        x=alt.X("jour:T", title=None), y=alt.Y("a_recharger:Q", title="Engins < 20 %"),
        color="ville:N", tooltip=["jour", "ville", "a_recharger", "inutilisables"])
    st.altair_chart(ch, width='stretch')

    dernier = q("SELECT max(jour) j FROM gold_flotte_reveil").j[0]
    st.markdown(f"**Liste actionnable — engins à recharger le {dernier}** "
                "(le dernier jour disponible)")
    liste = q(f"""SELECT ville, engin_id, type_engin, batterie_pct, statut
                 FROM gold_flotte_reveil
                 WHERE jour = ? AND en_alerte AND {vclause}
                 ORDER BY batterie_pct""", tuple([dernier] + vparams))
    st.dataframe(liste, width='stretch', hide_index=True)

# ============================================================ ④ FIABILITÉ
with tab4:
    st.subheader("Fiabilité des engins et des lots de batterie")
    st.caption("Destinataire : responsable flotte (retrait / réparation / garantie). "
               "Maille : engin, agrégée par lot de batterie. "
               "Définition : tickets de maintenance et part de temps hors service.")

    lots = q("""SELECT lot_batterie, engins, tickets_batterie, part_hors_service_moy_pct
                FROM gold_fiabilite_lot ORDER BY tickets_batterie DESC""")
    colA, colB = st.columns([2, 3])
    with colA:
        st.markdown("**Tickets batterie par lot**")
        ch = alt.Chart(lots.head(10)).mark_bar().encode(
            x=alt.X("tickets_batterie:Q", title="Tickets batterie"),
            y=alt.Y("lot_batterie:N", sort="-x", title=None),
            tooltip=["lot_batterie", "engins", "tickets_batterie", "part_hors_service_moy_pct"])
        st.altair_chart(ch, width='stretch')
    with colB:
        st.markdown("**Engins les plus fragiles**")
        engs = q(f"""SELECT engin_id, type_engin, ville, modele, lot_batterie,
                       n_tickets, n_tickets_batterie, part_hors_service_pct
                     FROM gold_fiabilite_engin WHERE {vclause.replace('ville','ville')}
                     ORDER BY n_tickets DESC, part_hors_service_pct DESC LIMIT 20""",
                 tuple(vparams))
        st.dataframe(engs, width='stretch', hide_index=True)

# ============================================================ ⑤ MÉTÉO
with tab5:
    st.subheader("Cause : la météo explique-t-elle le non-service ?")
    st.caption("Destinataire : analyse / direction. Décision : agir sur l'offre ou attendre. "
               "Maille : ville × jour. Croise pluie et taux de non-service.")

    met = q(f"""SELECT ville, jour, pluie_mm, temp_c, taux_non_service_pct
               FROM gold_meteo_nonservice
               WHERE {vclause} AND jour BETWEEN ? AND ? AND taux_non_service_pct IS NOT NULL
               ORDER BY jour""", tuple(base_params))
    corr = met[["pluie_mm", "taux_non_service_pct"]].corr().iloc[0, 1] if len(met) > 2 else float("nan")
    st.metric("Corrélation pluie / non-service", f"{corr:.2f}",
              help="Négative = il y a moins de non-service les jours de pluie (moins de demande).")
    ch = alt.Chart(met).mark_circle(size=70, opacity=0.6).encode(
        x=alt.X("pluie_mm:Q", title="Pluie (mm)"),
        y=alt.Y("taux_non_service_pct:Q", title="Non-service %"),
        color="ville:N", tooltip=["ville", "jour", "pluie_mm", "temp_c", "taux_non_service_pct"])
    st.altair_chart(ch, width='stretch')

st.markdown("---")
st.caption("MobiCity — Interface d'analyse.")
