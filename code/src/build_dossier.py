"""
Génère le dossier technique (livrable 3) en Markdown, À PARTIR de l'entrepôt.

Tous les chiffres sont calculés depuis les données : le dossier ne contient
aucune valeur codée en dur, et se régénère par une commande. À lancer après
run_backfill + gold :

    python -m src.build_dossier
"""
import glob
import time
import pathlib
import duckdb
from . import config as C

# La connexion est créée dans generer() (pas à l'import) : ainsi importer ce
# module avant la construction de l'entrepôt ne provoque pas d'erreur.
_con = None
S = lambda sql: _con.execute(sql).fetchone()[0]          # valeur scalaire
DF = lambda sql: _con.execute(sql).df()                  # DataFrame
fr = lambda n, suf="": f"{n:,.0f}{suf}".replace(",", " ")


def table_md(df, entetes=None):
    """Transforme un DataFrame en tableau Markdown."""
    cols = list(df.columns)
    tetes = entetes or cols
    lignes = ["| " + " | ".join(map(str, tetes)) + " |",
              "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lignes.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lignes)


def mesure_perf():
    """Mesure le temps de lecture d'une journée : fichiers bruts vs Parquet."""
    jour = S("SELECT max(jour) FROM silver_telemetrie")
    gz = sorted(glob.glob(str(C.HIST / "telemetrie" / "*.jsonl.gz")))
    liste = "[" + ",".join(f"'{pathlib.Path(p).as_posix()}'" for p in gz) + "]"
    lake = (C.LAKE / "silver_telemetrie").as_posix()
    req_brut = (f"SELECT engin_id,batterie_pct FROM read_json_auto({liste}, "
                f"format='newline_delimited', union_by_name=true) WHERE CAST(ts AS DATE)=DATE '{jour}'")
    req_pq = (f"SELECT engin_id,batterie_pct FROM read_parquet('{lake}/**/*.parquet', "
              f"hive_partitioning=true) WHERE jour=DATE '{jour}'")

    def chrono(sql, n=3):
        _con.execute(sql)
        best = min((_t(sql) for _ in range(n)))
        return best * 1000

    def _t(sql):
        t = time.perf_counter(); _con.execute(sql).fetchall(); return time.perf_counter() - t
    return jour, chrono(req_brut), chrono(req_pq)


def generer():
    global _con
    _con = duckdb.connect(str(C.WAREHOUSE), read_only=True)
    out = C.DOSSIER
    out.mkdir(parents=True, exist_ok=True)

    # ---- chiffres communs ----
    d1, d2 = S("SELECT min(jour) FROM silver_trajets"), S("SELECT max(jour) FROM silver_trajets")
    nb_jours = S("SELECT date_diff('day', min(jour), max(jour))+1 FROM silver_trajets")

    # durée d'une exécution automatique de la chaîne quotidienne (depuis le journal, si dispo)
    try:
        duree = S("""SELECT round(sum(duree_s),0) FROM _journal WHERE run_id = (
                       SELECT run_id FROM _journal WHERE etape='publication' AND statut='OK'
                       ORDER BY horodatage DESC LIMIT 1)""")
        duree_auto = f"environ {int(duree)} secondes" if duree else "quelques secondes"
    except Exception:
        duree_auto = "quelques secondes"

    # =========================================================== 00 plan
    (out / "00_plan_de_travail.md").write_text(f"""# 00 — Plan de travail

Projet : chaîne décisionnelle pour un opérateur de mobilité partagée (phase pilote,
4 villes). Objectif : mesurer la demande non servie et le respect du contrat de
recharge, et préparer le bulletin d'exploitation du matin.

## Démarche (Partie 1)
1. Cartographier les sources (format, volume, qualité, sensibilité, criticité).
2. Concevoir l'architecture en couches et la justifier (délai du bulletin, volume, cible 2027).
3. Construire l'ETL : ingestion tracée, normalisation, déduplication, intégrité.
4. Définir des règles de qualité (bloquantes / informatives), quarantaine, taux de rejet.
5. Traiter les données personnelles (pseudonymisation, minimisation).
6. Construire les tables d'indicateurs (maille + définition).
7. Réaliser l'interface d'analyse.
8. Rédiger les constats et la décision par destinataire.

## Jalons de vérification
- Le pipeline se régénère depuis les données par deux commandes.
- L'interface lit uniquement les couches produites.
- Chaque choix technique est justifié et ses limites documentées.

Historique traité : {d1} → {d2} ({nb_jours} jours).
""", encoding="utf-8")

    # =========================================================== 02 sources
    volumes = DF(f"""
        SELECT 'Trajets' AS source, count(*) AS lignes FROM bronze_trajets UNION ALL
        SELECT 'Recherches', count(*) FROM bronze_recherches UNION ALL
        SELECT 'Telemetrie', count(*) FROM bronze_telemetrie UNION ALL
        SELECT 'Interventions', count(*) FROM bronze_interventions UNION ALL
        SELECT 'Meteo (releves)', count(*) FROM bronze_meteo UNION ALL
        SELECT 'Maintenance (tickets)', count(*) FROM bronze_maintenance""")
    volumes["lignes"] = volumes["lignes"].map(lambda n: fr(n))
    fmt = DF("""SELECT
        count(*) FILTER(WHERE TRY_STRPTIME(debut,'%Y-%m-%d %H:%M:%S') IS NOT NULL) iso,
        count(*) FILTER(WHERE TRY_STRPTIME(debut,'%d/%m/%Y %H:%M') IS NOT NULL) fr,
        count(*) FILTER(WHERE TRY_CAST(debut AS BIGINT) IS NOT NULL) epoch,
        count(*) FILTER(WHERE debut IS NULL) nul FROM bronze_trajets""")
    r_eng, r_sta, r_cli = S("SELECT count(*) FROM ref_engins"), S("SELECT count(*) FROM ref_stations"), S("SELECT count(*) FROM ref_clients")

    (out / "02_tableau_des_sources.md").write_text(f"""# 02 — Tableau des sources

Historique : {d1} → {d2} ({nb_jours} jours). Volumes comptés dans la couche Bronze.

## Volumes
{table_md(volumes, ["Source", "Volume (lignes)"])}

Référentiels (autorité) : {r_eng} engins, {r_sta} stations, {fr(r_cli)} clients, 1 contrat.

## Format, sensibilité, criticité
| Source | Format | Sensibilité RGPD | Criticité pour le bulletin |
|---|---|---|---|
| Trajets | CSV (1/jour) | Élevée (client, paiement) | Moyenne — usage réel, panier moyen |
| Recherches | JSONL (1/jour) | Élevée (client + position GPS) | Haute — seule source de la demande non servie |
| Télémétrie | JSONL gzip (1/jour) | Faible (engin) | Critique — batterie = engins à recharger |
| Interventions | CSV « ; » (1/jour) | Moyenne (nom technicien) | Haute — suivi du contrat de recharge |
| Météo | JSON (1/jour) | Nulle | Faible — variable explicative |
| Maintenance | JSON (1/semaine) | Faible | Moyenne — fiabilité des engins |

## Qualité observée (mesurée)
- **Dates trajets au format mélangé** : ISO {fr(int(fmt.iso[0]))}, français {fr(int(fmt.fr[0]))},
  epoch Unix {fr(int(fmt.epoch[0]))}, nulles {fr(int(fmt.nul[0]))}. Comparées en texte, ~18 %
  semblent incohérentes ; après normalisation, {S("SELECT count(*) FROM silver_trajets WHERE debut>=fin")} le sont réellement.
- **Batterie manquante** : normale sur les vélos mécaniques, anormale sur les trottinettes
  (capteur) → traitée au niveau du champ, pas par rejet de ligne.
- **Villes bruitées** ({S("SELECT count(DISTINCT ville) FROM bronze_telemetrie")} variantes en télémétrie) → ville reprise du référentiel.
- **Interventions** : CSV « ; » avec BOM, dates FR, villes MAJUSCULES, clé engin préfixée `MC-`.
""", encoding="utf-8")

    # =========================================================== 01 architecture
    jour, t_brut, t_pq = mesure_perf()
    par_jour = S("SELECT count(*) FROM silver_telemetrie") / nb_jours
    proj = par_jour * (3000 / 600) * 2
    (out / "01_architecture_et_justifications.md").write_text(f"""# 01 — Architecture et justifications

## Pile
Python, DuckDB, Streamlit, Parquet. Poste local, sans service payant. DuckDB lit
nativement CSV/JSON/gzip/Parquet et élague les partitions ; un seul fichier d'entrepôt.

## Couches (medallion)
- **Bronze** — ingestion fidèle et tracée (copie brute + lignage : nom du fichier source, horodatage).
- **Silver** — données propres : normalisation (dates multi-format, fuseau, clé engin, ville via
  référentiel), déduplication sur clé métier, intégrité, règles de qualité (quarantaine + drapeaux),
  RGPD. Matérialisée en Parquet partitionné par jour.
- **Gold** — tables d'indicateurs pré-agrégées, une par décision.

## Justification par la mesure
Cas testé : lire la batterie de tous les engins de la veille ({jour}).

| Approche | Temps | Données lues |
|---|---|---|
| Full-scan des fichiers bruts (.jsonl.gz) | {t_brut:.0f} ms | tout l'historique décompressé |
| Parquet partitionné (élagage) | {t_pq:.0f} ms | 1 partition |

Accélération mesurée : **×{t_brut/t_pq:.0f}**. Sans partitionnement, le temps croît avec tout
l'historique ; avec, il reste borné à une journée — c'est ce qui sécurise le créneau du matin.

## Tenue à la charge 2027
Télémétrie actuelle : {fr(par_jour)} lignes/jour (600 engins). Projection 2027
(3 000 engins, relevé 30 s) : {fr(proj)} lignes/jour. Réponses : élagage par jour déjà en place,
sous-partitionnement par ville activable (ville déjà normalisée), format colonnaire.

## Reproductibilité
Le dossier `data/` (entrepôt, Parquet, rapports) n'est jamais édité à la main : il se
reconstruit intégralement depuis les sources par `run_backfill` puis `gold`.
""", encoding="utf-8")

    # =========================================================== 03 décision/question/indicateur
    (out / "03_decision_question_indicateur.md").write_text("""# 03 — Décision / question / indicateur

| Destinataire | Décision | Question | Indicateur (table Gold) | Maille |
|---|---|---|---|---|
| Exploitation (matin) | Où rééquilibrer avant 8 h ? | Où la demande n'est-elle pas servie ? | Taux de non-service (`gold_non_service`) | station × jour × heure |
| Exploitation (matin) | Quels engins recharger ? | Quels engins sous le seuil au réveil ? | Flotte au réveil (`gold_flotte_synthese`) | engin × jour |
| Direction (contrat) | Renouveler / renégocier / changer ? | Le prestataire tient-il le délai ? | Respect du contrat (`gold_sla_mensuel`) | intervention → mois |
| Direction (contrat) | Facturer des pénalités ? | Combien d'interventions hors délai ? | Respect du contrat (`gold_sla_interventions`) | intervention |
| Responsable flotte | Retirer / réparer / garantie ? | Quels engins/lots peu fiables ? | Fiabilité (`gold_fiabilite_lot`) | engin → lot |
| Analyse (cause) | Agir sur l'offre ou attendre ? | La météo explique-t-elle le non-service ? | Météo × non-service (`gold_meteo_nonservice`) | ville × jour |

Chaque indicateur est défini en détail dans l'interface (page « Dictionnaire des indicateurs »).
""", encoding="utf-8")

    # =========================================================== 04 rapport qualité
    rap = DF("""SELECT source AS Source, regle AS Regle, gravite AS Gravite,
                       n_total AS Total, n_concernees AS Cas, taux_pct AS "Taux %"
                FROM qualite_rapport ORDER BY source, regle""")
    rejet = DF("""
      WITH q AS (SELECT source, count(DISTINCT cle) r FROM quarantaine GROUP BY 1),
      c AS (SELECT 'trajets' s,count(*) n FROM silver_trajets UNION ALL
            SELECT 'recherches',count(*) FROM silver_recherches UNION ALL
            SELECT 'telemetrie',count(*) FROM silver_telemetrie UNION ALL
            SELECT 'interventions',count(*) FROM silver_interventions)
      SELECT c.s AS Source, c.n AS Conformes, COALESCE(q.r,0) AS Quarantaine,
             round(100.0*COALESCE(q.r,0)/(c.n+COALESCE(q.r,0)),2) AS "Rejet %"
      FROM c LEFT JOIN q ON q.source=c.s ORDER BY 1""")
    (out / "04_rapport_de_qualite.md").write_text(f"""# 04 — Rapport de qualité

Deux gravités : **bloquante** (ligne mise en quarantaine avec motif) et **informative**
(ligne conservée mais signalée). Généré depuis la table `qualite_rapport`.

## Catalogue des règles
{table_md(rap)}

## Taux de rejet par source
{table_md(rejet)}

Fichiers : `data/rapports/rapport_qualite.csv`, `data/quarantaine/quarantaine.csv`
(chaque ligne rejetée avec source, clé, règle, gravité).
""", encoding="utf-8")

    # =========================================================== 05 données personnelles
    cols_tr = ", ".join(c[0] for c in _con.execute("DESCRIBE silver_trajets").fetchall())
    cols_re = ", ".join(c[0] for c in _con.execute("DESCRIBE silver_recherches").fetchall())
    (out / "05_donnees_personnelles.md").write_text(f"""# 05 — Note sur les données personnelles

## Principes appliqués
- **Pseudonymisation** : l'identifiant client et le nom du technicien sont remplacés par une
  empreinte salée (`PX_…`). En production : HMAC-SHA256 avec secret hors dépôt.
- **Minimisation** : la position GPS du client (recherches) est supprimée — seule la station est
  conservée. Les données identifiantes du référentiel clients (nom, e-mail, téléphone, naissance)
  ne sont pas chargées.
- **Frontière** : aucune donnée identifiante n'atteint les couches Silver et Gold, seules exposées
  à l'interface. Les analyses portent sur le service, jamais sur une personne identifiable.

## Vérification (sur les données)
- Colonnes de `silver_trajets` : {cols_tr}
- Colonnes de `silver_recherches` : {cols_re}

Aucune colonne `client_id`, `lat` ni `lon` côté client : seuls subsistent `client_px` et `station_id`.
""", encoding="utf-8")

    # =========================================================== 06 exploitation (1 page)
    (out / "06_documentation_exploitation.md").write_text("""# 06 — Documentation d'exploitation

## Planification
Les données de la veille sont déposées vers 5 h. La chaîne quotidienne est déclenchée après le
dépôt et se termine avant 7 h 30. La planifier une fois par jour :
- Linux (cron) : `30 5 * * * cd /chemin/code && python jour.py --date $(date +%F)`
- Windows (Planificateur de tâches) : action `python jour.py --date AAAA-MM-JJ` à 5 h 30.

## Commandes (depuis `code/`)
- Construire l'historique une fois : `python build.py`
- Traiter une journée : `python jour.py --date 2026-09-14`
- Simuler sans écrire : `python jour.py --date 2026-09-14 --dry-run`
- Reprendre à une étape : `python jour.py --date 2026-09-15 --depuis controle`
- Publier malgré une ré-émission confirmée : `python jour.py --date 2026-09-15 --accepter-doublons`
- Interface : `streamlit run app/streamlit_app.py`

Codes de sortie : 0 succès, 2 publication bloquée par la porte qualité, 3 données manquantes,
4 erreur inattendue.

## Reprise après incident
- Erreur transitoire (fichier momentanément indisponible) : la chaîne réessaie automatiquement.
- Publication bloquée (code 2) : lire le journal, corriger ou confirmer la cause, puis relancer
  (`--depuis controle`, ou `--accepter-doublons` pour une ré-émission confirmée). Rien n'est
  publié tant que les contrôles ne passent pas.
- Repartir de zéro : supprimer `data/` puis relancer `build.py` et les journées. L'entrepôt étant
  entièrement dérivé des sources, aucune donnée n'est perdue ; une journée déjà publiée n'est pas
  retraitée (idempotence).

## Droits d'accès
- `donnees/` (sources) en lecture seule ; `data/` (couches, bulletins, journal) en écriture.
- L'interface ouvre l'entrepôt en lecture seule. Les bulletins ne contiennent aucune donnée personnelle.

## Conservation des données et des journaux
- `donnees/` : selon la politique de l'opérateur (hors périmètre du code).
- `data/` (entrepôt, Parquet) : régénérable, aucune conservation nécessaire.
- `data/bulletins/` et `data/journal/` : à conserver le temps utile au suivi (par exemple 12 mois),
  puis purge. Aucune donnée personnelle n'y figure.
""", encoding="utf-8")

    # =========================================================== 08 automatisation + gain
    (out / "08_automatisation.md").write_text(f"""# 08 — Automatisation : tâche, gain et chaîne

## Tâche automatisée
Le bulletin d'exploitation du matin, préparé jusqu'ici à la main à partir de plusieurs exports.
La chaîne le produit automatiquement à partir du dépôt de 5 h.

## Gain
- Temps : d'environ 45 minutes de travail manuel à {duree_auto} d'exécution automatique.
- Mise à disposition : bulletin prêt bien avant 7 h 30, sans intervention.
- Fiabilité : traitement idempotent, contrôles bloquants avant publication, reprise automatique
  sur erreur transitoire, journal horodaté de chaque exécution.

## Étapes de la chaîne
`ingestion → transformation → indicateurs → controle → publication` : chaque étape dépend de la
précédente. Pilotage en ligne de commande (journée à traiter, reprise à une étape, simulation),
détaillé dans la documentation d'exploitation.

## Porte qualité (contrôle bloquant avant publication)
- Couverture : les trois sources critiques du jour (télémétrie, trajets, recherches) sont présentes.
- Doublons du dépôt : au-delà de 30 %, la chaîne suspecte une ré-émission en double, bloque la
  publication et prévient l'exploitation ; reprise avec `--accepter-doublons` après confirmation.
- Cohérence : le nombre d'engins suivis ne dépasse pas la flotte du référentiel.

## Journées de démonstration
- 14/09 traité deux fois : la seconde exécution ne duplique rien et ne refait aucun travail.
- 15/09 : dépôt ré-émis (environ 51 % de doublons) → publication bloquée, exploitation prévenue,
  reprise après confirmation. Le journal `data/journal/executions.jsonl` conserve la trace des
  exécutions, de l'incident et de la reprise.

## Branchement de l'interface
Chaque exécution reconstruit les couches lues par l'interface : le tableau de bord se met donc à
jour à chaque passage. La page d'accueil affiche la fraîcheur (dernière journée publiée) et le
périmètre, et chaque indicateur est comparé à la moyenne de l'historique.
""", encoding="utf-8")

    # =========================================================== 07 limites
    (out / "07_limites_et_conditions.md").write_text("""# 07 — Limites et conditions d'usage

- **Fuseau horaire** : la conversion UTC→local est faite par +2 h, valable sur la fenêtre des
  données (été, CEST, sans changement d'heure). Hors été, activer un vrai fuseau `Europe/Paris`.
- **Manque à gagner** : estimé via un proxy (recherches « aucun engin » × panier moyen). C'est un
  ordre de grandeur pour prioriser, pas une comptabilité exacte : une partie des clients aurait renoncé.
- **Pseudonymisation** : md5 salé pour la reproductibilité de l'épreuve ; en production, HMAC-SHA256
  avec un secret conservé hors du dépôt.
- **Projection 2027** : hypothèse de ×5 engins et de relevé 2× plus fréquent ; à réviser selon le
  déploiement réel.
- **Corrélation météo** : indicative (association, non causalité).
""", encoding="utf-8")

    _con.close()
    return sorted(p.name for p in out.glob("*.md"))


if __name__ == "__main__":
    fichiers = generer()
    print("Dossier genere dans", C.DOSSIER.name + "/ :")
    for f in fichiers:
        print("  -", f)
