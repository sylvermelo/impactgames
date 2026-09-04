"""
Entraînement unique des trois moteurs + backtest walk-forward honnête.

Sortie : data/modeles.json  (tout ce dont l'application a besoin)
"""
from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import moteurs as M
import sources as S

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"


def _saison_label(d: str) -> str:
    if not d or len(d) < 4:
        return "?"
    y = int(d[:4])
    try:
        m = int(d[5:7])
    except (TypeError, ValueError):
        m = 10
    return f"{y}-{y+1}" if m >= 8 else f"{y-1}-{y}"


# ------------------------------------------------------------------ backtests
def backtest_ml(matchs, fit_fn, pron_fn, sport: str, min_hist=400, pas=1):
    """Walk-forward par saison : on entraîne sur le passé, on prédit la saison suivante."""
    par = defaultdict(list)
    for m in matchs:
        par[_saison_label(m.get("date") or "")].append(m)
    saisons = sorted(k for k in par if k != "?")
    rows = []
    for i, s in enumerate(saisons):
        if i == 0:
            continue
        hist = []
        for k in saisons[:i]:
            hist.extend(par[k])
        if len(hist) < min_hist:
            continue
        modele = fit_fn(hist)
        if not modele:
            continue
        for m in par[s]:
            p = pron_fn(modele, m["home"], m["away"])
            if not p:
                continue
            try:
                hg, ag = int(m["hg"]), int(m["ag"])
            except (TypeError, ValueError, KeyError):
                continue
            y = 0 if hg > ag else 1  # 0 = home, 1 = away (pas de nul ML)
            if hg == ag:
                continue
            p1, p2 = p["victoire_1"], p["victoire_2"]
            s12 = p1 + p2
            if s12 <= 0:
                continue
            p1, p2 = p1 / s12, p2 / s12
            rec = {"p1": p1, "p2": p2, "y": y, "hg": hg, "ag": ag,
                   "exp": p.get("points_attendus") or p.get("buts_attendus")}
            # cotes marché (américaines → proba)
            mh, ma = M.american_to_prob(m.get("ml_h")), M.american_to_prob(m.get("ml_a"))
            if mh and ma:
                s = mh + ma
                rec["m1"], rec["m2"] = mh / s, ma / s
                rec["c1"] = M.american_to_decimal(m.get("ml_h"))
                rec["c2"] = M.american_to_decimal(m.get("ml_a"))
            rows.append(rec)
    return _resumer_ml(rows, sport)


def _resumer_ml(rows, sport):
    if len(rows) < 50:
        return {"n": len(rows), "sport": sport, "note": "échantillon insuffisant"}
    n = len(rows)
    ll = -sum(math.log(max(r["p1"] if r["y"] == 0 else r["p2"], 1e-9)) for r in rows) / n
    acc = sum(1 for r in rows if (r["p1"] >= r["p2"]) == (r["y"] == 0)) / n
    # calibration
    cal = []
    for a, b in ((0.0, 0.20), (0.20, 0.35), (0.35, 0.50), (0.50, 0.65), (0.65, 1.01)):
        bucket = []
        for r in rows:
            for p, y in ((r["p1"], 1 if r["y"] == 0 else 0), (r["p2"], 1 if r["y"] == 1 else 0)):
                if a <= p < b:
                    bucket.append((p, y))
        if len(bucket) > 40:
            mp = sum(p for p, _ in bucket) / len(bucket)
            my = sum(y for _, y in bucket) / len(bucket)
            cal.append({"plage": f"{int(a*100)}-{int(min(b,1)*100)} %",
                        "n": len(bucket), "predite": round(mp, 3),
                        "reel": round(my, 3), "ecart": round(my - mp, 3)})
    # vs marché + ROI
    mk = [r for r in rows if r.get("m1") is not None]
    llm = accm = roi = clv = None
    n_paris = 0
    if len(mk) > 80:
        llm = -sum(math.log(max(r["m1"] if r["y"] == 0 else r["m2"], 1e-9)) for r in mk) / len(mk)
        accm = sum(1 for r in mk if (r["m1"] >= r["m2"]) == (r["y"] == 0)) / len(mk)
        pnl = mise = 0.0
        for r in mk:
            for j, (p, c) in enumerate(((r["p1"], r.get("c1")), (r["p2"], r.get("c2")))):
                if not c or c <= 1.01:
                    continue
                if p > (1 / c) * 1.05:
                    mise += 1
                    n_paris += 1
                    if r["y"] == j:
                        pnl += c - 1
                    else:
                        pnl -= 1
        roi = (pnl / mise) if mise else None
        clv = (llm - ll) if llm is not None else None  # >0 : le modèle bat le marché en log-loss
    return {
        "sport": sport, "n": n, "n_marche": len(mk),
        "logloss_modele": round(ll, 4),
        "logloss_marche": round(llm, 4) if llm is not None else None,
        "precision_modele": round(acc, 4),
        "precision_marche": round(accm, 4) if accm is not None else None,
        "roi_edge5": round(roi, 4) if roi is not None else None,
        "n_paris_edge5": n_paris,
        "clv": round(clv, 4) if clv is not None else None,
        "calibration": cal,
    }


