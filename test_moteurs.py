"""Contrôles de non-régression — probabilités, bornes, parité des marchés."""
import math
import moteurs as M


def test_norm_cdf():
    assert abs(M.norm_cdf(0) - 0.5) < 1e-9
    assert M.norm_cdf(3) > 0.99
    assert M.norm_cdf(-3) < 0.01


def test_poisson_somme():
    s = sum(M.poisson_pmf(k, 2.7) for k in range(0, 20))
    assert abs(s - 1) < 1e-6


def test_devig():
    p = M.devig(2.0, 2.0)
    assert p is not None and abs(p[0] - 0.5) < 1e-9
    assert M.devig(1.0, 2.0) is None
    assert M.devig(None, 2.1) is None


def test_american():
    assert abs(M.american_to_prob(-200) - 200 / 300) < 1e-9
    assert abs(M.american_to_decimal(-200) - 1.5) < 1e-9
    assert abs(M.american_to_decimal(150) - 2.5) < 1e-9


def _matchs_basket(n=40):
    out = []
    for i in range(n):
        out.append({"date": f"2024-{(i % 12)+1:02d}-{(i % 27)+1:02d}",
                    "home": "Celtics" if i % 2 == 0 else "Lakers",
                    "away": "Heat" if i % 3 else "Nuggets",
                    "hg": 110 + (i % 15), "ag": 105 + (i % 12)})
    return out


def test_fit_pronostic_basket():
    mo = M.fit_basket(_matchs_basket(80))
    assert mo and "Celtics" in mo["forces"]
    p = M.pronostic_basket(mo, "Celtics", "Heat")
    assert p
    assert abs(p["victoire_1"] + p["victoire_2"] - 1) < 1e-6
    assert 0.05 < p["victoire_1"] < 0.95
    assert p["points_attendus"] > 180


def _matchs_hockey(n=80):
    out = []
    for i in range(n):
        out.append({"date": f"2024-{(i % 12)+1:02d}-{(i % 27)+1:02d}",
                    "home": "Bruins" if i % 2 == 0 else "Maple Leafs",
                    "away": "Canadiens" if i % 3 else "Rangers",
                    "hg": i % 6, "ag": (i * 3) % 5})
    return out


def test_fit_pronostic_hockey():
    mo = M.fit_hockey(_matchs_hockey(120))
    assert mo
    p = M.pronostic_hockey(mo, "Bruins", "Canadiens")
    assert p
    assert abs(p["victoire_1"] + p["victoire_2"] - 1) < 1e-6  # ML, nul partagé
    s = sum(p["over"].values())  # pas une partition
    assert 0.2 < p["over"]["5.5"] < 0.9
    assert abs(p["btts_oui"] + p["btts_non"] - 1) < 1e-6
    assert len(p["scores_top"]) >= 3


def test_tennis_sets():
    p_bo3 = M.p_match_from_set(0.6, 3)
    assert 0.6 < p_bo3 < 0.8
    inv = M.p_set_from_match(p_bo3, 3)
    assert abs(inv - 0.6) < 0.01
    matchs = []
    for i in range(400):
        matchs.append({"date": f"2023-06-{(i % 27)+1:02d}",
                       "winner": "Alpha" if i % 3 else "Beta",
                       "loser": "Gamma" if i % 2 else "Delta",
                       "surface": "Hard" if i % 2 else "Clay",
                       "best_of": 3, "wrank": 10, "lrank": 40})
    mo = M.fit_tennis(matchs)
    assert mo and mo["n"] == 400
    p = M.pronostic_tennis(mo, "Alpha", "Beta", "Hard", 3)
    assert p and abs(p["victoire_1"] + p["victoire_2"] - 1) < 1e-6
    assert abs(sum(p["sets"].values()) - 1) < 1e-3


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("  ok", t.__name__)
    print(f"TOUS LES TESTS PASSENT ({len(tests)})")
