"""Page « Dictionnaire des indicateurs ».

Pour chaque table Gold : sa maille, sa définition, son nombre de lignes et un
aperçu — le tout tiré de l'entrepôt.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import streamlit as st
import _shared as sh

q, fr = sh.interroger, sh.fr

st.set_page_config(page_title="Dictionnaire des indicateurs", layout="wide")
sh.exiger_entrepot()

st.title("Dictionnaire des indicateurs")
st.write("Six indicateurs composent la couche Gold. Pour chacun, on précise sa maille "
         "(ce que représente une ligne) et sa définition. Ensemble, ils mesurent la "
         "demande non servie, le respect du contrat de recharge, et les causes possibles. "
         "Déplier un indicateur pour voir sa définition et un aperçu des données.")

# (table, titre, maille, définition, colonnes à prévisualiser)
INDICATEURS = [
    ("gold_non_service", "Taux de non-service",
     "une station, un jour, une heure",
     "Part des recherches qui n'ont trouvé aucun engin disponible, soit "
     "sans_engin / recherches (sans_engin = recherches au résultat « aucun engin »).",
     ["station", "ville", "jour", "heure", "recherches", "sans_engin", "taux_non_service_pct"]),
    ("gold_non_service_station", "Non-service par station et manque à gagner",
     "une station, sur toute la période",
     "trajets_perdus_estimes correspond aux recherches « aucun engin » (une estimation "
     "de la demande perdue) ; manque_a_gagner_eur = ces trajets perdus multipliés par le "
     "panier moyen observé.",
     ["station", "ville", "trajets_perdus_estimes", "taux_non_service_pct", "manque_a_gagner_eur"]),
    ("gold_sla_mensuel", "Respect du contrat de recharge",
     "une intervention, agrégée par mois",
     "Le délai doit rester sous 4 h à partir de l'alerte (une alerte hors 07 h–21 h "
     "démarre à l'ouverture suivante). taux_respect = interventions dans les délais / "
     "interventions réalisées ; penalites_dues = nombre hors délai multiplié par 12 €.",
     ["mois", "interventions", "hors_delai", "taux_respect_pct", "penalites_dues_eur"]),
    ("gold_flotte_synthese", "État de la flotte au réveil",
     "un engin, un jour (résumé par ville et par jour)",
     "Dernière batterie fiable relevée avant 07 h ; un engin est en alerte sous 20 %, "
     "inutilisable sous 15 % (seuils du contrat). Donne le nombre d'engins à recharger "
     "par ville chaque matin.",
     ["jour", "ville", "engins_elec_suivis", "a_recharger", "inutilisables", "hors_service"]),
    ("gold_fiabilite_lot", "Fiabilité des lots de batterie",
     "un engin, regroupé par lot de batterie",
     "Nombre de tickets de maintenance (dont ceux liés à la batterie) et part du temps "
     "passé hors service, regroupés par lot pour repérer un lot défectueux.",
     ["lot_batterie", "engins", "tickets_batterie", "part_hors_service_moy_pct"]),
    ("gold_meteo_nonservice", "Météo et non-service",
     "une ville, un jour",
     "Met en regard la pluie, la température et le taux de non-service du jour, pour "
     "aider à expliquer les pics.",
     ["ville", "jour", "pluie_mm", "temp_c", "taux_non_service_pct"]),
]

for table, titre, maille, definition, apercu in INDICATEURS:
    lignes = sh.scalaire(f"SELECT count(*) FROM {table}")
    with st.expander(f"{titre}  —  {fr(lignes)} lignes"):
        st.markdown(f"**Maille** : {maille}")
        st.markdown(f"**Définition** : {definition}")
        st.caption(f"Table : {table}")
        cols = ", ".join(apercu)
        st.dataframe(q(f"SELECT {cols} FROM {table} LIMIT 8"), width='stretch', hide_index=True)
