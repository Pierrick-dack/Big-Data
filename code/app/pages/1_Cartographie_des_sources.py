"""Page « Cartographie des sources ».

Le texte décrit la structure des données (format, sensibilité, importance pour
le bulletin). Tous les chiffres — volumes, formats de dates, batterie manquante —
sont calculés en direct depuis l'entrepôt, construit à partir de donnees/.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # rend _shared importable

import pandas as pd
import streamlit as st
import _shared as sh

q, fr, C = sh.interroger, sh.fr, sh.C

st.set_page_config(page_title="Cartographie des sources", layout="wide")
sh.exiger_entrepot()

st.title("Cartographie des sources")

# --- Période couverte, calculée depuis les données --------------------------
periode = q("SELECT min(jour) a, max(jour) b FROM silver_trajets")
d1, d2 = periode.a[0], periode.b[0]
nb_jours = (d2 - d1).days + 1
st.write(f"L'historique va du {d1} au {d2}, soit {nb_jours} jours. "
         "Les chiffres de cette page sont recalculés à chaque affichage, "
         "directement à partir des données.")

# --- Volumes, comptés dans la couche Bronze (copie fidèle des sources) -------
volumes = {
    "Trajets":       ("CSV, un fichier par jour",        sh.scalaire("SELECT count(*) FROM bronze_trajets")),
    "Recherches":    ("JSONL, un par jour",              sh.scalaire("SELECT count(*) FROM bronze_recherches")),
    "Télémétrie":    ("JSONL compressé, un par jour",    sh.scalaire("SELECT count(*) FROM bronze_telemetrie")),
    "Interventions": ("CSV séparé par « ; »",            sh.scalaire("SELECT count(*) FROM bronze_interventions")),
    "Météo":         ("JSON, un par jour",               sh.scalaire("SELECT count(*) FROM bronze_meteo")),
    "Maintenance":   ("JSON, un export par semaine",     sh.scalaire("SELECT count(*) FROM bronze_maintenance")),
}
sensibilite = {
    "Trajets": "Élevée (client, paiement)", "Recherches": "Élevée (client, position GPS)",
    "Télémétrie": "Faible (engin seulement)", "Interventions": "Moyenne (nom du technicien)",
    "Météo": "Nulle", "Maintenance": "Faible",
}
importance = {
    "Trajets": "Usage réel et panier moyen",
    "Recherches": "La seule source de la demande non servie",
    "Télémétrie": "Essentielle : la batterie dit quels engins recharger",
    "Interventions": "Suivi du contrat de recharge",
    "Météo": "Variable d'explication",
    "Maintenance": "Fiabilité des engins",
}
tableau = pd.DataFrame(
    [{"Source": s, "Format": v[0], "Volume": fr(v[1]),
      "Sensibilité": sensibilite[s], "Importance pour le bulletin": importance[s]}
     for s, v in volumes.items()])

st.subheader("Les six sources")
st.write("Chaque source arrive dans son format et à son rythme. Le tableau résume "
         "ce qu'elles pèsent, leur sensibilité côté données personnelles, et leur "
         "rôle pour le bulletin du matin.")
st.dataframe(tableau, width='stretch', hide_index=True)

r_eng = sh.scalaire("SELECT count(*) FROM ref_engins")
r_sta = sh.scalaire("SELECT count(*) FROM ref_stations")
r_cli = sh.scalaire("SELECT count(*) FROM ref_clients")
st.write(f"À côté, les référentiels font autorité : {r_eng} engins, {r_sta} stations, "
         f"{fr(r_cli)} clients et le contrat de recharge.")

st.divider()
st.subheader("Ce que les données ont de piégeux")

# Piège 1 : formats de dates mélangés dans les trajets
fmt = q("""SELECT
    count(*) FILTER(WHERE TRY_STRPTIME(debut,'%Y-%m-%d %H:%M:%S') IS NOT NULL) iso,
    count(*) FILTER(WHERE TRY_STRPTIME(debut,'%d/%m/%Y %H:%M') IS NOT NULL) fr,
    count(*) FILTER(WHERE TRY_CAST(debut AS BIGINT) IS NOT NULL) epoch,
    count(*) FILTER(WHERE debut IS NULL) nul
  FROM bronze_trajets""")
iso, frq, epoch, nul = int(fmt.iso[0]), int(fmt.fr[0]), int(fmt.epoch[0]), int(fmt.nul[0])
incoherent_reel = sh.scalaire("SELECT count(*) FROM silver_trajets WHERE debut>=fin")

st.markdown("**Des dates écrites de trois façons différentes.**")
st.write(f"Les heures de début et de fin des trajets ne suivent pas toutes le même "
         f"format : la plupart sont au format ISO ({fr(iso)}), d'autres au format "
         f"français ({fr(frq)}), et certaines sont des timestamps Unix ({fr(epoch)}) ; "
         f"{fr(nul)} sont vides. Si on compare ces textes tels quels, beaucoup de "
         f"trajets semblent se terminer avant d'avoir commencé. Une fois les dates "
         f"ramenées à un format unique, il n'en reste que {incoherent_reel} réellement "
         f"incohérent. C'est pour cela qu'on normalise d'abord, et qu'on valide ensuite.")

# Piège 2 : batterie manquante selon le type d'engin
bat = q("""SELECT e.type_engin,
             count(*) tot,
             count(*) FILTER(WHERE t.batterie_pct IS NULL) nul
           FROM bronze_telemetrie t JOIN ref_engins e USING(engin_id)
           GROUP BY 1 ORDER BY 1""")
bat["Part vide"] = (100*bat["nul"]/bat["tot"]).round(0).astype(int).astype(str)+" %"
st.markdown("**Une batterie parfois absente, pour deux raisons opposées.**")
st.write("Sur les vélos mécaniques, l'absence de batterie est normale : ils n'en ont "
         "pas. Sur les trottinettes, c'est un capteur qui décroche. Plutôt que de "
         "jeter toute la mesure, on neutralise seulement la valeur de batterie et on "
         "conserve la position et le statut, qui restent utiles au rééquilibrage.")
st.dataframe(bat.rename(columns={"type_engin": "Type d'engin", "tot": "Mesures", "nul": "Batterie vide"}),
             width='stretch', hide_index=True)

# Piège 3 : villes bruitées + format sale des interventions
n_var = sh.scalaire("SELECT count(DISTINCT ville) FROM bronze_telemetrie")
st.markdown("**Des noms de villes approximatifs.**")
st.write(f"Dans la télémétrie, le champ ville prend {n_var} formes différentes "
         "(majuscules, fautes comme « Lyonn » ou « Nante », espaces en trop), alors "
         "que le référentiel n'en connaît que quatre. On reprend donc toujours la "
         "ville depuis le référentiel, jamais depuis le champ brut.")
st.markdown("**Des interventions dans un format peu commode.**")
st.write("Elles arrivent en CSV séparé par « ; », avec un en-tête parasite, des dates "
         "à la française, des villes en majuscules et un identifiant d'engin préfixé "
         "(par exemple « MC-EN00599 » au lieu de « EN00599 »). Tout cela est nettoyé "
         "pour que la source rejoigne les couches existantes.")

st.caption("Le détail des règles et des taux de rejet se trouve sur la page "
           "« Règles de qualité », qui contient aussi la partie données personnelles.")
