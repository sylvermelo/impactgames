"""
Tests des moteurs hockey et basket.
============================================================================
Le test le plus important n'est pas « ça tourne » mais **« l'estimateur
retrouve-t-il la vérité ? »**. On génère des milliers de matchs à partir de
paramètres d'attaque/défense CONNUS, on les donne au moteur, et on vérifie
qu'il remonte ces paramètres. S'il n'y arrive pas sur des données propres, il
n'y arrivera pas sur des données réelles.

Lancer :  python3 -m unittest discover -s tests -v
"""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sports import basket as B
from sports import hockey as H


# ----------------------------------------------------------- données de test
def generer_hockey(equipes, forces, n_par_equipe, gamma=0.25, graine=1,
                   debut="2020-01-01"):
    """Génère des matchs dont les buts viennent de Poisson avec les forces
    données — donc une vérité connue à comparer."""
    from scipy.stats import poisson
    rng = random.Random(graine)
    prng = np.random.default_rng(graine)
    matchs = []
    idx = {e: i for i, e in enumerate(equipes)}
    jour = 0
    for _ in range(n_par_equipe * len(equipes) // 2):
        h, a = rng.sample(equipes, 2)
        lam = 3.0 * math.exp(forces[idx[h]] - forces[idx[a]] + gamma)
        mu = 3.0 * math.exp(forces[idx[a]] - forces[idx[h]])
        hg, ag = int(prng.poisson(lam)), int(prng.poisson(mu))
        apres = hg == ag
        if apres:                       # prolongation : un but de plus au gagnant
            if prng.random() < 0.545:
                hg += 1
            else:
                ag += 1
        d = __import__("datetime").date.fromisoformat(debut)
        d += __import__("datetime").timedelta(days=jour % 900)
        matchs.append({"date": d.isoformat(), "saison": "20202021",
                       "domicile": h, "exterieur": a,
                       "buts_dom": hg, "buts_ext": ag,
                       "apres_reglement": apres})
        jour += 1
    return matchs


def generer_basket(equipes, net, rythme, n, hfa=2.6, graine=2):
    rng = np.random.default_rng(graine)
    r = random.Random(graine)
    idx = {e: i for i, e in enumerate(equipes)}
    matchs = []
    for k in range(n):
        h, a = r.sample(equipes, 2)
        mu_t = 224.0 + rythme[idx[h]] + rythme[idx[a]]
        mu_d = net[idx[h]] - net[idx[a]] + hfa
        t = rng.normal(mu_t, 19.0)
        d = rng.normal(mu_d, 12.5)
        pd_ = int(round((t + d) / 2))
        pa = int(round((t - d) / 2))
        if pd_ == pa:                       # égalité → prolongation
            pd_ += 1 if rng.random() < 0.535 else 0
            pa += 0 if pd_ > pa else 1
        jour = (k % 1000)
        d0 = __import__("datetime").date(2021, 1, 1) + __import__("datetime").timedelta(days=jour)
        matchs.append({"date": d0.isoformat(), "saison": "2021",
                       "domicile": h, "exterieur": a,
                       "pts_dom": max(pd_, 80), "pts_ext": max(pa, 80)})
    return matchs


# =================================================================== HOCKEY
class TestHockeyChargement(unittest.TestCase):

    def test_but_de_prolongation_retire(self):
        m = {"buts_dom": 4, "buts_ext": 3, "apres_reglement": True}
        self.assertEqual(H.buts_reglementaires(m), (3, 3),
                         "un 4-3 en prolongation = 3-3 à 60 minutes")

    def test_fin_reglementaire_intacte(self):
        m = {"buts_dom": 4, "buts_ext": 1, "apres_reglement": False}
        self.assertEqual(H.buts_reglementaires(m), (4, 1))

    def test_fusillade_1_0(self):
        """Une fusillade 1-0 n'a produit AUCUN but en jeu : 0-0 à 60 minutes."""
        m = {"buts_dom": 1, "buts_ext": 0, "apres_reglement": True}
        self.assertEqual(H.buts_reglementaires(m), (0, 0))


class TestHockeyEstimation(unittest.TestCase):
    """L'estimateur retrouve-t-il les forces qui ont servi à générer ?"""

    @classmethod
    def setUpClass(cls):
        cls.equipes = [f"E{i}" for i in range(12)]
        cls.forces = np.array([0.45, 0.35, 0.25, 0.15, 0.05, -0.05,
                               -0.15, -0.25, -0.35, -0.45, 0.0, 0.10])
        cls.matchs = generer_hockey(cls.equipes, cls.forces, 400, graine=11)
        cls.modele = H.ajuster(cls.matchs)

    def test_convergence(self):
        self.assertTrue(self.modele.get("converge"), "l'optimiseur a échoué")

    def test_retrouve_les_forces(self):
        """Corrélation entre forces réelles et forces estimées : doit être > 0,9."""
        idx = self.modele["idx"]
        # la force nette est attaque − faiblesse_défensive (voir classement())
        estime = np.array([self.modele["attaque"][idx[e]] - self.modele["defense"][idx[e]]
                           for e in self.equipes])
        r = np.corrcoef(self.forces, estime)[0, 1]
        self.assertGreater(r, 0.90, f"corrélation {r:.3f} : le modèle ne retrouve pas")

    def test_ordre_des_equipes(self):
        """La meilleure équipe générée doit finir en tête du classement."""
        cl = H.classement(self.modele)
        meilleure_generee = self.equipes[int(np.argmax(self.forces))]
        self.assertEqual(cl[0]["equipe"], meilleure_generee)

    def test_retrouve_avantage_domicile(self):
        """Le générateur applique un avantage de 0,25 en log. Avec `b` seul
        ancré à zéro, γ doit ressortir à 0,25 — pas à log(3)+0,25 ni à 1,12."""
        self.assertAlmostEqual(self.modele["gamma"], 0.25, delta=0.08,
                               msg=f"γ estimé {self.modele['gamma']:.3f}")

    def test_retrouve_le_niveau_de_buts(self):
        """C'est moyenne(a) qui porte le niveau de la ligue, pas γ. Le
        générateur part d'une base de 3,0 buts : exp(moyenne(a)) doit valoir 3."""
        niveau = math.exp(float(np.mean(self.modele["attaque"])))
        self.assertAlmostEqual(niveau, 3.0, delta=0.35, msg=f"niveau {niveau:.2f}")

    def test_seule_b_est_ancree(self):
        self.assertAlmostEqual(float(np.mean(self.modele["defense"])), 0.0, places=3)

    def test_taux_de_prolongation_bien_calibre(self):
        """Le vrai test : la moyenne des prolongations prédites doit coller au
        taux de matchs nuls réellement observé dans les données qui ont servi
        à l'entraînement. Pas de seuil arbitraire — une comparaison."""
        nuls = sum(1 for m in self.matchs
                   if H.buts_reglementaires(m)[0] == H.buts_reglementaires(m)[1])
        reel = nuls / len(self.matchs)
        pred = np.mean([H.marches(H.matrice_scores(self.modele, h, a))["p_prolongation"]
                        for h in self.equipes for a in self.equipes if h != a])
        self.assertAlmostEqual(float(pred), reel, delta=0.04,
                               msg=f"prédit {pred:.3f} vs réel {reel:.3f}")

    def test_but_par_match_retrouve(self):
        """Comparer le total prédit au total RÉELLEMENT observé.

        (Première version : on vérifiait « entre 5 et 7 buts » en moyennant
        sur les 6 meilleurs à domicile contre les 6 plus faibles à
        l'extérieur — un biais de sélection qui gonflait le chiffre de 0,7
        but. Le bon test n'a pas de seuil arbitraire, il compare aux données.)
        """
        reel = np.mean([sum(H.buts_reglementaires(m)) for m in self.matchs])
        pred = np.mean([H.marches(H.matrice_scores(self.modele, h, a))["buts_attendus"]
                        for h in self.equipes for a in self.equipes if h != a])
        self.assertAlmostEqual(float(pred), float(reel), delta=0.4,
                               msg=f"prédit {pred:.2f} vs réel {reel:.2f}")

    def test_buts_reels_dans_la_norme_nhl(self):
        """Sanity check séparé : les DONNÉES de test doivent ressembler à du
        hockey. Si le générateur dérive, c'est ce test qui le dit, pas l'autre."""
        reel = np.mean([sum(H.buts_reglementaires(m)) for m in self.matchs])
        self.assertGreater(reel, 5.0)
        self.assertLess(reel, 7.5, f"{reel:.2f} buts/match")


class TestHockeyMarches(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        equipes = [f"E{i}" for i in range(8)]
        forces = np.linspace(0.4, -0.4, 8)
        m = H.ajuster(generer_hockey(equipes, forces, 300, graine=3))
        cls.M = H.matrice_scores(m, "E0", "E7")
        cls.mk = H.marches(cls.M)

    def test_matrice_somme_a_un(self):
        self.assertAlmostEqual(self.M.sum(), 1.0, places=9)

    def test_trois_voies_somment_a_un(self):
        self.assertAlmostEqual(self.mk["1"] + self.mk["X"] + self.mk["2"], 1.0, places=9)

    def test_moneyline_somme_a_un(self):
        self.assertAlmostEqual(self.mk["ml_dom"] + self.mk["ml_ext"], 1.0, places=9)

    def test_moneyline_superieur_au_temps_reglementaire(self):
        """Prolongation comprise, le domicile gagne plus souvent qu'à 60 min."""
        self.assertGreater(self.mk["ml_dom"], self.mk["1"])

    def test_prolongation_realiste(self):
        """Sur un match ÉQUILIBRÉ, 20 à 25 % des rencontres NHL vont au-delà
        de 60 minutes. Sur un E0-E7 (le plus déséquilibré possible) le nul est
        rarissime : c'est attendu, pas un bug — d'où le choix d'E3 contre E4.
        """
        equipes = [f"E{i}" for i in range(8)]
        forces = np.linspace(0.4, -0.4, 8)
        m = H.ajuster(generer_hockey(equipes, forces, 300, graine=3))
        eq = H.marches(H.matrice_scores(m, "E3", "E4"))
        des = self.mk["p_prolongation"]
        self.assertLess(des, eq["p_prolongation"],
                        "un choc déséquilibré donne moins de prolongations")
        # la valeur absolue est calibrée par test_taux_de_prolongation_bien_calibre
        self.assertGreater(eq["p_prolongation"], 0.05)

    def test_over_under_complementaires(self):
        for seuil in (3.5, 4.5, 5.5, 6.5, 7.5):
            self.assertAlmostEqual(self.mk[f"O{seuil}"] + self.mk[f"U{seuil}"], 1.0,
                                   places=9, msg=seuil)

    def test_handicap_complementaire(self):
        for h in (0.5, 1.5, 2.5):
            self.assertAlmostEqual(self.mk[f"handicap_dom_{h}"] +
                                   self.mk[f"handicap_ext_plus_{h}"], 1.0, places=9,
                                   msg=h)

    def test_double_chance_coherente(self):
        self.assertAlmostEqual(self.mk["double_chance_1X"], self.mk["1"] + self.mk["X"],
                               places=9)
        self.assertAlmostEqual(self.mk["double_chance_1X"] + self.mk["2"], 1.0, places=9)

    def test_equipe_inconnue(self):
        m = {"idx": {"A": 0}, "equipes": ["A"], "attaque": np.array([0.0]),
             "defense": np.array([0.0]), "gamma": 0.0, "rho": 0.0}
        self.assertIn("erreur", H.pronostic(m, "A", "ZZZ"))


# =================================================================== BASKET
class TestBasketEstimation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.equipes = [f"T{i}" for i in range(14)]
        cls.net = np.array([8.0, 6.0, 4.0, 2.0, 0.0, -2.0, -4.0,
                            -6.0, -8.0, 1.0, -1.0, 3.0, -3.0, 5.0])
        cls.rythme = np.array([4.0, -4.0, 2.0, -2.0, 6.0, -6.0, 0.0,
                               3.0, -3.0, 1.0, -1.0, 5.0, -5.0, 2.0])
        cls.matchs = generer_basket(cls.equipes, cls.net, cls.rythme, 6000, graine=5)
        cls.modele = B.ajuster(cls.matchs)

    def test_retrouve_la_force_nette(self):
        idx = self.modele["idx"]
        est = np.array([self.modele["net"][idx[e]] for e in self.equipes])
        r = np.corrcoef(self.net, est)[0, 1]
        self.assertGreater(r, 0.90, f"corrélation force nette {r:.3f}")

    def test_retrouve_le_rythme(self):
        idx = self.modele["idx"]
        est = np.array([self.modele["rythme"][idx[e]] for e in self.equipes])
        r = np.corrcoef(self.rythme, est)[0, 1]
        self.assertGreater(r, 0.85, f"corrélation rythme {r:.3f}")

    def test_retrouve_avantage_domicile(self):
        self.assertAlmostEqual(self.modele["hfa"], 2.6, delta=0.8,
                               msg=f"hfa estimé {self.modele['hfa']:.2f}")

    def test_retrouve_les_ecarts_types(self):
        """Le générateur tire T avec un écart-type de 19 et D avec 12,5 : ce
        sont ces valeurs que l'estimateur doit retrouver (pas 19·√2 — T et D
        sont déjà tirés directement, il n'y a pas de composition de variances).
        """
        self.assertAlmostEqual(self.modele["sigma_total"], 19.0, delta=2.0)
        self.assertAlmostEqual(self.modele["sigma_ecart"], 12.5, delta=2.0)

    def test_notes_somment_a_zero(self):
        """Contrainte d'identifiabilité : la moyenne des notes doit être nulle."""
        self.assertAlmostEqual(float(np.sum(self.modele["net"])), 0.0, places=4)
        self.assertAlmostEqual(float(np.sum(self.modele["rythme"])), 0.0, places=4)


class TestBasketMarches(unittest.TestCase):

    P = {"mu_total": 224.0, "mu_ecart": 5.0, "sigma_total": 24.0,
         "sigma_ecart": 15.0, "correlation": 0.1}

    def test_deux_voies_somment_a_un(self):
        m = B.marches(self.P)
        self.assertAlmostEqual(m["dom_gagne"] + m["ext_gagne"], 1.0, places=9)

    def test_prolongation_representee(self):
        # écart-type NBA réel ≈ 12,5 points ; avec 15 on descend sous 3 %
        m = B.marches(dict(self.P, mu_ecart=0.0, sigma_ecart=12.5))
        self.assertGreater(m["p_prolongation"], 0.025,
                           "à égalité de niveau, ~6 % de prolongations en NBA")
        self.assertLess(m["p_prolongation"], 0.06)

    def test_over_under_complementaires(self):
        m = B.marches(self.P)
        for ligne in (205.5, 215.5, 220.5, 225.5, 230.5, 240.5):
            self.assertAlmostEqual(m[f"O{ligne}"] + m[f"U{ligne}"], 1.0, places=9,
                                   msg=ligne)

    def test_handicap_complementaire(self):
        m = B.marches(self.P)
        for h in (2.5, 4.5, 6.5, 8.5, 10.5, 12.5):
            self.assertAlmostEqual(m[f"dom_moins_{h}"] + m[f"ext_plus_{h}"], 1.0,
                                   places=9, msg=h)

    def test_pas_de_correction_de_continuite_sur_les_handicaps(self):
        """Régression : à écart attendu nul, dom −6,5 doit valoir exactement 50 %.

        Avec le 0,5 parasite qu'on avait ajouté, on tombait sous 50 % pour un
        favori — un demi-point de décalage sur toutes les lignes.
        """
        # à écart attendu EXACTEMENT égal à la ligne, le 50/50 est la bonne
        # réponse ; avec le 0,5 parasite on obtenait 0,487
        m = B.marches(dict(self.P, mu_ecart=6.5))
        self.assertAlmostEqual(m["dom_moins_6.5"], 0.5, places=9)

    def test_favori_monotone(self):
        a = B.marches(dict(self.P, mu_ecart=2.0))["dom_gagne"]
        b = B.marches(dict(self.P, mu_ecart=10.0))["dom_gagne"]
        self.assertGreater(b, a)

    def test_ecart_attendu_coherent(self):
        m = B.marches(self.P)
        self.assertAlmostEqual(m["ecart_attendu"], 5.0, places=9)
        self.assertEqual(m["ecart_le_plus_probable"], 5)

    def test_equipe_inconnue(self):
        mod = {"idx": {"A": 0}, "net": np.array([0.0]), "rythme": np.array([0.0]),
               "hfa": 2.6, "base_total": 224.0, "sigma_total": 24.0,
               "sigma_ecart": 15.0, "correlation": 0.1}
        self.assertIn("erreur", B.pronostic(mod, "A", "ZZZ"))


class TestBasketChargement(unittest.TestCase):

    def test_doublons_ignores(self):
        import tempfile
        from pathlib import Path
        contenu = ("date,saison,domicile,exterieur,pts_dom,pts_ext\n"
                   "2024-01-01,2024,BOS,LAL,110,100\n"
                   "2024-01-01,2024,BOS,LAL,110,100\n")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.csv"
            f.write_text(contenu, encoding="utf-8")
            self.assertEqual(len(B.charger_matchs(f)), 1)

    def test_ligne_cassee_igneree(self):
        import tempfile
        from pathlib import Path
        contenu = ("date,saison,domicile,exterieur,pts_dom,pts_ext\n"
                   "2024-01-01,2024,BOS,LAL,abc,100\n"
                   "2024-01-02,2024,BOS,LAL,110,100\n")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.csv"
            f.write_text(contenu, encoding="utf-8")
            self.assertEqual(len(B.charger_matchs(f)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
