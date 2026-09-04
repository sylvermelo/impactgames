"""
Tests des sources de données (`sources.py`).
============================================================================
Ces tests ne touchent pas au réseau : `_get` est bouchonné. Ce qu'on vérifie,
c'est le TRAVAIL fait autour de la réponse — découpage des fenêtres de dates,
lecture du JSON d'ESPN, réassemblage domicile/extérieur, repli d'une source sur
l'autre — parce que ce sont exactement les endroits où la plateforme s'est
cassée en production (une source muette ressemblait à une source vide).

Lancer :  python3 -m unittest discover -s tests -v
"""
import datetime as dt
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sources
from sports import basket as B


def ev(id_, date, dom, pts_dom, ext, pts_ext, termine=True, periodes=4):
    """Construit un « événement » au format du scoreboard ESPN."""
    return {
        "id": id_, "date": date,
        "competitions": [{
            "status": {"type": {"completed": termine,
                                "state": "post" if termine else "pre"}},
            "competitors": [
                {"homeAway": "home", "score": pts_dom,
                 "team": {"abbreviation": dom},
                 "linescores": [{"period": p} for p in range(1, periodes + 1)]},
                {"homeAway": "away", "score": pts_ext,
                 "team": {"abbreviation": ext}},
            ],
        }],
    }


PAYLOAD = {"events": [
    ev("1", "2025-01-11T00:00Z", "IND", "108", "GS", "105"),
    ev("2", "2024-11-05T01:30Z", "BOS", "119", "LAL", "122", periodes=5),
    # match à venir : score vide, statut non terminé → doit être écarté
    ev("3", "2026-10-20T23:00Z", "MIA", "", "CHI", "", termine=False),
]}


class Bouchon:
    """Remplace `sources._get` : mémorise les URL, renvoie ce qu'on lui donne."""

    def __init__(self, reponses):
        self.reponses = reponses          # liste de (motif, bytes | None)
        self.urls = []

    def __call__(self, url, entetes=None, timeout=45):
        self.urls.append(url)
        for motif, valeur in self.reponses:
            if motif in url:
                return valeur
        return None

    @property
    def dates(self):
        """Plages de dates demandées, dans l'ordre d'appel."""
        return [u.split("?dates=")[1].split("&")[0] for u in self.urls
                if "?dates=" in u]


