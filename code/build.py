"""
Construit toute la chaîne en une seule commande, à lancer depuis le dossier code/ :

    python build.py

Lancer un script place automatiquement son dossier (code/) sur le chemin d'import :
cette méthode fonctionne avec toutes les installations de Python, y compris celle
du Microsoft Store, contrairement à « python -m … » qui dépend du dossier courant.
Ensuite, ouvrir l'interface avec :  streamlit run app/streamlit_app.py
"""
from src.run_backfill import main as construire_couches
from src.gold import build_gold
from src.build_dossier import generer

if __name__ == "__main__":
    print(">> 1/3  Bronze + Silver + Parquet + rapports de qualité")
    construire_couches()
    print("\n>> 2/3  Tables d'indicateurs (Gold)")
    build_gold()
    print("\n>> 3/3  Dossier technique")
    generer()
    print("\nTermine. Interface :  streamlit run app/streamlit_app.py")
