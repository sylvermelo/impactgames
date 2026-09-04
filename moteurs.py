"""
Moteurs de calcul — basketball (loi normale), hockey (Poisson / Dixon-Coles),
tennis (Elo + sets indépendants).

Aucune bibliothèque tierce : Python standard uniquement, reproductible,
identiques en JavaScript dans la version autonome.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

# --------------------------------------------------------------------------- maths
SQRT2 = math.sqrt(2.0)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    if k < 0:
        return 0.0
    logp = -lam + k * math.log(lam) - math.lgamma(k + 1)
    return math.exp(logp)


def clip(x, a, b):
    return a if x < a else b if x > b else x


def american_to_decimal(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0 or abs(a) < 1:
        return None
    return round(1 + 100 / abs(a), 3) if a < 0 else round(1 + a / 100, 3)


def american_to_prob(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0 or abs(a) < 1:
        return None
    return abs(a) / (abs(a) + 100) if a < 0 else 100 / (a + 100)


def devig(*cotes):
    vals = []
    for c in cotes:
        try:
            v = float(c)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(v) or v <= 1.01:
            return None
        vals.append(1.0 / v)
    s = sum(vals)
    if s <= 0:
        return None
    return [x / s for x in vals]


def _as_date(d):
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    s = str(d)
    if not s:
        return None
    s = s.replace(".", "").strip()
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _poids(ref: date, d: date, demi_vie: float) -> float:
    if ref is None or d is None:
        return 1.0
    j = (ref - d).days
    if j < 0:
        j = 0
    return math.exp(-math.log(2.0) * j / max(demi_vie, 1.0))


# ===========================================================================
# BASKETBALL — attaque × défense, totaux ~ Normal
# ===========================================================================
BASKET_DEMI_VIE = 140.0   # un match d'il y a 140 j pèse 50 %
BASKET_ITERS = 28


def fit_basket(matchs: list, shrink: float = 12.0) -> dict | None:
    """Estime att/def par équipe + σ de marge et de total.

    matchs : [{date, home, away, hg, ag}, ...]  (points finaux)
    """
    rows = []
    for m in matchs:
        d = _as_date(m.get("date"))
        try:
            hg, ag = int(m["hg"]), int(m["ag"])
        except (TypeError, ValueError, KeyError):
            continue
        h, a = str(m.get("home") or ""), str(m.get("away") or "")
        if not h or not a or h == a or h == "0" or a == "0":
            continue
        if hg < 50 or ag < 50 or hg > 200 or ag > 200:
            continue
        rows.append({"date": d, "home": h, "away": a, "hg": hg, "ag": ag})
    if len(rows) < 80:
        return None
    teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    ref = max((r["date"] for r in rows if r["date"]), default=date.today())
    w = [_poids(ref, r["date"], BASKET_DEMI_VIE) for r in rows]

    sw = sum(w) or 1.0
    mu_h = sum(wi * r["hg"] for wi, r in zip(w, rows)) / sw
    mu_a = sum(wi * r["ag"] for wi, r in zip(w, rows)) / sw
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}

    for _ in range(BASKET_ITERS):
        num_a = {t: 0.0 for t in teams}
        den_a = {t: 0.0 for t in teams}
        num_d = {t: 0.0 for t in teams}
        den_d = {t: 0.0 for t in teams}
        for r, wi in zip(rows, w):
            h, a = r["home"], r["away"]
            num_a[h] += wi * r["hg"]
            den_a[h] += wi * dfn[a] * mu_h
            num_a[a] += wi * r["ag"]
            den_a[a] += wi * dfn[h] * mu_a
            num_d[a] += wi * r["hg"]
            den_d[a] += wi * att[h] * mu_h
            num_d[h] += wi * r["ag"]
            den_d[h] += wi * att[a] * mu_a
        for t in teams:
            att[t] = (num_a[t] / den_a[t]) if den_a[t] > 1e-9 else 1.0
            dfn[t] = (num_d[t] / den_d[t]) if den_d[t] > 1e-9 else 1.0
        ma = sum(att.values()) / len(teams)
        md = sum(dfn.values()) / len(teams)
        att = {t: v / ma for t, v in att.items()}
        dfn = {t: v / md for t, v in dfn.items()}

    # résidus pour les σ
    eh, ea, em, et = [], [], [], []
    for r, wi in zip(rows, w):
        lh = att[r["home"]] * dfn[r["away"]] * mu_h
        la = att[r["away"]] * dfn[r["home"]] * mu_a
        eh.append((r["hg"] - lh) ** 2 * wi)
        ea.append((r["ag"] - la) ** 2 * wi)
        em.append(((r["hg"] - r["ag"]) - (lh - la)) ** 2 * wi)
        et.append(((r["hg"] + r["ag"]) - (lh + la)) ** 2 * wi)
    sig_h = math.sqrt(max(sum(eh) / sw, 25.0))
    sig_a = math.sqrt(max(sum(ea) / sw, 25.0))
    sig_m = math.sqrt(max(sum(em) / sw, 36.0))
    sig_t = math.sqrt(max(sum(et) / sw, 36.0))

    n_eff = {t: 0.0 for t in teams}
    n_brut = {t: 0 for t in teams}
    for r, wi in zip(rows, w):
        n_eff[r["home"]] += wi
        n_eff[r["away"]] += wi
        n_brut[r["home"]] += 1
        n_brut[r["away"]] += 1

    forces = {}
    for t in teams:
        ne = n_eff[t]
        s = min(1.0, ne / max(shrink, 1.0))
        a = att[t] ** s
        d = dfn[t] ** s
        forces[t] = {
            "att": round(a, 4),
            "dfn": round(d, 4),
            "puissance": round(a / max(d, 1e-6), 4),
            "n_eff": round(ne, 1),
            "n_brut": int(n_brut[t]),
            "lissage": round(s, 3),
        }
    return {
        "att": att, "dfn": dfn, "forces": forces,
        "mu_home": round(mu_h, 3), "mu_away": round(mu_a, 3),
        "sigma_home": round(sig_h, 3), "sigma_away": round(sig_a, 3),
        "sigma_margin": round(sig_m, 3), "sigma_total": round(sig_t, 3),
        "n": len(rows), "equipes": teams,
    }


def pronostic_basket(modele: dict, home: str, away: str) -> dict | None:
    F = modele.get("forces") or {}
    if home not in F or away not in F:
        return None
    mu_h = F[home]["att"] * F[away]["dfn"] * modele["mu_home"]
    mu_a = F[away]["att"] * F[home]["dfn"] * modele["mu_away"]
    mu_h = clip(mu_h, 70, 160)
    mu_a = clip(mu_a, 70, 160)
    margin = mu_h - mu_a
    total = mu_h + mu_a
    sm = max(modele.get("sigma_margin") or 12.0, 6.0)
    st = max(modele.get("sigma_total") or 12.0, 6.0)

    p1 = clip(norm_cdf(margin / sm), 0.02, 0.98)          # P(domicile gagne), pas de nul NBA
    p2 = 1.0 - p1

    def p_over(line):
        return clip(1.0 - norm_cdf((line - total) / st), 0.02, 0.98)

    def p_cover(spread_home):
        # spread_home négatif = favori domicile (ex. -5.5) → P(marge > 5.5)
        return clip(1.0 - norm_cdf(( -spread_home - margin) / sm) if False else
                    1.0 - norm_cdf(((-spread_home) - margin) / sm), 0.02, 0.98)

    # P(home covers S) where S is the home spread (negative if favorite)
    # home covers if (hg - ag) > -S   e.g. S=-5.5 → margin > 5.5
    def cover(s):
        return clip(1.0 - norm_cdf(((-s) - margin) / sm), 0.02, 0.98)

    lignes_tot = [x + 0.5 for x in range(int(total) - 12, int(total) + 13, 2)]
    lignes_tot = [x for x in lignes_tot if 180 <= x <= 260]
    if not lignes_tot:
        lignes_tot = [209.5, 215.5, 221.5]
    over = {str(x): round(p_over(x), 4) for x in lignes_tot}
    under = {str(x): round(1 - over[str(x)], 4) for x in lignes_tot}

    spreads = [-9.5, -7.5, -5.5, -3.5, -1.5, 1.5, 3.5, 5.5, 7.5, 9.5]
    cov = {str(s): round(cover(s), 4) for s in spreads}

    p10 = clip(1.0 - norm_cdf((10 - margin) / sm), 0.01, 0.99)
    p10a = clip(norm_cdf((-10 - margin) / sm), 0.01, 0.99)

    ne_h, ne_a = F[home].get("n_eff", 0), F[away].get("n_eff", 0)
    mini = min(ne_h, ne_a)
    conf = "haute" if mini >= 40 else "moyenne" if mini >= 18 else "faible"

    # totaux « canoniques » autour de l'espérance
    line_ref = round(total * 2) / 2
    if line_ref == int(line_ref):
        line_ref += 0.5
    return {
        "sport": "basket", "home": home, "away": away,
        "lambda_home": round(mu_h, 2), "lambda_away": round(mu_a, 2),
        "points_attendus": round(total, 2), "marge": round(margin, 2),
        "victoire_1": round(p1, 4), "nul": 0.0, "victoire_2": round(p2, 4),
        "over": over, "under": under,
        "spread": cov,
        "line_totale": line_ref,
        "over_ref": round(p_over(line_ref), 4),
        "under_ref": round(1 - p_over(line_ref), 4),
        "ecart_10_home": round(p10, 4), "ecart_10_away": round(p10a, 4),
        "sigma_margin": round(sm, 2), "sigma_total": round(st, 2),
        "fiabilite": {"niveau": conf, "home_n_eff": ne_h, "away_n_eff": ne_a,
                      "home_n_brut": F[home].get("n_brut", 0),
                      "away_n_brut": F[away].get("n_brut", 0)},
    }


# ===========================================================================
# HOCKEY — Poisson bivarié + correction τ (Dixon-Coles)
# ===========================================================================
HOCKEY_MAXG = 10
HOCKEY_DEMI_VIE = 160.0
HOCKEY_ITERS = 30


def fit_hockey(matchs: list, shrink: float = 14.0) -> dict | None:
    rows = []
    for m in matchs:
        d = _as_date(m.get("date"))
        try:
            hg, ag = int(m["hg"]), int(m["ag"])
        except (TypeError, ValueError, KeyError):
            continue
        h, a = str(m.get("home") or ""), str(m.get("away") or "")
        if not h or not a or h == a or h == "0" or a == "0":
            continue
        if hg < 0 or ag < 0 or hg > 15 or ag > 15:
            continue
        rows.append({"date": d, "home": h, "away": a, "hg": hg, "ag": ag})
    if len(rows) < 80:
        return None
    teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    ref = max((r["date"] for r in rows if r["date"]), default=date.today())
    w = [_poids(ref, r["date"], HOCKEY_DEMI_VIE) for r in rows]
    sw = sum(w) or 1.0
    mu_h = sum(wi * r["hg"] for wi, r in zip(w, rows)) / sw
    mu_a = sum(wi * r["ag"] for wi, r in zip(w, rows)) / sw
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}

    for _ in range(HOCKEY_ITERS):
        num_a = {t: 0.0 for t in teams}
        den_a = {t: 0.0 for t in teams}
        num_d = {t: 0.0 for t in teams}
        den_d = {t: 0.0 for t in teams}
        for r, wi in zip(rows, w):
            h, a = r["home"], r["away"]
            num_a[h] += wi * r["hg"]
            den_a[h] += wi * dfn[a] * mu_h
            num_a[a] += wi * r["ag"]
            den_a[a] += wi * dfn[h] * mu_a
            num_d[a] += wi * r["hg"]
            den_d[a] += wi * att[h] * mu_h
            num_d[h] += wi * r["ag"]
            den_d[h] += wi * att[a] * mu_a
        for t in teams:
            att[t] = (num_a[t] / den_a[t]) if den_a[t] > 1e-9 else 1.0
            dfn[t] = (num_d[t] / den_d[t]) if den_d[t] > 1e-9 else 1.0
        ma = sum(att.values()) / len(teams)
        md = sum(dfn.values()) / len(teams)
        att = {t: v / ma for t, v in att.items()}
        dfn = {t: v / md for t, v in dfn.items()}

    # ρ Dixon-Coles : moments sur les scores 0-0, 1-0, 0-1, 1-1
    # estimateur simple : moyenne des τ implicites, bornée.
    rho_num = rho_den = 0.0
    for r, wi in zip(rows, w):
        lh = max(att[r["home"]] * dfn[r["away"]] * mu_h, 1e-3)
        la = max(att[r["away"]] * dfn[r["home"]] * mu_a, 1e-3)
        if r["hg"] == 0 and r["ag"] == 0:
            rho_num += wi * (1 - math.exp(-lh) * math.exp(-la) / max(poisson_pmf(0, lh) * poisson_pmf(0, la), 1e-12))
            rho_den += wi
        # on se contente d'un ρ empirique faible, typique hockey ~ 0.02-0.08
    rho = 0.04
    n00 = sum(wi for r, wi in zip(rows, w) if r["hg"] == 0 and r["ag"] == 0)
    n11 = sum(wi for r, wi in zip(rows, w) if r["hg"] == 1 and r["ag"] == 1)
    attendu_00 = sum(wi * poisson_pmf(0, att[r["home"]] * dfn[r["away"]] * mu_h)
                     * poisson_pmf(0, att[r["away"]] * dfn[r["home"]] * mu_a)
                     for r, wi in zip(rows, w))
    if attendu_00 > 1e-6:
        # si plus de 0-0 que Poisson → ρ positif (corrélation négative des buts)
        rho = clip((n00 - attendu_00) / sw * 8.0, -0.12, 0.12)

    n_eff = {t: 0.0 for t in teams}
    n_brut = {t: 0 for t in teams}
    for r, wi in zip(rows, w):
        n_eff[r["home"]] += wi
        n_eff[r["away"]] += wi
        n_brut[r["home"]] += 1
        n_brut[r["away"]] += 1

    forces = {}
    for t in teams:
        ne = n_eff[t]
        s = min(1.0, ne / max(shrink, 1.0))
        a = att[t] ** s
        d = dfn[t] ** s
        forces[t] = {
            "att": round(a, 4), "dfn": round(d, 4),
            "puissance": round(a / max(d, 1e-6), 4),
            "n_eff": round(ne, 1), "n_brut": int(n_brut[t]), "lissage": round(s, 3),
        }
    return {
        "forces": forces, "gamma": round(mu_h, 4), "s_away": round(mu_a, 4),
        "rho": round(rho, 4), "n": len(rows), "equipes": teams,
    }


def matrice_hockey(modele: dict, home: str, away: str):
    F = modele.get("forces") or {}
    if home not in F or away not in F:
        return None
    lam = clip(F[home]["att"] * F[away]["dfn"] * modele["gamma"], 0.15, 8.0)
    mu = clip(F[away]["att"] * F[home]["dfn"] * modele["s_away"], 0.15, 8.0)
    rho = clip(modele.get("rho") or 0.0, -0.2, 0.2)
    ph = [poisson_pmf(i, lam) for i in range(HOCKEY_MAXG + 1)]
    pa = [poisson_pmf(j, mu) for j in range(HOCKEY_MAXG + 1)]
    M = [[ph[i] * pa[j] for j in range(HOCKEY_MAXG + 1)] for i in range(HOCKEY_MAXG + 1)]
    M[0][0] *= max(1 - lam * mu * rho, 1e-9)
    M[0][1] *= max(1 + lam * rho, 1e-9)
    M[1][0] *= max(1 + mu * rho, 1e-9)
    M[1][1] *= max(1 - rho, 1e-9)
    s = sum(sum(row) for row in M)
    if s <= 0:
        return None
    M = [[max(x, 0.0) / s for x in row] for row in M]
    return M, lam, mu


def pronostic_hockey(modele: dict, home: str, away: str) -> dict | None:
    r = matrice_hockey(modele, home, away)
    if r is None:
        return None
    M, lam, mu = r
    n = HOCKEY_MAXG + 1
    p1 = pX = p2 = 0.0
    over = {str(x): 0.0 for x in (3.5, 4.5, 5.5, 6.5, 7.5)}
    under = {str(x): 0.0 for x in (3.5, 4.5, 5.5, 6.5, 7.5)}
    btts = 0.0
    puck_h = puck_a = 0.0
    cases = []
    for i in range(n):
        for j in range(n):
            p = M[i][j]
            if i > j:
                p1 += p
            elif i == j:
                pX += p
            else:
                p2 += p
            tot = i + j
            for x in (3.5, 4.5, 5.5, 6.5, 7.5):
                if tot > x:
                    over[str(x)] += p
                elif tot < x:
                    under[str(x)] += p
            if i >= 1 and j >= 1:
                btts += p
            if i - j >= 2:
                puck_h += p
            if j - i >= 2:
                puck_a += p
            cases.append((i, j, p))
    cases.sort(key=lambda z: -z[2])
    # moneyline NHL = vainqueur y compris prolongation : on partage le nul 50/50
    ml1 = p1 + 0.5 * pX
    ml2 = p2 + 0.5 * pX
    F = modele["forces"]
    ne_h, ne_a = F[home].get("n_eff", 0), F[away].get("n_eff", 0)
    mini = min(ne_h, ne_a)
    conf = "haute" if mini >= 40 else "moyenne" if mini >= 18 else "faible"
    return {
        "sport": "hockey", "home": home, "away": away,
        "lambda_home": round(lam, 3), "lambda_away": round(mu, 3),
        "buts_attendus": round(lam + mu, 2),
        "victoire_1": round(ml1, 4), "nul": round(pX, 4), "victoire_2": round(ml2, 4),
        "regulation_1": round(p1, 4), "regulation_X": round(pX, 4), "regulation_2": round(p2, 4),
        "over": {k: round(v, 4) for k, v in over.items()},
        "under": {k: round(v, 4) for k, v in under.items()},
        "btts_oui": round(btts, 4), "btts_non": round(1 - btts, 4),
        "puck_home": round(puck_h, 4), "puck_away": round(puck_a, 4),
        "scores_top": [{"score": f"{i}-{j}", "p": round(p, 4)} for i, j, p in cases[:8]],
        "matrice": [[round(M[i][j], 4) for j in range(8)] for i in range(8)],
        "fiabilite": {"niveau": conf, "home_n_eff": ne_h, "away_n_eff": ne_a,
                      "home_n_brut": F[home].get("n_brut", 0),
                      "away_n_brut": F[away].get("n_brut", 0)},
    }


# ===========================================================================
# TENNIS — Elo surface + sets indépendants
# ===========================================================================
ELO_START = 1500.0
ELO_K = 24.0
ELO_SURFACE_K = 28.0


def _elo_expect(a, b):
    return 1.0 / (1.0 + 10 ** ((b - a) / 400.0))


def fit_tennis(matchs: list) -> dict | None:
    """Elo en ligne (walk-forward naturel) + Elo par surface.

    matchs triés par date : [{date, winner, loser, surface, best_of, wsets, lsets, wrank, lrank}]
    """
    rows = []
    for m in matchs:
        w, l = str(m.get("winner") or "").strip(), str(m.get("loser") or "").strip()
        if not w or not l or w == l:
            continue
        d = _as_date(m.get("date"))
        surf = (m.get("surface") or "Hard").title()
        if surf not in ("Hard", "Clay", "Grass", "Carpet"):
            surf = "Hard"
        try:
            bo = int(m.get("best_of") or 3)
        except (TypeError, ValueError):
            bo = 3
        if bo not in (3, 5):
            bo = 3
        rows.append({
            "date": d, "winner": w, "loser": l, "surface": surf, "best_of": bo,
            "wrank": _rank(m.get("wrank")), "lrank": _rank(m.get("lrank")),
            "wsets": _inum(m.get("wsets")), "lsets": _inum(m.get("lsets")),
        })
    if len(rows) < 200:
        return None
    rows.sort(key=lambda r: r["date"] or date(1990, 1, 1))

    elo = defaultdict(lambda: ELO_START)
    elo_s = {s: defaultdict(lambda: ELO_START) for s in ("Hard", "Clay", "Grass", "Carpet")}
    n = defaultdict(int)
    last = {}
    last_rank = {}
    last_surf = {}
    wins = defaultdict(int)
    # pour le backtest : on stocke la proba AVANT mise à jour
    preds = []

    for r in rows:
        w, l, s = r["winner"], r["loser"], r["surface"]
        ew = 0.65 * elo[w] + 0.35 * elo_s[s][w]
        el = 0.65 * elo[l] + 0.35 * elo_s[s][l]
        p = _elo_expect(ew, el)
        preds.append({"p": p, "wrank": r["wrank"], "lrank": r["lrank"],
                      "surface": s, "best_of": r["best_of"],
                      "date": r["date"], "winner": w, "loser": l})
        k = ELO_K
        elo[w] += k * (1 - p)
        elo[l] += k * (0 - (1 - p))
        ps = _elo_expect(elo_s[s][w], elo_s[s][l])
        elo_s[s][w] += ELO_SURFACE_K * (1 - ps)
        elo_s[s][l] += ELO_SURFACE_K * (0 - (1 - ps))
        n[w] += 1
        n[l] += 1
        wins[w] += 1
        last[w] = r["date"]
        last[l] = r["date"]
        if r["wrank"]:
            last_rank[w] = r["wrank"]
        if r["lrank"]:
            last_rank[l] = r["lrank"]
        last_surf[w] = s
        last_surf[l] = s

    joueurs = {}
    for nom in n:
        joueurs[nom] = {
            "elo": round(elo[nom], 1),
            "elo_hard": round(elo_s["Hard"][nom], 1),
            "elo_clay": round(elo_s["Clay"][nom], 1),
            "elo_grass": round(elo_s["Grass"][nom], 1),
            "n": int(n[nom]),
            "victoires": int(wins[nom]),
            "rank": last_rank.get(nom),
            "dernier": str(last[nom]) if last.get(nom) else None,
            "surface": last_surf.get(nom),
        }
    return {"joueurs": joueurs, "n": len(rows), "preds": preds}


def _rank(x):
    try:
        v = int(float(x))
        return v if 1 <= v <= 3000 else None
    except (TypeError, ValueError):
        return None


def _inum(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def p_match_from_set(p_set: float, best_of: int) -> float:
    """P(gagner le match) si P(gagner un set) = p_set, sets i.i.d."""
    p = clip(p_set, 0.02, 0.98)
    q = 1 - p
    if best_of >= 5:
        # 3 sets gagnants : P(3-0)+P(3-1)+P(3-2)
        return p ** 3 * (1 + 3 * q + 6 * q ** 2)
    # 2 sets gagnants
    return p ** 2 * (1 + 2 * q)


def p_set_from_match(p_match: float, best_of: int) -> float:
    """Inverse numérique de p_match_from_set."""
    cible = clip(p_match, 0.02, 0.98)
    lo, hi = 0.02, 0.98
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        v = p_match_from_set(mid, best_of)
        if v < cible:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def pronostic_tennis(modele: dict, p1: str, p2: str, surface: str = "Hard",
                     best_of: int = 3) -> dict | None:
    J = modele.get("joueurs") or {}
    if p1 not in J or p2 not in J:
        return None
    surf = (surface or "Hard").title()
    key = {"Hard": "elo_hard", "Clay": "elo_clay", "Grass": "elo_grass"}.get(surf, "elo_hard")
    e1 = 0.65 * J[p1]["elo"] + 0.35 * J[p1].get(key, J[p1]["elo"])
    e2 = 0.65 * J[p2]["elo"] + 0.35 * J[p2].get(key, J[p2]["elo"])
    # joueurs peu vus : on mélange avec un prior 1500
    def shrink_elo(nom, e):
        n = J[nom].get("n") or 0
        w = min(1.0, n / 25.0)
        return w * e + (1 - w) * ELO_START
    e1, e2 = shrink_elo(p1, e1), shrink_elo(p2, e2)
    p1w = clip(_elo_expect(e1, e2), 0.03, 0.97)
    p_set = p_set_from_match(p1w, best_of)
    q = 1 - p_set
    if best_of >= 5:
        s30 = p_set ** 3
        s31 = 3 * p_set ** 3 * q
        s32 = 6 * p_set ** 3 * q ** 2
        s03 = q ** 3
        s13 = 3 * q ** 3 * p_set
        s23 = 6 * q ** 3 * p_set ** 2
        sets = {"3-0": s30, "3-1": s31, "3-2": s32, "0-3": s03, "1-3": s13, "2-3": s23}
        # jeux : ~ 9.8 par set, nombre de sets attendu
        e_sets = 3 * (s30 + s03) + 4 * (s31 + s13) + 5 * (s32 + s23)
    else:
        s20 = p_set ** 2
        s21 = 2 * p_set ** 2 * q
        s02 = q ** 2
        s12 = 2 * q ** 2 * p_set
        sets = {"2-0": s20, "2-1": s21, "0-2": s02, "1-2": s12}
        e_sets = 2 * (s20 + s02) + 3 * (s21 + s12)
    e_jeux = e_sets * 9.7
    # σ jeux ~ 4.2 (empirique ATP)
    sig_j = 4.4
    def p_over_jeux(line):
        return clip(1.0 - norm_cdf((line - e_jeux) / sig_j), 0.03, 0.97)
    lignes = [19.5, 20.5, 21.5, 22.5, 23.5, 24.5, 25.5, 26.5]
    over = {str(x): round(p_over_jeux(x), 4) for x in lignes}
    under = {str(x): round(1 - over[str(x)], 4) for x in lignes}
    n1, n2 = J[p1].get("n", 0), J[p2].get("n", 0)
    mini = min(n1, n2)
    conf = "haute" if mini >= 40 else "moyenne" if mini >= 15 else "faible"
    return {
        "sport": "tennis", "home": p1, "away": p2, "surface": surf, "best_of": best_of,
        "elo_1": round(e1, 1), "elo_2": round(e2, 1),
        "victoire_1": round(p1w, 4), "nul": 0.0, "victoire_2": round(1 - p1w, 4),
        "p_set": round(p_set, 4),
        "sets": {k: round(v, 4) for k, v in sets.items()},
        "sets_attendus": round(e_sets, 2), "jeux_attendus": round(e_jeux, 1),
        "over": over, "under": under,
        "straight_sets_1": round(sets.get("2-0") or sets.get("3-0") or 0, 4),
        "straight_sets_2": round(sets.get("0-2") or sets.get("0-3") or 0, 4),
        "fiabilite": {"niveau": conf, "home_n_eff": n1, "away_n_eff": n2,
                      "home_n_brut": n1, "away_n_brut": n2,
                      "rank_1": J[p1].get("rank"), "rank_2": J[p2].get("rank")},
    }


def stats_equipe(hist: list, team: str, jours: int = 400) -> dict | None:
    """Forme récente (victoires / points ou buts). hist = matchs {date,home,away,hg,ag}."""
    rec = []
    for m in hist:
        d = _as_date(m.get("date"))
        h, a = m.get("home"), m.get("away")
        if team not in (h, a):
            continue
        try:
            hg, ag = int(m["hg"]), int(m["ag"])
        except (TypeError, ValueError, KeyError):
            continue
        rec.append((d, h, a, hg, ag))
    if not rec:
        return None
    rec.sort(key=lambda x: x[0] or date(1990, 1, 1))
    cut = (rec[-1][0] or date.today()) - timedelta(days=jours)
    rec2 = [x for x in rec if (x[0] or date.today()) >= cut]
    if not rec2:
        rec2 = rec[-20:]
    n = len(rec2)
    v = d = 0
    mf = me = 0
    forme = []
    for dt, h, a, hg, ag in rec2:
        if h == team:
            marque, enc = hg, ag
            win = hg > ag
            draw = hg == ag
        else:
            marque, enc = ag, hg
            win = ag > hg
            draw = ag == hg
        mf += marque
        me += enc
        if win:
            v += 1
            forme.append("V")
        elif draw:
            d += 1
            forme.append("N")
        else:
            forme.append("D")
    return {
        "matchs": n, "victoires": v, "nuls": d, "defaites": n - v - d,
        "marques": round(mf / n, 2), "encaisses": round(me / n, 2),
        "forme": "".join(forme[-5:]),
    }