class TestRepliEspn(unittest.TestCase):
    """Le scoreboard ESPN est la source de secours du basket."""

    def lance(self, depart, jusqu_a, budget_s=30):
        bouchon = Bouchon([("site.api.espn.com", json.dumps(PAYLOAD).encode())])
        original, pause = sources._get, sources.PAUSE_ESPN
        sources._get, sources.PAUSE_ESPN = bouchon, 0.0
        try:
            r = sources._maj_basket_espn(depart, jusqu_a,
                                         time.time() + budget_s)
        finally:
            sources._get, sources.PAUSE_ESPN = original, pause
        return bouchon, sources._lignes_basket(r)

    def test_reassemble_domicile_et_exterieur(self):
        _, lignes = self.lance(dt.date(2024, 10, 1), dt.date(2025, 1, 20))
        ind = [l for l in lignes if l["domicile"] == "IND"][0]
        self.assertEqual((ind["exterieur"], ind["pts_dom"], ind["pts_ext"]),
                         ("GS", 108, 105))

    def test_home_away_pas_l_ordre_du_json(self):
        """ESPN ne range pas toujours le domicile en premier : on se fie au
        champ `homeAway`, jamais à la position dans la liste."""
        _, lignes = self.lance(dt.date(2024, 10, 1), dt.date(2025, 1, 20))
        bos = [l for l in lignes if "BOS" in (l["domicile"], l["exterieur"])][0]
        self.assertEqual(bos["domicile"], "BOS")
        self.assertEqual(bos["exterieur"], "LAL")
        self.assertEqual((bos["pts_dom"], bos["pts_ext"]), (119, 122))

    def test_match_a_venir_ecarte(self):
        """Un match sans score final n'a rien à faire dans la base d'entraînement
        (ce serait une fuite : le modèle verrait le futur)."""
        _, lignes = self.lance(dt.date(2024, 10, 1), dt.date(2025, 1, 20))
        self.assertEqual(len(lignes), 2)
        self.assertNotIn("MIA", [l["domicile"] for l in lignes])

    def test_saison_calculee_depuis_la_date(self):
        """Une saison NBA commence en octobre : un match de janvier 2025
        appartient à la saison 2024-25, pas 2025-26."""
        _, lignes = self.lance(dt.date(2024, 10, 1), dt.date(2025, 1, 20))
        self.assertEqual({l["saison"] for l in lignes}, {"2024-25"})

    def test_fenetres_sans_chevauchement(self):
        """112 jours en fenêtres de 5 jours = 23 requêtes, pas une de plus :
        chaque requête coûte du temps dans un job de 6 minutes."""
        bouchon, _ = self.lance(dt.date(2024, 10, 1), dt.date(2025, 1, 20))
        self.assertEqual(len(bouchon.dates), 23)
        self.assertEqual(len(set(bouchon.dates)), 23)

    def test_du_plus_recent_vers_le_plus_ancien(self):
        """Si le budget s'épuise, il faut avoir gardé les saisons utiles."""
        bouchon, _ = self.lance(dt.date(2024, 10, 1), dt.date(2025, 1, 20))
        self.assertEqual(bouchon.dates[0], "20250116-20250120")
        self.assertEqual(bouchon.dates[-1], "20241001-20241002")

    def test_intersaison_sautee(self):
        """Juillet, août, septembre : aucun match NBA. Inutile de le demander."""
        bouchon, _ = self.lance(dt.date(2025, 6, 20), dt.date(2025, 10, 10))
        mois = {d[4:6] for d in bouchon.dates}
        self.assertTrue(mois <= {"06", "10"}, mois)

    def test_reponse_invalide_ne_casse_rien(self):
        bouchon = Bouchon([("site.api.espn.com", b"<html>pas du json</html>")])
        original = sources._get
        sources._get = bouchon
        try:
            r = sources._maj_basket_espn(dt.date(2025, 1, 1),
                                         dt.date(2025, 1, 10),
                                         time.time() + 5)
        finally:
            sources._get = original
        self.assertEqual(r, {})

    def test_abandon_rapide_sur_403(self):
        """Depuis les serveurs de GitHub, stats.nba.com ET ESPN répondent 403
        (protection anti-robot). Insister 330 fois ne change rien et coûte trois
        minutes à chaque exécution."""
        class Refus:
            def __init__(self):
                self.urls = []

            def __call__(self, url, entetes=None, timeout=45):
                self.urls.append(url)
                sources.DERNIER_CODE = 403
                return None

        bouchon = Refus()
        avant = (sources._get, sources.PAUSE_ESPN, sources.DERNIER_CODE)
        sources._get, sources.PAUSE_ESPN = bouchon, 0.0
        try:
            r = sources._maj_basket_espn(dt.date(2024, 10, 1),
                                         dt.date(2025, 1, 20), time.time() + 30)
        finally:
            (sources._get, sources.PAUSE_ESPN,
             sources.DERNIER_CODE) = avant
        self.assertEqual(r, {})
        self.assertEqual(len(bouchon.urls), 3, "il faut abandonner après 3 refus")

    def test_les_echecs_non_403_n_arretent_pas(self):
        """Un hôte lent ou en panne n'est pas un hôte qui nous bloque : là il
        faut continuer, sinon une panne passagère vide la base de données."""
        class Panne:
            def __init__(self):
                self.urls = []

            def __call__(self, url, entetes=None, timeout=45):
                self.urls.append(url)
                sources.DERNIER_CODE = None      # timeout, pas refus
                return None

        bouchon = Panne()
        avant = (sources._get, sources.PAUSE_ESPN, sources.DERNIER_CODE)
        sources._get, sources.PAUSE_ESPN = bouchon, 0.0
        try:
            sources._maj_basket_espn(dt.date(2024, 10, 1),
                                     dt.date(2025, 1, 20), time.time() + 30)
        finally:
            (sources._get, sources.PAUSE_ESPN,
             sources.DERNIER_CODE) = avant
        self.assertEqual(len(bouchon.urls), 23, "toutes les fenêtres doivent être tentées")

    def test_lignes_incompletes_ecartees(self):
        bruts = {
            "ok": {"date": "2025-01-01", "domicile": "BOS", "exterieur": "LAL",
                   "pts_dom": 110, "pts_ext": 100},
            "sans_score": {"date": "2025-01-02", "domicile": "MIA",
                           "exterieur": "CHI", "pts_dom": 100},
            "contre_soi": {"date": "2025-01-03", "domicile": "DEN",
                           "exterieur": "DEN", "pts_dom": 1, "pts_ext": 2},
        }
        self.assertEqual(len(sources._lignes_basket(bruts)), 1)


