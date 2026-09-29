"""
Chaîne quotidienne, du dépôt de 5 h à la publication du bulletin de 7 h 30.

Étapes, dans l'ordre (chacune dépend de la précédente) :
    ingestion → transformation → indicateurs → controle → publication

Chaque exécution est journalisée (étape, statut, durée, volumes lus/rejetés/publiés)
dans data/journal/executions.jsonl et dans une table de l'entrepôt.

Points clés :
- idempotence : un dépôt déjà publié n'est pas retraité (rien n'est dupliqué) ;
- reprise : on peut reprendre à une étape donnée ;
- simulation : --dry-run montre ce qui serait fait sans rien écrire ;
- porte qualité : contrôles bloquants avant publication (dont la détection d'un
  dépôt ré-émis en double) ;
- erreurs : nouvelle tentative sur erreur transitoire, arrêt propre, codes de
  sortie distincts selon la nature de l'échec.
"""
import json
import time
import hashlib
import glob
import pathlib
from datetime import datetime

import duckdb

from . import config as C
from .etl import Pipeline, _p
from .gold import build_gold
from .bulletin import generer_bulletin
from .run_backfill import historical_sources

# --- Codes de sortie (distincts selon la nature de l'échec) ------------------
EXIT_OK       = 0   # succès (publié) ou rien à faire (idempotent)
EXIT_CONTROLE = 2   # un contrôle bloquant a empêché la publication
EXIT_DONNEES  = 3   # dépôt manquant ou illisible
EXIT_ERREUR   = 4   # erreur inattendue

ETAPES = ["ingestion", "transformation", "indicateurs", "controle", "publication"]


class ErreurDonnees(Exception):
    """Dépôt manquant ou illisible."""


class ErreurControle(Exception):
    """Un contrôle bloquant a échoué : on ne publie pas."""


