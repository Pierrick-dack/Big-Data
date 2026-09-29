"""
Bulletin d'exploitation de 7 h 30 pour Karim.

Produit un fichier HTML autonome (styles inclus, lisible sur téléphone comme sur
poste), horodaté, à partir des tables Gold. Aucune dépendance externe : il
s'ouvre d'un double-clic, sans rien installer.
"""
from datetime import datetime
from . import config as C

# Petit gabarit HTML, volontairement sobre et responsive (une seule colonne).
_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       margin: 0; padding: 16px; max-width: 720px; margin-inline: auto;
       line-height: 1.5; }
h1 { font-size: 1.4rem; margin: 0 0 4px; }
h2 { font-size: 1.1rem; margin: 24px 0 8px; border-bottom: 1px solid #8883; padding-bottom: 4px; }
.entete { color: #666; font-size: .9rem; margin-bottom: 8px; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #8882; }
th { font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.pied { color: #888; font-size: .8rem; margin-top: 28px; }
"""


def _table(colonnes, lignes, colonnes_num=()):
    """Construit un tableau HTML simple à partir de lignes (liste de tuples)."""
    th = "".join(f"<th>{c}</th>" for c in colonnes)
    corps = ""
    for lg in lignes:
        tds = ""
        for i, val in enumerate(lg):
            classe = ' class="num"' if colonnes[i] in colonnes_num else ""
            tds += f"<td{classe}>{val}</td>"
        corps += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{th}</tr></thead><tbody>{corps}</tbody></table>"


def generer_bulletin(con, date):
    """Génère le bulletin du jour `date`. Retourne (chemin, nb_engins_a_recharger)."""
    d = str(date)
    genere_le = datetime.now().strftime("%d/%m/%Y à %H:%M")

    # 1) Engins à recharger par ville (résumé)
    par_ville = con.execute("""
        SELECT ville, a_recharger, inutilisables
        FROM gold_flotte_synthese WHERE jour = ? ORDER BY a_recharger DESC""", [d]).fetchall()
    total_recharge = sum(r[1] for r in par_ville) if par_ville else 0

    # 2) Liste actionnable : engins sous le seuil, du plus critique au moins critique
    a_recharger = con.execute("""
        SELECT ville, engin_id, type_engin, batterie_pct, statut
        FROM gold_flotte_reveil WHERE jour = ? AND en_alerte
        ORDER BY batterie_pct LIMIT 40""", [d]).fetchall()

    # 3) Où la demande risque de ne pas être servie (stations à réalimenter en priorité)
    stations = con.execute("""
        SELECT station, ville, taux_non_service_pct, sans_engin
        FROM (SELECT station, ville, sum(sans_engin) sans_engin, sum(recherches) rech,
                     round(100.0*sum(sans_engin)/nullif(sum(recherches),0),1) taux_non_service_pct
              FROM gold_non_service WHERE jour = ? GROUP BY station, ville)
        WHERE rech > 20 ORDER BY sans_engin DESC LIMIT 8""", [d]).fetchall()

    html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bulletin d'exploitation — {d}</title>
<style>{_STYLE}</style></head><body>
<h1>Bulletin d'exploitation</h1>
<div class="entete">Journée du {d} · généré le {genere_le} · données arrêtées à cette journée</div>

<h2>Engins à recharger — {total_recharge} au total</h2>
{_table(["Ville", "À recharger", "Inutilisables"],
        [(v, a, i) for (v, a, i) in par_ville],
        colonnes_num=["À recharger", "Inutilisables"]) if par_ville
   else "<p>Aucune donnée de flotte pour cette journée.</p>"}

<h2>Priorité de recharge (batteries les plus basses)</h2>
{_table(["Ville", "Engin", "Type", "Batterie %", "Statut"],
        [(v, e, t, b, s) for (v, e, t, b, s) in a_recharger],
        colonnes_num=["Batterie %"]) if a_recharger
   else "<p>Aucun engin sous le seuil d'alerte.</p>"}

<h2>Stations à réalimenter en priorité</h2>
{_table(["Station", "Ville", "Non-service %", "Recherches sans engin"],
        [(st, v, tx, se) for (st, v, tx, se) in stations],
        colonnes_num=["Non-service %", "Recherches sans engin"]) if stations
   else "<p>Pas de tension notable sur les stations.</p>"}

<div class="pied">MobiCity — bulletin automatique. Chiffres calculés depuis l'entrepôt,
données pseudonymisées. Pour le détail et l'historique, voir l'interface d'analyse.</div>
</body></html>"""

    C.BULLETINS.mkdir(parents=True, exist_ok=True)
    chemin = C.BULLETINS / f"bulletin_{d}.html"
    chemin.write_text(html, encoding="utf-8")
    # copie "dernier bulletin" pour un accès stable
    (C.BULLETINS / "dernier.html").write_text(html, encoding="utf-8")
    return chemin, total_recharge