class TestMajBasketRepli(unittest.TestCase):
    """`maj_basket` doit basculer sur ESPN quand stats.nba.com ne répond pas."""

    def setUp(self):
        # Les tests bouchonnent `_get` et raccourcissent les budgets : on remet
        # tout en place après, sinon un test en contamine un autre.
        self.avant = (sources._get, sources.PAUSE_ESPN, sources.BUDGET_BASKET,
                      list(sources.DERNIERES_ERREURS))
        sources.PAUSE_ESPN = 0.0

    def tearDown(self):
        (sources._get, sources.PAUSE_ESPN, sources.BUDGET_BASKET, _) = self.avant
        sources.DERNIERES_ERREURS[:] = self.avant[3]

    def test_bascule_sur_espn_et_ecrit_le_csv(self):
        matchs = [ev(str(i), f"2025-01-{10 + i:02d}T00:00Z",
                     dom, "110", ext, "100")
                  for i, (dom, ext) in enumerate(
                      [("BOS", "LAL"), ("MIA", "CHI"), ("DEN", "PHX"),
                       ("GS", "DAL"), ("MIL", "NY"), ("PHI", "CLE"),
                       ("MEM", "UTA"), ("SAC", "POR")])]
        payload = json.dumps({"events": matchs}).encode()
        # stats.nba.com muet (c'est ce qui arrive dans le job GitHub), ESPN ok
        sources._get = Bouchon([("stats.nba.com", None),
                                ("site.api.espn.com", payload)])
        sources.BUDGET_BASKET = 2          # le test ne doit pas durer 4 minutes
        with tempfile.TemporaryDirectory() as d:
            r = sources.maj_basket(Path(d))
            fichier = Path(d) / "nba_matchs.csv"
            self.assertNotIn("erreur", r)
            self.assertEqual(r["source"], "espn")
            self.assertGreaterEqual(r["matchs"], 8)
            self.assertTrue(fichier.exists())
            # et le fichier est lisible par le moteur qui le consomme
            lus = B.charger_matchs(fichier)
            self.assertEqual(len(lus), 8)
            self.assertEqual(lus[0]["domicile"], "BOS")

    def test_stats_nba_com_garde_la_priorite(self):
        """Si stats.nba.com répond, on ne dépense pas 400 requêtes ESPN."""
        paires = [("BOS", "LAL"), ("MIA", "CHI"), ("DEN", "PHX"), ("GS", "DAL"),
                  ("MIL", "NY"), ("PHI", "CLE"), ("MEM", "UTA"), ("SAC", "POR")]
        rowset = []
        for i, (dom, ext) in enumerate(paires):
            jour = f"2025-01-{10 + i:02d}T00:00:00"
            rowset.append([str(i), f"{dom} vs. {ext}", 110, jour])
            rowset.append([str(i), f"{ext} @ {dom}", 100, jour])
        stats = json.dumps({"resultSets": [
            {"headers": ["GAME_ID", "MATCHUP", "PTS", "GAME_DATE"],
             "rowSet": rowset}]}).encode()
        bouchon = Bouchon([("stats.nba.com", stats)])
        sources._get = bouchon
        with tempfile.TemporaryDirectory() as d:
            r = sources.maj_basket(Path(d), saisons=1)
            self.assertEqual(r["source"], "stats.nba.com")
            self.assertNotIn("erreur", r)
            self.assertEqual(bouchon.dates, [])   # aucune requête ESPN
            self.assertGreaterEqual(r["matchs"], 8)

    def test_echec_des_deux_sources_diagnostique(self):
        """Une source muette ne doit plus ressembler à une source vide :
        le rapport doit porter la raison."""
        sources._get = Bouchon([])                # tout renvoie None
        sources.BUDGET_BASKET = 1
        with tempfile.TemporaryDirectory() as d:
            avant = (Path(d) / "nba_matchs.csv")
            avant.write_text("date,saison,domicile,exterieur,pts_dom,pts_ext\n"
                             "2024-01-01,2024,BOS,LAL,110,100\n")
            r = sources.maj_basket(Path(d))
            self.assertEqual(r["matchs"], 0)
            self.assertEqual(r["erreur"], "aucun_match")
            # le fichier existant est conservé, pas écrasé par du vide
            self.assertIn("2024-01-01", avant.read_text())

    def test_le_repli_a_un_budget_meme_si_stats_nba_a_tout_mange(self):
        """Régression : le repli partageait le budget de stats.nba.com. Une
        source qui traîne jusqu'au bout laissait donc zéro seconde à ESPN, et le
        repli ne partait jamais — exactement quand on en a besoin."""
        payload = json.dumps({"events": [
            ev("1", "2025-01-11T00:00Z", "IND", "108", "GS", "105")]}).encode()
        bouchon = Bouchon([("stats.nba.com", None),
                           ("site.api.espn.com", payload)])
        sources._get = bouchon
        sources.BUDGET_BASKET = 0            # stats.nba.com a tout consommé
        with tempfile.TemporaryDirectory() as d:
            r = sources.maj_basket(Path(d))
            self.assertTrue(bouchon.dates, "ESPN n'a même pas été interrogé")
            self.assertEqual(r["source"], "espn")

    def test_fichier_non_ecrit_est_signale(self):
        """Un CSV trop court pour être honnête n'est pas écrit : le rapport doit
        le dire au lieu d'annoncer des matchs qui ne sont nulle part."""
        sources._get = Bouchon([("stats.nba.com", json.dumps({"resultSets": [
            {"headers": ["GAME_ID", "MATCHUP", "PTS", "GAME_DATE"],
             "rowSet": [["1", "BOS vs. LAL", 110, "2025-01-10T00:00:00"],
                        ["1", "BOS @ LAL", 100, "2025-01-10T00:00:00"]]},
        ]}).encode())])
        with tempfile.TemporaryDirectory() as d:
            r = sources.maj_basket(Path(d), saisons=1)
            self.assertEqual(r["erreur"], "fichier_non_ecrit")
            self.assertEqual(r["matchs"], 0)
            self.assertFalse((Path(d) / "nba_matchs.csv").exists())


class TestGetErreurs(unittest.TestCase):
    """`_get` doit expliquer pourquoi une source n'a rien donné."""

    def test_erreur_enregistree(self):
        sources.DERNIERES_ERREURS.clear()
        self.assertIsNone(sources._get("https://127.0.0.1:9/inexistant",
                                       timeout=2))
        self.assertTrue(sources.DERNIERES_ERREURS)

    def test_liste_bornee(self):
        """Des centaines d'appels ne doivent pas gonfler le rapport sans limite,
        et la PREMIÈRE erreur doit survivre : c'est la plus parlante."""
        sources.DERNIERES_ERREURS.clear()
        for _ in range(39):
            sources.DERNIERES_ERREURS.append("ancienne erreur")
        for _ in range(6):
            sources._get("https://127.0.0.1:9/inexistant", timeout=2)
        self.assertLessEqual(len(sources.DERNIERES_ERREURS), 40)
        self.assertIn("ancienne erreur", sources.DERNIERES_ERREURS[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
