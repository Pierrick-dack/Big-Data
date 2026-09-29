"""
Régénère le dossier technique seul, depuis le dossier code/ :

    python dossier.py

À lancer après build.py (et éventuellement après quelques exécutions de jour.py,
pour que le gain chiffré reflète une exécution réelle).
"""
from src.build_dossier import generer

if __name__ == "__main__":
    fichiers = generer()
    print("Dossier régénéré :")
    for f in fichiers:
        print("  -", f)
