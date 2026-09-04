"""
Tests du moteur tennis.
============================================================================
Le point central : la chaîne de Markov (programme dynamique) est vérifiée
contre une **simulation de Monte-Carlo indépendante**, écrite autrement et
sans partager de code avec elle. Si la DP et la simulation tombent d'accord à
0,3 point près sur 400 000 matchs simulés, le calcul est bon — sinon c'est la
convolution qui perd des valeurs, exactement le bug que ce test a attrapé.

Lancer :  python3 -m unittest discover -s tests -v
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from sports import tennis as T
from sports.commun import calibration, devig, log_loss, rps


# ------------------------------------------------- simulation de référence
def simuler_match(p_serv, p_ret, best_of, p_tb, rng, n=200_000):
    """Simule `n` matchs jeu par jeu. Aucune code commun avec la DP."""
    cible = (best_of + 1) // 2
    tot_vict = [0, 0]
    tot_jeux = 0
    tot_ecart = 0
    carres_jeux = 0
    carres_ecart = 0
    hist_jeux = {}
    hist_scores = {}
    for _ in range(n):
        sa = sb = 0
        jeux_a = jeux_b = 0
        while sa < cible and sb < cible:
            ja = jb = 0
            jeu = 0
            while True:
                p_a = p_serv if jeu % 2 == 0 else p_ret
                if rng.random() < p_a:
                    ja += 1
                else:
                    jb += 1
                jeu += 1
                if (ja, jb) == (6, 6):
                    if rng.random() < p_tb:
                        ja += 1
                    else:
                        jb += 1
                    break
                if max(ja, jb) >= 6 and abs(ja - jb) >= 2:
                    break
            jeux_a += ja
            jeux_b += jb
            if ja > jb:
                sa += 1
            else:
                sb += 1
        v = 0 if sa > sb else 1
        tot_vict[v] += 1
        tot_jeux += jeux_a + jeux_b
        tot_ecart += jeux_a - jeux_b
        carres_jeux += (jeux_a + jeux_b) ** 2
        carres_ecart += (jeux_a - jeux_b) ** 2
        hist_jeux[jeux_a + jeux_b] = hist_jeux.get(jeux_a + jeux_b, 0) + 1
        hist_scores[f"{sa}-{sb}"] = hist_scores.get(f"{sa}-{sb}", 0) + 1
    return {"p_a": tot_vict[0] / n,
            "jeux_moy": tot_jeux / n,
            "ecart_moy": tot_ecart / n,
            "hist_jeux": hist_jeux,
            "scores": hist_scores, "n": n,
            # erreur-type de la moyenne : c'est elle qui fixe la tolérance,
            # pas un chiffre arbitraire
            "se_jeux": (max(carres_jeux / n - (tot_jeux / n) ** 2, 0) ** 0.5) / n ** 0.5,
            "se_ecart": (max(carres_ecart / n - (tot_ecart / n) ** 2, 0) ** 0.5) / n ** 0.5}


def dp(p_serv, p_ret, best_of, p_tb):
    """Même entrée, mais via la chaîne de Markov du moteur."""
    entrees = T.distribution_set(p_serv, p_ret, p_tb)
    cible = (best_of + 1) // 2
    total = T.dp_match(entrees, cible, T.TAILLE_DP, "total")
    ecart = T.dp_match(entrees, cible, T.TAILLE_DP, "ecart")
    total = total / total.sum()
    ecart = ecart / ecart.sum()
    valeurs = np.arange(T.TAILLE_DP) - T.TAILLE_DP // 2
    sc = T.scores_en_sets(entrees, cible)
    p_a = sum(p for s, p in sc.items() if int(s.split("-")[0]) == cible)
    return {"p_a": p_a,
            "jeux_moy": float((total * valeurs).sum()),
            "ecart_moy": float((ecart * valeurs).sum()),
            "dist_total": (valeurs, total),
            "scores": sc}


class TestDistributionSet(unittest.TestCase):

    def test_somme_a_un(self):
        for ps, pr in ((0.64, 0.36), (0.70, 0.30), (0.55, 0.45), (0.80, 0.20)):
            ent = T.distribution_set(ps, pr, 0.5 + 0.6 * (ps + pr - 1.0))
            self.assertAlmostEqual(sum(p for *_x, p in ent), 1.0, places=9,
                                   msg=f"ps={ps} pr={pr}")

    def test_scores_possibles(self):
        ent = T.distribution_set(0.64, 0.36, 0.5)
        attendus = {(6, 0), (6, 1), (6, 2), (6, 3), (6, 4), (7, 5), (7, 6)}
        obtenus = {(jv, jp) for _v, jv, jp, _p in ent}
        self.assertEqual(obtenus, attendus)

    def test_egalite_symetrie(self):
        """À 50/50 sur chaque point, A et B gagnent le set autant."""
        ent = T.distribution_set(0.5, 0.5, 0.5)
        pa = sum(p for v, _a, _b, p in ent if v == 0)
        self.assertAlmostEqual(pa, 0.5, places=9)


class TestChaineMarkov(unittest.TestCase):
    """DP vs Monte-Carlo : le test qui attrape les fuites de convolution."""

    # paires symétriques ET asymétriques : les asymétriques sont celles qui
    # font bouger l'écart de jeux, donc celles qui testent vraiment la DP.
    CAS = [(0.640, 0.360, 3), (0.700, 0.300, 3), (0.615, 0.385, 5),
           (0.668, 0.332, 5), (0.580, 0.420, 3),
           (0.700, 0.420, 3), (0.690, 0.400, 5), (0.600, 0.330, 3),
           (0.750, 0.450, 5), (0.620, 0.300, 3)]

    def test_dp_contre_simulation(self):
        rng = random.Random(20260904)
        for p_serv, p_ret, best_of in self.CAS:
            p_tb = 0.5 + 0.6 * (p_serv + p_ret - 1.0)
            sim = simuler_match(p_serv, p_ret, best_of, p_tb, rng, n=200_000)
            det = dp(p_serv, p_ret, best_of, p_tb)
            avec = dict(ps=p_serv, pr=p_ret, bo=best_of)
            self.assertAlmostEqual(det["p_a"], sim["p_a"], delta=0.004, msg=avec)
            # tolérance = 4 erreurs-types : au-delà, ce n'est plus du bruit
            self.assertAlmostEqual(det["jeux_moy"], sim["jeux_moy"],
                                   delta=max(0.05, 4 * sim["se_jeux"]), msg=avec)
            self.assertAlmostEqual(det["ecart_moy"], sim["ecart_moy"],
                                   delta=max(0.05, 4 * sim["se_ecart"]),
                                   msg=f"{avec} <-- écart (bug de convolution)")

    def test_scores_en_sets_contre_simulation(self):
        rng = random.Random(777)
        sim = simuler_match(0.665, 0.335, 3, 0.5, rng, n=200_000)
        det = dp(0.665, 0.335, 3, 0.5)
        for score, n_sim in sim["scores"].items():
            self.assertAlmostEqual(det["scores"][score], n_sim / sim["n"],
                                   delta=0.004, msg=score)

    def test_distribution_jeux_contre_simulation(self):
        rng = random.Random(4242)
        sim = simuler_match(0.640, 0.360, 3, 0.5, rng, n=200_000)
        det = dp(0.640, 0.360, 3, 0.5)
        valeurs, dist = det["dist_total"]
        idx = {int(v): p for v, p in zip(valeurs, dist) if p > 1e-9}
        for jeux, n_sim in sim["hist_jeux"].items():
            self.assertAlmostEqual(idx.get(jeux, 0.0), n_sim / sim["n"],
                                   delta=0.004, msg=f"{jeux} jeux")

    def test_ecart_positif_pour_le_favori(self):
        # Attention au piège : (0.700, 0.300) est SYMÉTRIQUE — B tient aussi son
        # service à 70 %. Pour un vrai favori il faut un écart des deux côtés.
        det = dp(0.700, 0.420, 3, 0.5)
        self.assertGreater(det["ecart_moy"], 1.0,
                           "un favori net doit avoir un écart de jeux positif")
        det2 = dp(0.580, 0.300, 3, 0.5)
        self.assertLess(det2["ecart_moy"], -1.0, "et négatif quand il est B")
        # Cas piège : (0.700, 0.300) = les deux tiennent leur service à 70 %,
        # donc on s'attendrait à un écart nul. Il ne l'est pas : A sert en
        # PREMIER dans chaque set, ce qui lui donne l'initiative sur les jeux
        # décisifs (6-5). Cet avantage d'environ 0,3 jeu est réel, et la
        # simulation Monte-Carlo indépendante le retrouve (voir CAS).
        sym = dp(0.700, 0.300, 3, 0.5)["ecart_moy"]
        self.assertGreater(sym, 0.0, "avantage du premier serveur")
        self.assertLess(sym, 0.6, "mais il reste marginal")

    def test_handicap_coherent_avec_ecart(self):
        p = T.pronostic(1900, 1400, "Hard", 3, 0.09)
        self.assertGreater(p["ecart_attendu"], 0)
        self.assertGreater(p["A_moins_2.5"], 0.3)
        for h in (2.5, 3.5, 4.5, 5.5, 6.5):
            self.assertAlmostEqual(p[f"A_moins_{h}"] + p[f"B_plus_{h}"], 1.0,
                                   places=9,
                                   msg=f"handicap {h} : les deux côtés d'un pari "
                                       f"à deux issues doivent sommer à 1")
        # plus la ligne est dure, moins le favori la couvre
        self.assertGreater(p["A_moins_2.5"], p["A_moins_4.5"])
        self.assertGreater(p["A_moins_4.5"], p["A_moins_6.5"])


class TestPronostic(unittest.TestCase):

    def test_joueurs_identiques(self):
        p = T.pronostic(1600, 1600, "Clay", 3, 0.09)
        self.assertAlmostEqual(p["p_a"], 0.5, places=6)
        self.assertAlmostEqual(p["p_b"], 0.5, places=6)
        self.assertAlmostEqual(sum(p["scores"].values()), 1.0, places=9)

    # paramètres d'allure réaliste, tels que `ajuster_logistique` les produit
    PARAMS = {"Hard|3": {"echelle": 1.12}, "Clay|3": {"echelle": 1.18},
              "Grass|3": {"echelle": 1.34}, "Hard|5": {"echelle": 0.82},
              "Clay|5": {"echelle": 0.60}, "Grass|5": {"echelle": 0.76}}

    def test_surface_modifie_les_marches_derives(self):
        """La probabilité de match vient de la logistique calibrée : à écart Elo
        égal elle est identique d'une surface à l'autre (l'effet surface est
        déjà DANS l'Elo par surface). Ce qui change, ce sont les marchés
        dérivés : le service pèse plus sur gazon que sur terre."""
        dur = T.pronostic(1700, 1500, "Hard", 3, 0.155, self.PARAMS)
        herbe = T.pronostic(1700, 1500, "Grass", 3, 0.155, self.PARAMS)
        terre = T.pronostic(1700, 1500, "Clay", 3, 0.155, self.PARAMS)
        self.assertGreater(herbe["p_service_a"], dur["p_service_a"])
        self.assertGreater(dur["p_service_a"], terre["p_service_a"])
        self.assertGreater(herbe["jeux_attendus"], terre["jeux_attendus"])

    def test_cinq_sets_amplifie_le_favori(self):
        """L'effet Grand Chelem vient de l'échelle ajustée par format
        (0,82 en dur sur 5 sets contre 1,12 sur 3) : il est MESURÉ sur les
        données, pas supposé. C'est le test de régression de ce mécanisme."""
        bo3 = T.pronostic(1800, 1500, "Hard", 3, 0.155, self.PARAMS)["p_a"]
        bo5 = T.pronostic(1800, 1500, "Hard", 5, 0.155, self.PARAMS)["p_a"]
        self.assertGreater(bo5, bo3, "en 5 sets le favori doit gagner plus souvent")

    def test_total_jeux_realiste(self):
        p = T.pronostic(1650, 1620, "Hard", 3, 0.09)
        self.assertGreater(p["jeux_attendus"], 19)
        self.assertLess(p["jeux_attendus"], 26)

    def test_over_under_somment_a_un(self):
        p = T.pronostic(1700, 1550, "Hard", 5, 0.09)
        for seuil in (21.5, 23.5, 25.5, 35.5, 39.5):
            self.assertAlmostEqual(p[f"O{seuil}"] + p[f"U{seuil}"], 1.0, places=9,
                                   msg=seuil)


class TestElo(unittest.TestCase):

    def setUp(self):
        self.matchs = [
            {"date": "2024-01-01", "match_num": i, "surface": "Hard",
             "niveau": "A", "best_of": 3, "joueur_a": f"P{i % 8}",
             "joueur_b": f"P{(i + 1) % 8}"}
            for i in range(40)
        ]

    def test_somme_nulle(self):
        """L'Elo est un jeu à somme nulle : la moyenne du plateau ne bouge pas."""
        elo = T.entrainer_elo(self.matchs)
        moyenne = sum(elo["elo_global"].values()) / len(elo["elo_global"])
        self.assertAlmostEqual(moyenne, T.ELO_INITIAL, places=6)

    def test_historique_avant_match(self):
        """Le premier match de deux inconnus doit partir du classement initial :
        c'est ce qui garantit l'absence de fuite de données."""
        elo = T.entrainer_elo(self.matchs)
        self.assertEqual(elo["avant"][0], (T.ELO_INITIAL, T.ELO_INITIAL))
        self.assertEqual(len(elo["avant"]), len(self.matchs))

    def test_davis_cup_ignoree(self):
        m = [{"date": "2024-01-01", "match_num": 1, "surface": "Hard",
              "niveau": "D", "best_of": 5, "joueur_a": "A", "joueur_b": "B"}]
        elo = T.entrainer_elo(m)
        self.assertEqual(elo["elo_global"].get("A"), None)


class TestCommun(unittest.TestCase):

    def test_devig_retire_la_marge(self):
        p = devig(2.0, 2.0)
        self.assertAlmostEqual(p.sum(), 1.0, places=9)
        self.assertAlmostEqual(p[0], 0.5, places=9)

    def test_devig_cote_manquante(self):
        self.assertTrue(np.isnan(devig(2.0, None)).all())
        self.assertTrue(np.isnan(devig(1.005, 3.0)).all())

    def test_logloss_parfaite(self):
        self.assertAlmostEqual(
            log_loss(np.array([[0.999999, 0.000001]]), np.array([0])), 0.0, places=4)

    def test_logloss_absurde(self):
        self.assertGreater(log_loss(np.array([[0.01, 0.99]]), np.array([0])), 4.0)

    def test_rps_ordre(self):
        """Rater de 2 crans doit coûter plus cher que rater d'un cran."""
        loin = rps(np.array([[1.0, 0.0, 0.0]]), np.array([2]))
        proche = rps(np.array([[1.0, 0.0, 0.0]]), np.array([1]))
        self.assertGreater(loin, proche)

    def test_calibration_apparie_chaque_colonne_a_son_issue(self):
        """Régression : aplatir probas et issues séparément donne ~50 % partout.

        On construit 200 « favoris sûrs » (p = 0.9) qui gagnent réellement : la
        tranche haute doit afficher un taux réel proche de 100 %, pas de 50 %.
        """
        n = 200
        probas = np.tile(np.array([[0.9, 0.1]]), (n, 1))
        issues = np.zeros(n, dtype=int)                    # la colonne 0 gagne
        c = calibration(probas.ravel(), np.eye(2)[issues].ravel())
        haute = [t for t in c if t["de"] == 0.70][0]
        self.assertAlmostEqual(haute["reel"], 1.0, places=6)
        basse = [t for t in c if t["de"] == 0.0][0]
        self.assertAlmostEqual(basse["reel"], 0.0, places=6)

    def test_calibration_ecarte_les_petits_effectifs(self):
        c = calibration(np.array([0.9, 0.95]), np.array([1, 1]))
        self.assertEqual(c, [], "moins de 30 observations : on n'affiche rien")


if __name__ == "__main__":
    unittest.main(verbosity=2)
