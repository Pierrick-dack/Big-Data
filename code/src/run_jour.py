"""
Interface en ligne de commande de la chaîne quotidienne.

Exemples :
    python -m src.run_jour --date 2026-09-14                 # traiter une journée
    python -m src.run_jour --date 2026-09-14 --dry-run       # simuler, sans rien écrire
    python -m src.run_jour --date 2026-09-15 --depuis controle   # reprendre à une étape
    python -m src.run_jour --date 2026-09-15 --accepter-doublons # publier malgré une ré-émission

Code de sortie : 0 succès, 2 bloqué par la porte qualité, 3 données manquantes,
4 erreur inattendue.
"""
import argparse
import sys

from .orchestrateur import ChaineJour, ETAPES


def main(argv=None):
    ap = argparse.ArgumentParser(description="Chaîne quotidienne MobiCity (dépôt 5 h → bulletin 7 h 30).")
    ap.add_argument("--date", required=True, help="journée à traiter, au format AAAA-MM-JJ")
    ap.add_argument("--depuis", choices=ETAPES, help="reprendre à cette étape")
    ap.add_argument("--dry-run", action="store_true", help="simuler : montrer les étapes sans rien écrire")
    ap.add_argument("--force", action="store_true", help="retraiter même si la journée est déjà publiée")
    ap.add_argument("--accepter-doublons", action="store_true",
                    help="publier malgré un taux de doublons élevé (ré-émission confirmée)")
    ap.add_argument("--simuler-erreur-transitoire", action="store_true",
                    help="lever une erreur transitoire à la 1re tentative (démonstration de la reprise)")
    a = ap.parse_args(argv)

    chaine = ChaineJour(a.date, dry_run=a.dry_run, force=a.force,
                        accepter_doublons=a.accepter_doublons,
                        simuler_transitoire=a.simuler_erreur_transitoire)
    code = chaine.executer(depuis=a.depuis)
    sys.exit(code)


if __name__ == "__main__":
    main()