def backtest_tennis(preds: list) -> dict:
    """Les preds Elo sont déjà walk-forward (proba avant mise à jour)."""
    rows = []
    for r in preds:
        p = r["p"]
        rows.append({"p1": p, "p2": 1 - p, "y": 0})  # y=0 : le « home » est le vainqueur réel
    # log-loss du vainqueur = -log(p)
    if len(rows) < 200:
        return {"n": len(rows), "sport": "tennis"}
    n = len(rows)
    ll = -sum(math.log(max(r["p1"], 1e-9)) for r in rows) / n
    acc = sum(1 for r in rows if r["p1"] >= 0.5) / n
    cal = []
    for a, b in ((0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01)):
        bucket = [r["p1"] for r in rows if a <= r["p1"] < b]
        if len(bucket) > 80:
            mp = sum(bucket) / len(bucket)
            # tous ces matchs ont été gagnés par le favori-modèle (y=0 toujours ici)
            # ATTENTION : p1 est P(vainqueur réel). Donc fréquence réelle = 1.0 ? NON
            # p = P(winner beats loser) BEFORE the match, and winner DID win.
            # So we're measuring: when we said p, did it happen? It ALWAYS happened
            # because we condition on the winner. That's the log-loss of the winner,
            # calibration needs both outcomes.
            pass
    # calibration honnête : on prend p du favori Elo et on regarde s'il a gagné
    fav = []
    for r in preds:
        p = r["p"]  # P(winner) — always the actual winner
        # reconstruct: the favorite is whoever had p>=0.5, they won iff p>=0.5
        fav.append((max(p, 1 - p), p >= 0.5))
    for a, b in ((0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01)):
        bucket = [(p, y) for p, y in fav if a <= p < b]
        if len(bucket) > 80:
            mp = sum(p for p, _ in bucket) / len(bucket)
            my = sum(1 for _, y in bucket if y) / len(bucket)
            cal.append({"plage": f"{int(a*100)}-{int(min(b,1)*100)} %",
                        "n": len(bucket), "predite": round(mp, 3),
                        "reel": round(my, 3), "ecart": round(my - mp, 3)})
    return {
        "sport": "tennis", "n": n,
        "logloss_modele": round(ll, 4),
        "precision_favori": round(acc, 4),
        "calibration": cal,
        "note": "Elo en ligne : chaque match est prédit sans le connaître. "
                "Pas de cotes de clôture dans l'archive Sackmann.",
    }


