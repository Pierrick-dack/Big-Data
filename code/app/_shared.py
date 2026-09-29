"""
Fonctions communes à toutes les pages de l'interface.

Chaque page importe ce module pour : se connecter à l'entrepôt, lancer des
requêtes (mises en cache), vérifier que l'entrepôt existe, et formater les
nombres à la française. Centraliser ici évite de répéter le même code partout.
"""
import sys
import pathlib

# Rend le projet importable (accès à src/config) quel que soit l'endroit d'où
# Streamlit est lancé : on remonte jusqu'au dossier qui contient "src".
_ICI = pathlib.Path(__file__).resolve()
RACINE = next(p for p in _ICI.parents if (p / "src").is_dir())
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import duckdb
import streamlit as st
from src import config as C


@st.cache_resource
def connexion():
    """Ouvre une connexion unique (lecture seule) à l'entrepôt, réutilisée
    par toutes les pages tant que l'app tourne."""
    return duckdb.connect(str(C.WAREHOUSE), read_only=True)


@st.cache_data(show_spinner=False)
def interroger(sql: str, params: tuple = ()):
    """Exécute une requête SQL et renvoie un DataFrame. Le résultat est mis en
    cache : la même requête ne frappe l'entrepôt qu'une fois."""
    return connexion().execute(sql, list(params)).df()


def scalaire(sql: str, params: tuple = ()):
    """Renvoie la première valeur de la première ligne (un compteur, une moyenne…)."""
    return connexion().execute(sql, list(params)).fetchone()[0]


def exiger_entrepot():
    """Affiche un message clair et arrête la page si l'entrepôt n'a pas encore
    été construit. À appeler en tête de chaque page."""
    if not C.WAREHOUSE.exists():
        st.title("Entrepôt non construit")
        st.markdown(
            "Cette interface lit les tables produites par la chaîne. "
            "Il faut d'abord la construire, depuis le dossier `code/` :\n\n"
            "```bash\npython build.py\n```")
        st.caption(f"Données sources détectées : {C.DATA_SRC} "
                   f"({'trouvées' if C.DATA_SRC.exists() else 'introuvables'})")
        st.stop()


def fr(nombre, suffixe: str = "") -> str:
    """Formate un entier à la française : 68 057 plutôt que 68,057."""
    return f"{nombre:,.0f}{suffixe}".replace(",", " ")
