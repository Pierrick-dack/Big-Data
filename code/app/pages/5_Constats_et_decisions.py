"""Page « Constats et décisions ».

Relie chaque chiffre mesuré à une cause probable et à une décision, pour un
destinataire précis. Tous les nombres sont calculés en direct depuis l'entrepôt.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import streamlit as st
import _shared as sh

q, fr = sh.interroger, sh.fr

st.set_page_config(page_title="Constats et décisions", layout="wide")
sh.exiger_entrepot()

st.title("Constats et décisions recommandées")

# --- Chiffres clés, calculés en direct --------------------------------------
non_service = sh.scalaire("SELECT round(100.0*sum(sans_engin)/sum(recherches),1) FROM gold_non_service")
manque = sh.scalaire("SELECT round(sum(manque_a_gagner_eur),0) FROM gold_non_service_station")
sla = sh.scalaire("""SELECT round(100.0*count(*) FILTER(WHERE hors_delai=FALSE AND non_realisee=FALSE)
                     /count(*) FILTER(WHERE non_realisee=FALSE),1) FROM gold_sla_interventions""")
penalites = sh.scalaire("SELECT round(12*count(*) FILTER(WHERE hors_delai),0) FROM gold_sla_interventions")
a_recharger = sh.scalaire("SELECT round(avg(t),0) FROM (SELECT jour, sum(a_recharger) t FROM gold_flotte_synthese GROUP BY jour)")

st.write("Quatre chiffres résument la situation sur la période. Le reste de la page "
         "les met en perspective, destinataire par destinataire.")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Demande non servie", f"{non_service} %")
c2.metric("Manque à gagner", fr(manque, " €"))
c3.metric("Respect du contrat", f"{sla} %")
c4.metric("Pénalités dues", fr(penalites, " €"))

# ---------------------------------------------------------------- Exploitation
st.divider()
st.subheader("Pour l'exploitation, chaque matin")

top = q("""SELECT station, ville, taux_non_service_pct, trajets_perdus_estimes, manque_a_gagner_eur
           FROM gold_non_service_station ORDER BY trajets_perdus_estimes DESC LIMIT 4""")
pic = q("""SELECT heure, round(100.0*sum(sans_engin)/sum(recherches),1) taux
           FROM gold_non_service GROUP BY heure ORDER BY taux DESC LIMIT 1""")
liste_top = ", ".join(f"{r.station} ({r.taux_non_service_pct} %)" for r in top.itertuples())

st.write(f"La demande non servie n'est pas dispersée : elle se concentre sur quelques "
         f"stations, surtout {liste_top}. Elle atteint son maximum vers "
         f"{int(pic.heure[0])} h ({pic.taux[0]} %), au moment de la pointe du matin vers "
         "les campus. La priorité est donc de rééquilibrer ces stations avant 8 h.")
st.dataframe(top.rename(columns={
    "station": "Station", "ville": "Ville", "taux_non_service_pct": "Non-service %",
    "trajets_perdus_estimes": "Trajets perdus", "manque_a_gagner_eur": "Manque (€)"}),
    width='stretch', hide_index=True)

flotte = q("""SELECT ville, round(avg(a_recharger),1) moy
              FROM gold_flotte_synthese GROUP BY ville ORDER BY moy DESC""")
villes_flotte = ", ".join(f"{r.ville} ({r.moy})" for r in flotte.itertuples())
st.write(f"La recharge se concentre elle aussi : en moyenne {fr(a_recharger)} engins "
         f"passent sous le seuil d'alerte chaque matin, répartis ainsi — {villes_flotte}. "
         "La tournée gagne à être dimensionnée sur les villes de tête. La liste précise "
         "des engins à recharger (identifiant, batterie, station) est disponible sur la "
         "page d'accueil, dans l'onglet consacré à la flotte au réveil.")

# ---------------------------------------------------------------- Direction
st.divider()
st.subheader("Pour la direction, avant le 31 décembre")

mens = q("""SELECT date_trunc('month',jour)::DATE mois,
              count(*) FILTER(WHERE non_realisee=FALSE) interventions,
              count(*) FILTER(WHERE hors_delai) hors_delai,
              round(100.0*count(*) FILTER(WHERE hors_delai=FALSE AND non_realisee=FALSE)
                    /count(*) FILTER(WHERE non_realisee=FALSE),1) respect_pct,
              round(12*count(*) FILTER(WHERE hors_delai),0) penalites_eur
            FROM gold_sla_interventions GROUP BY 1 ORDER BY 1""")
pire = mens.loc[mens.respect_pct.idxmin()]

st.write(f"Le prestataire de recharge ne tient pas toujours son engagement de 4 h : le "
         f"respect global est de {sla} %. Surtout, il se dégrade quand le volume "
         f"augmente — le pire mois est {pire.mois:%B %Y} ({pire.respect_pct} %, "
         f"{int(pire.hors_delai)} interventions hors délai). C'est un signal important "
         "à l'approche du passage à 3 000 engins en 2027. Deux décisions se dégagent : "
         f"facturer les pénalités dues ({fr(penalites, ' €')}, justifiables intervention "
         "par intervention), et renégocier un engagement de capacité indexé sur le "
         "volume, vérifié chaque mois par cette chaîne — à défaut d'amélioration, "
         "mettre le marché en concurrence avant le renouvellement.")
st.dataframe(mens.rename(columns={
    "mois": "Mois", "interventions": "Interventions", "hors_delai": "Hors délai",
    "respect_pct": "Respect %", "penalites_eur": "Pénalités (€)"}),
    width='stretch', hide_index=True)

# ---------------------------------------------------------------- Flotte
st.divider()
st.subheader("Pour le responsable flotte, chaque semaine")

lot = q("""SELECT lot_batterie, engins, tickets_batterie, part_hors_service_moy_pct
           FROM gold_fiabilite_lot ORDER BY tickets_batterie DESC LIMIT 3""")
pire_lot = lot.iloc[0]
st.write(f"Un lot de batterie ressort nettement : le lot {pire_lot.lot_batterie} "
         f"({int(pire_lot.engins)} engins) concentre le plus de tickets liés à la "
         f"batterie ({int(pire_lot.tickets_batterie)}), ce qui évoque un défaut de "
         "série. Il vaut la peine d'inspecter ce lot en priorité, de vérifier s'il est "
         "encore sous garantie, et de retirer ou réparer les engins qui passent le plus "
         "de temps hors service.")
st.dataframe(lot.rename(columns={
    "lot_batterie": "Lot", "engins": "Engins", "tickets_batterie": "Tickets batterie",
    "part_hors_service_moy_pct": "Hors service moyen %"}),
    width='stretch', hide_index=True)

# ---------------------------------------------------------------- Cause
st.divider()
st.subheader("Une cause écartée : la météo")
corr = sh.scalaire("""SELECT round(corr(pluie_mm, taux_non_service_pct),2)
                      FROM gold_meteo_nonservice WHERE taux_non_service_pct IS NOT NULL""")
st.write(f"On aurait pu croire que la météo explique le non-service. C'est l'inverse : "
         f"la corrélation entre la pluie et le taux de non-service est de {corr}, "
         "c'est-à-dire qu'il y a moins de non-service les jours de pluie, tout "
         "simplement parce que la demande baisse. Le manque d'engins aux campus est "
         "donc bien un problème d'offre, pas un effet de la météo — ce qui confirme "
         "qu'il faut rééquilibrer plutôt qu'attendre.")