# ------------------------------------------------------------------ stats + classement
def pack_ligue_equipe(modele, hist, nom, pays, sport):
    equipes = modele.get("equipes") or list((modele.get("forces") or {}).keys())
    # équipes « actuelles » = celles vues dans les 18 derniers mois
    recents = []
    cutoff = None
    dates = [m.get("date") for m in hist if m.get("date")]
    if dates:
        cutoff = max(dates)
        # 18 mois
        try:
            y, mo, d = int(cutoff[:4]), int(cutoff[5:7]), int(cutoff[8:10])
            y2 = y - 1 if mo > 6 else y - 2
            cutoff_old = f"{y2}-{mo:02d}-{d:02d}"
        except Exception:
            cutoff_old = "2000-01-01"
        recents = [m for m in hist if (m.get("date") or "") >= cutoff_old]
    act = sorted({m["home"] for m in recents} | {m["away"] for m in recents})
    if not act:
        act = sorted(equipes)
    stats = {}
    for t in act:
        s = M.stats_equipe(hist, t)
        if s:
            stats[t] = s
    forces = {t: modele["forces"][t] for t in act if t in modele.get("forces", {})}
    out = {
        "nom": nom, "pays": pays, "sport": sport,
        "n_historique": modele.get("n") or len(hist),
        "equipes_actuelles": [t for t in act if t in forces],
        "forces": forces, "stats": stats,
        "dernier_match": max((m.get("date") or "" for m in hist), default=""),
        "saison": _saison_label(max((m.get("date") or "" for m in hist), default="")),
    }
    if sport == "basket":
        out.update({
            "mu_home": modele["mu_home"], "mu_away": modele["mu_away"],
            "sigma_margin": modele["sigma_margin"], "sigma_total": modele["sigma_total"],
            "points_moy": round(modele["mu_home"] + modele["mu_away"], 1),
        })
    else:
        out.update({
            "gamma": modele["gamma"], "s_away": modele["s_away"], "rho": modele["rho"],
            "buts_moy": round(modele["gamma"] + modele["s_away"], 2),
        })
    return out


def pack_tennis(modele, ligue):
    J = modele["joueurs"]
    # on garde les joueurs actifs (vus récemment ou volume suffisant)
    actifs = []
    for nom, v in J.items():
        if (v.get("n") or 0) >= 8:
            actifs.append(nom)
    actifs.sort(key=lambda n: -J[n]["elo"])
    # top 400 pour ne pas gonfler le JSON
    keep = set(actifs[:400])
    joueurs = {n: J[n] for n in keep}
    return {
        "nom": ligue, "pays": "Circuit", "sport": "tennis",
        "n_historique": modele["n"],
        "joueurs": joueurs,
        "equipes_actuelles": actifs[:250],
        "dernier_match": max((J[n].get("dernier") or "" for n in keep), default=""),
        "saison": str(date.today().year),
    }


