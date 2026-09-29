"""Page « Bulletin de 7 h 30 ».

Affiche le dernier bulletin produit par la chaîne quotidienne et permet de le
télécharger. Le bulletin est un fichier HTML autonome, lisible sur téléphone.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import streamlit as st
import _shared as sh

C = sh.C

st.set_page_config(page_title="Bulletin de 7 h 30", layout="wide")
sh.exiger_entrepot()

st.title("Bulletin de 7 h 30")
st.write("Ce bulletin est produit automatiquement par la chaîne quotidienne, à "
         "destination de l'exploitation. C'est un fichier HTML autonome : il s'ouvre "
         "sur un téléphone ou un poste sans rien installer.")

# Liste des bulletins disponibles
bulletins = sorted(C.BULLETINS.glob("bulletin_*.html"), reverse=True)
if not bulletins:
    st.write("Aucun bulletin n'a encore été produit. Lancer la chaîne quotidienne, "
             "par exemple : `python jour.py --date 2026-09-14`.")
    st.stop()

noms = [b.stem.replace("bulletin_", "") for b in bulletins]
choix = st.selectbox("Journée", noms, index=0)
fichier = C.BULLETINS / f"bulletin_{choix}.html"
contenu = fichier.read_text(encoding="utf-8")

st.download_button("Télécharger ce bulletin (HTML)", data=contenu,
                   file_name=fichier.name, mime="text/html")

st.divider()
st.markdown("**Aperçu**")
# Aperçu dans un cadre isolé. On tente le rendu inline ; sinon le téléchargement suffit.
try:
    import streamlit.components.v1 as components
    components.html(contenu, height=900, scrolling=True)
except Exception:
    import base64
    b64 = base64.b64encode(contenu.encode("utf-8")).decode("ascii")
    st.markdown(
        f'<iframe src="data:text/html;base64,{b64}" width="100%" height="900" '
        'style="border:1px solid #8883;border-radius:6px;"></iframe>',
        unsafe_allow_html=True)
