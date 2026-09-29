"""
Lanceur de la chaîne quotidienne, à utiliser depuis le dossier code/ :

    python jour.py --date 2026-09-14
    python jour.py --date 2026-09-15 --accepter-doublons

Passe les arguments à l'interface en ligne de commande. Comme build.py, cette
forme fonctionne avec toutes les installations de Python (y compris Microsoft Store).
"""
from src.run_jour import main

if __name__ == "__main__":
    main()