def main():
    t0 = time.time()
    DATA.mkdir(exist_ok=True)
    print("=== IMPACT GAMES — entraînement ===")
    S.assurer_archives()

    nba = S.charger_sbr_nba()
    nhl = S.charger_sbr_nhl()
    print(f"  archive SBR : NBA {len(nba)} | NHL {len(nhl)}")

    recent = S.espn_historique_recent(annees=4)
    def fusion(a, b):
        vus = {(m["date"], m["home"], m["away"]) for m in a}
        out = list(a)
        for m in b:
            cle = (m["date"], m["home"], m["away"])
            if cle in vus or not m.get("hg") or not m.get("ag"):
                continue
            vus.add(cle)
            out.append(m)
        out.sort(key=lambda x: x.get("date") or "")
        return out

    nba = fusion(nba, recent.get("NBA") or [])
    nhl = fusion(nhl, recent.get("NHL") or [])
    wnba = recent.get("WNBA") or []
    euro = recent.get("Euroleague") or []
    print(f"  après ESPN : NBA {len(nba)} | NHL {len(nhl)} | WNBA {len(wnba)} | Euro {len(euro)}")

    sack = S.charger_atp_sackmann()
    td = S.charger_tennis_data()
    tennis = S.fusionner_tennis(sack, td)
    print(f"  tennis : {len(tennis)} matchs (Sackmann {len(sack)} + tennis-data {len(td)})")

    sports = {"basket": {"ligues": {}}, "hockey": {"ligues": {}}, "tennis": {"ligues": {}}}
    hist_store = {"basket": {}, "hockey": {}, "tennis": {}}

    # ---- basket
    for lig, hist, pays in (
        ("NBA", nba, "USA"),
        ("WNBA", wnba, "USA"),
        ("Euroleague", euro, "Europe"),
    ):
        if len(hist) < 120:
            print(f"  {lig}: pas assez de matchs ({len(hist)})")
            continue
        mo = M.fit_basket(hist)
        if not mo:
            continue
        sports["basket"]["ligues"][lig] = pack_ligue_equipe(mo, hist, lig, pays, "basket")
        hist_store["basket"][lig] = hist
        print(f"  {lig:<12} {mo['n']:>6} matchs | μ {mo['mu_home']:.1f}-{mo['mu_away']:.1f} "
              f"| σmarge {mo['sigma_margin']:.1f} | {len(mo['equipes'])} équipes")

    # ---- hockey
    if len(nhl) >= 120:
        mo = M.fit_hockey(nhl)
        if mo:
            sports["hockey"]["ligues"]["NHL"] = pack_ligue_equipe(mo, nhl, "NHL", "USA/Canada", "hockey")
            hist_store["hockey"]["NHL"] = nhl
            print(f"  {'NHL':<12} {mo['n']:>6} matchs | λ {mo['gamma']:.2f}-{mo['s_away']:.2f} "
                  f"| ρ {mo['rho']:.3f} | {len(mo['equipes'])} équipes")

    # ---- tennis (ATP, et WTA si présent)
    par_lig = defaultdict(list)
    for m in tennis:
        par_lig[m.get("ligue") or "ATP"].append(m)
    tennis_preds = {}
    for lig, hist in par_lig.items():
        if len(hist) < 300:
            continue
        mo = M.fit_tennis(hist)
        if not mo:
            continue
        sports["tennis"]["ligues"][lig] = pack_tennis(mo, lig)
        tennis_preds[lig] = mo.get("preds") or []
        print(f"  {lig:<12} {mo['n']:>6} matchs | {len(mo['joueurs'])} joueurs")

    # ---- backtests (sur les ligues principales)
    print("  backtest walk-forward…")
    bilan = {"par_sport": {}}
    if nba:
        bilan["par_sport"]["basket"] = backtest_ml(nba, M.fit_basket, M.pronostic_basket, "basket")
        b = bilan["par_sport"]["basket"]
        print(f"    NBA  logloss {b.get('logloss_modele')} vs marché {b.get('logloss_marche')} "
              f"| préc. {b.get('precision_modele')} | ROI {b.get('roi_edge5')} | n={b.get('n')}")
    if nhl:
        bilan["par_sport"]["hockey"] = backtest_ml(nhl, M.fit_hockey, M.pronostic_hockey, "hockey")
        b = bilan["par_sport"]["hockey"]
        print(f"    NHL  logloss {b.get('logloss_modele')} vs marché {b.get('logloss_marche')} "
              f"| préc. {b.get('precision_modele')} | ROI {b.get('roi_edge5')} | n={b.get('n')}")
    if tennis_preds.get("ATP"):
        bilan["par_sport"]["tennis"] = backtest_tennis(tennis_preds["ATP"])
        b = bilan["par_sport"]["tennis"]
        print(f"    ATP  logloss {b.get('logloss_modele')} | préc. favori {b.get('precision_favori')} "
              f"| n={b.get('n')}")

    total = sum(L.get("n_historique", 0)
                for sp in sports.values() for L in sp["ligues"].values())
    out = {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "sports": sports,
        "fixtures": [],
        "calendrier_log": {},
        "bilan": bilan,
        "meta": {
            "total_matchs": total,
            "n_ligues": sum(len(sp["ligues"]) for sp in sports.values()),
            "duree_s": round(time.time() - t0, 1),
            "sources": [
                "Sportsbook Review archive 10 ans (NBA, NHL) — cotes de clôture incluses",
                "ESPN API publique (calendrier + saisons récentes, sans clé)",
                "tennis-data.co.uk (ATP/WTA + cotes) si joignable",
                "Miroir Sackmann ATP 2012-2022 (GitHub, secours tennis)",
            ],
        },
    }
    dest = DATA / "modeles.json"
    dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\nmodeles.json : {dest.stat().st_size/1024:.0f} Ko | {out['meta']['n_ligues']} ligues | "
          f"{total} matchs | {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