class ChaineJour:
    def __init__(self, date, dry_run=False, force=False,
                 accepter_doublons=False, simuler_transitoire=False):
        self.date = str(date)
        self.dry_run = dry_run
        self.force = force
        self.accepter_doublons = accepter_doublons
        self.simuler_transitoire = simuler_transitoire
        self._transitoire_deja_levee = False
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.con = duckdb.connect(str(C.WAREHOUSE))
        self.con.execute("SET TimeZone='UTC';")
        self._init_etat()

    # -- état persistant (journal, manifeste, publication) -------------------
    def _init_etat(self):
        self.con.execute("""CREATE TABLE IF NOT EXISTS _journal(
            run_id VARCHAR, date_traitee VARCHAR, etape VARCHAR, statut VARCHAR,
            duree_s DOUBLE, lignes_lues BIGINT, lignes_rejetees BIGINT,
            lignes_publiees BIGINT, horodatage TIMESTAMP, message VARCHAR)""")
        self.con.execute("""CREATE TABLE IF NOT EXISTS _manifeste(
            date_traitee VARCHAR, signature VARCHAR, statut VARCHAR, horodatage TIMESTAMP)""")
        self.con.execute("""CREATE TABLE IF NOT EXISTS _publication(
            date_traitee VARCHAR, horodatage TIMESTAMP, perimetre VARCHAR,
            engins_a_recharger BIGINT)""")

    def _log(self, etape, statut, duree=0.0, lues=0, rejetees=0, publiees=0, message=""):
        """Écrit une ligne de journal : dans l'entrepôt, dans le fichier JSONL, à l'écran."""
        self.con.execute("INSERT INTO _journal VALUES (?,?,?,?,?,?,?,?,?,?)",
                         [self.run_id, self.date, etape, statut, round(duree, 3),
                          int(lues), int(rejetees), int(publiees), datetime.now(), message])
        ligne = {"run_id": self.run_id, "date": self.date, "etape": etape, "statut": statut,
                 "duree_s": round(duree, 3), "lues": int(lues), "rejetees": int(rejetees),
                 "publiees": int(publiees), "horodatage": datetime.now().isoformat(timespec="seconds"),
                 "message": message}
        with open(C.JOURNAL / "executions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        drapeau = {"OK": "  ok ", "IGNORE": " skip", "BLOQUE": "BLOQ", "ECHEC": "ECHEC"}.get(statut, statut)
        print(f"[{drapeau}] {etape:<14} {duree:6.2f}s  lues={int(lues):<6} "
              f"rejetees={int(rejetees):<5} publiees={int(publiees):<4} {message}")

    # -- utilitaires ---------------------------------------------------------
    def _depot_dir(self):
        return C.DEPOTS / self.date

    def _fichiers_recherches_jour(self):
        return sorted(glob.glob(str(self._depot_dir() / "recherches_app" / "*.jsonl")))

    def _signature(self):
        """Empreinte du dépôt du jour (noms + tailles) : sert à repérer un dépôt identique."""
        h = hashlib.md5()
        for f in sorted(glob.glob(str(self._depot_dir() / "**" / "*"), recursive=True)):
            p = pathlib.Path(f)
            if p.is_file():
                h.update(p.name.encode())
                h.update(str(p.stat().st_size).encode())
        return h.hexdigest()

    def _sources_jusqua(self):
        """Fichiers à ingérer : historique + tous les dépôts jusqu'au jour traité inclus."""
        s = historical_sources()
        corresp = {"trajets": "trajets", "recherches": "recherches_app",
                   "telemetrie": "telemetrie", "interventions": "interventions_recharge",
                   "meteo": "meteo"}
        for dep in sorted(glob.glob(str(C.DEPOTS / "*"))):
            jour = pathlib.Path(dep).name
            if jour <= self.date:               # dépôts jusqu'au jour traité
                for cle, dossier in corresp.items():
                    s[cle] += sorted(glob.glob(str(pathlib.Path(dep) / dossier / "*")))
        return s

    def _avec_reprise(self, fn, tentatives=3, delai=0.5):
        """Rejoue une opération en cas d'erreur transitoire (ex. fichier momentanément verrouillé)."""
        for essai in range(1, tentatives + 1):
            try:
                return fn()
            except (OSError, IOError) as e:
                if essai == tentatives:
                    raise
                print(f"       tentative {essai} échouée ({e}); nouvelle tentative…")
                time.sleep(delai)

    # =====================================================================
    #  Étapes
    # =====================================================================
    def ingestion(self):
        depot = self._depot_dir()
        if not depot.exists():
            raise ErreurDonnees(f"aucun dépôt pour le {self.date} dans {C.DEPOTS.name}/")
        # volume brut du dépôt du jour (recherches, à titre indicatif pour le journal)
        fichiers = self._fichiers_recherches_jour()
        lues = 0
        if fichiers:
            liste = "[" + ",".join(f"'{_p(f)}'" for f in fichiers) + "]"
            lues = self.con.execute(
                f"SELECT count(*) FROM read_json_auto({liste}, format='newline_delimited', union_by_name=true)"
            ).fetchone()[0]

        def _charger():
            # simulation d'une erreur transitoire pour démontrer la reprise
            if self.simuler_transitoire and not self._transitoire_deja_levee:
                self._transitoire_deja_levee = True
                raise OSError("erreur transitoire simulée")
            p = Pipeline(con=self.con)
            p.init_quarantine()
            p.load_referentiels()
            p.bronze(self._sources_jusqua())
            return p

        if self.dry_run:
            return {"lues": lues, "message": f"[simulation] {len(fichiers)} fichier(s) recherches à ingérer"}
        self._pipeline = self._avec_reprise(_charger)
        return {"lues": lues, "message": "dépôt ingéré (bronze reconstruit)"}

    def transformation(self):
        if self.dry_run:
            return {"message": "[simulation] normalisation + qualité + RGPD"}
        p = getattr(self, "_pipeline", None) or Pipeline(con=self.con)
        p.run_silver()
        p.write_quality_report()
        p.export_parquet()
        rapport = (C.REPORTS / "rapport_qualite.csv").as_posix()
        quaran = (C.QUARANTINE / "quarantaine.csv").as_posix()
        p.sql(f"COPY (SELECT * FROM qualite_rapport ORDER BY source,regle) TO '{rapport}' (HEADER)")
        p.sql(f"COPY (SELECT * FROM quarantaine ORDER BY source,regle) TO '{quaran}' (HEADER)")
        # rejets attribués au jour : brut du dépôt - lignes conservées en Silver pour ce jour
        rej = self.con.execute(
            "SELECT count(*) FROM quarantaine").fetchone()[0]
        return {"rejetees": rej, "message": "silver construit (normalisé, dédupliqué, contrôlé)"}

    def indicateurs(self):
        if self.dry_run:
            return {"message": "[simulation] reconstruction des tables Gold"}
        build_gold(con=self.con)
        return {"message": "indicateurs (Gold) reconstruits"}

    def controle(self):
        """Porte qualité : contrôles bloquants avant publication."""
        d = self.date
        msgs = []

        # 1) Couverture : les 3 sources critiques du jour sont présentes en Silver.
        for table in ("silver_telemetrie", "silver_trajets", "silver_recherches"):
            n = self.con.execute(f"SELECT count(*) FROM {table} WHERE jour = ?", [d]).fetchone()[0]
            if n == 0:
                raise ErreurControle(f"aucune donnée {table.replace('silver_','')} pour le {d} "
                                     "→ publication bloquée. À prévenir : l'exploitation (Karim).")

        # 2) Doublons du dépôt : un taux élevé signale une ré-émission en double.
        fichiers = self._fichiers_recherches_jour()
        if fichiers:
            liste = "[" + ",".join(f"'{_p(f)}'" for f in fichiers) + "]"
            tot, dup = self.con.execute(f"""
                SELECT count(*) FILTER(WHERE recherche_id IS NOT NULL),
                       count(*) FILTER(WHERE recherche_id IS NOT NULL) - count(DISTINCT recherche_id)
                FROM read_json_auto({liste}, format='newline_delimited', union_by_name=true)
            """).fetchone()
            taux_dup = round(100 * dup / tot, 1) if tot else 0
            if taux_dup > 30 and not self.accepter_doublons:
                raise ErreurControle(
                    f"taux de doublons du dépôt recherches = {taux_dup}% (seuil 30%) : "
                    "dépôt vraisemblablement ré-émis en double → publication bloquée. "
                    "À prévenir : l'exploitation (Karim). Reprise : relancer avec "
                    "--accepter-doublons une fois la ré-émission confirmée.")
            msgs.append(f"doublons dépôt {taux_dup}%")

        # 3) Cohérence : le nombre d'engins suivis ne dépasse pas la flotte connue.
        flotte = self.con.execute("SELECT count(*) FROM ref_engins").fetchone()[0]
        suivis = self.con.execute(
            "SELECT count(DISTINCT engin_id) FROM gold_flotte_reveil WHERE jour = ?", [d]).fetchone()[0]
        if suivis > flotte:
            raise ErreurControle(f"{suivis} engins suivis > {flotte} au référentiel → incohérence, publication bloquée.")

        return {"message": "contrôles passés (" + ", ".join(msgs) + ")" if msgs else "contrôles passés"}

    def publication(self):
        d = self.date
        if self.dry_run:
            return {"message": "[simulation] génération du bulletin (non écrit)"}
        chemin, total = generer_bulletin(self.con, d)
        # trace de fraîcheur / périmètre pour l'interface
        self.con.execute("DELETE FROM _publication WHERE date_traitee = ?", [d])
        self.con.execute("INSERT INTO _publication VALUES (?,?,?,?)",
                         [d, datetime.now(), f"journée {d}", int(total)])
        # manifeste : marque le dépôt comme publié
        self.con.execute("DELETE FROM _manifeste WHERE date_traitee = ?", [d])
        self.con.execute("INSERT INTO _manifeste VALUES (?,?,?,?)",
                         [d, self._signature(), "publie", datetime.now()])
        return {"publiees": total, "message": f"bulletin publié : {chemin.name}"}

    # =====================================================================
    #  Orchestration
    # =====================================================================
    def executer(self, depuis=None):
        debut = ETAPES.index(depuis) if depuis else 0

        # Idempotence : si le même dépôt a déjà été publié, on ne refait rien.
        if debut == 0 and not self.force and not self.dry_run:
            deja = self.con.execute(
                "SELECT signature FROM _manifeste WHERE date_traitee = ? AND statut = 'publie'",
                [self.date]).fetchone()
            if deja and deja[0] == self._signature():
                for e in ETAPES:
                    self._log(e, "IGNORE", message="déjà traité, rien à refaire")
                print(f"→ Journée {self.date} déjà publiée : aucune duplication, aucun retraitement.")
                self.con.close()
                return EXIT_OK

        methodes = {"ingestion": self.ingestion, "transformation": self.transformation,
                    "indicateurs": self.indicateurs, "controle": self.controle,
                    "publication": self.publication}
        try:
            for etape in ETAPES[debut:]:
                t0 = time.perf_counter()
                res = methodes[etape]() or {}
                self._log(etape, "OK", duree=time.perf_counter() - t0,
                          lues=res.get("lues", 0), rejetees=res.get("rejetees", 0),
                          publiees=res.get("publiees", 0), message=res.get("message", ""))
            print(f"→ Journée {self.date} : chaîne terminée avec succès.")
            return EXIT_OK
        except ErreurControle as e:
            self._log("controle", "BLOQUE", message=str(e))
            self.con.execute("DELETE FROM _manifeste WHERE date_traitee = ?", [self.date])
            self.con.execute("INSERT INTO _manifeste VALUES (?,?,?,?)",
                             [self.date, self._signature(), "bloque", datetime.now()])
            print(f"→ Journée {self.date} : publication BLOQUÉE par la porte qualité.")
            return EXIT_CONTROLE
        except ErreurDonnees as e:
            self._log("ingestion", "ECHEC", message=str(e))
            print(f"→ Journée {self.date} : arrêt, données manquantes.")
            return EXIT_DONNEES
        except Exception as e:                       # arrêt propre sur erreur inattendue
            self._log("erreur", "ECHEC", message=f"{type(e).__name__}: {e}")
            print(f"→ Journée {self.date} : arrêt sur erreur inattendue.")
            return EXIT_ERREUR
        finally:
            self.con.close()
