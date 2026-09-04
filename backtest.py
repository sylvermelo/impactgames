"""
BACKTEST WALK-FORWARD — la seule chose qui prouve qu'un moteur vaut quelque chose
================================================================================
Règle absolue : pour prédire les matchs de l'année Y, on n'utilise QUE ce qui
s'est passé avant l'année Y. Aucun paramètre, aucun classement, aucune cote du
futur ne filtre. C'est ce qui distingue un modèle d'un numéro de voyante.

Usage :
    python3 backtest.py tennis      # un seul sport
    python3 backtest.py             # les trois
    python3 backtest.py --ecrit     # enregistre data/backtest_<sport>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from sports.commun import calibration, log_loss, rps

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"


def _probas_2(p_a) -> np.ndarray:
    p = np.clip(np.asarray(p_a, dtype=float), 1e-6, 1 - 1e-6)
    return np.stack([p, 1 - p], axis=1)


# ==================================================================== TENNIS
def backtest_tennis(ecrit: bool = False) -> dict:
    from sports import tennis as T

    matchs = T.charger_matchs(DATA)
    if not matchs:
        return {"erreur": "aucun fichier data/atp_matches_*.csv — lance maj.py"}
    elo = T.entrainer_elo(matchs)
    avant = elo["avant"]
    annees = sorted({m["annee"] for m in matchs})

    print(f"\n{'=' * 78}\nTENNIS ATP — {len(matchs)} matchs, {annees[0]} → {annees[-1]}\n{'=' * 78}")

    lignes = []
    for annee in annees:
        entrain = [m for m in matchs if m["annee"] <= annee]
        test_idx = [i for i, m in enumerate(matchs) if m["annee"] == annee]
        if len(test_idx) < 200 or len(entrain) < 3000:
            continue
        sous_elo = {**elo, "avant": [avant[i] for i in range(len(entrain))]}
        params = T.ajuster_logistique(entrain, sous_elo)
        # beta est ré-ajusté à chaque pas : il n'a le droit de voir que le passé
        beta = T.ajuster_beta(entrain, sous_elo, params)["beta"]
        p_modele, p_elo, p_rang = [], [], []
        for i in test_idx:
            m = matchs[i]
            ra, rb = avant[i]
            p_modele.append(T.pronostic(ra, rb, m["surface"], m["best_of"],
                                        beta, params)["p_a"])
            p_elo.append(1.0 / (1.0 + 10.0 ** (-(ra - rb) / 400.0)))
            p_rang.append(1.0 if ra > rb else 0.0)

        # colonne 0 = « A gagne », et A est TOUJOURS le vainqueur réel dans la
        # base Sackmann : le résultat observé vaut donc 0 pour chaque match.
        reel = np.zeros(len(test_idx), dtype=int)
        P = _probas_2(p_modele)
        lignes.append({
            "annee": annee,
            "n": len(test_idx),
            "ll_modele": log_loss(_probas_2(p_modele), reel),
            "ll_elo": log_loss(_probas_2(p_elo), reel),
            "ll_elo_brut": log_loss(_probas_2(p_rang), reel),
            "ll_hasard": log_loss(_probas_2([0.5] * len(test_idx)), reel),
            "rps_modele": rps(P, reel),
            "precision": float(np.mean(np.asarray(p_modele) > 0.5)),
            # Chaque COLONNE de probabilité doit être appariée à son issue à
            # elle : la colonne 0 au vecteur « la colonne 0 s'est produite »,
            # la colonne 1 au contraire. Aplatir les deux vecteurs séparément
            # (l'erreur qu'on a faite) mélange tout et donne ~50 % partout.
            "calibration": calibration(P.ravel(), np.eye(2)[reel].ravel()),
            "p_modele": [float(x) for x in p_modele],
        })
        l = lignes[-1]
        print(f"\n  {annee} — {l['n']} matchs de contrôle (jamais servis à l'ajustement)")
        print(f"    log-loss  modèle {l['ll_modele']:.4f} | Elo seul {l['ll_elo']:.4f}"
              f" | hasard {l['ll_hasard']:.4f}")
        print(f"    RPS {l['rps_modele']:.4f} | favori du modèle gagne "
              f"{l['precision']:.1%} des matchs")

    if not lignes:
        return {"erreur": "pas assez d'historique pour un backtest"}

    moy = lambda k: float(np.mean([l[k] for l in lignes]))
    total = sum(l["n"] for l in lignes)
    # moyenne pondérée par le nombre de matchs, pas moyenne des moyennes
    pond = lambda k: float(sum(l[k] * l["n"] for l in lignes) / total)
    rapport = {
        "sport": "tennis",
        "n_matchs": total,
        "annees": [l["annee"] for l in lignes],
        "logloss_modele": pond("ll_modele"),
        "logloss_elo": pond("ll_elo"),
        "logloss_hasard": pond("ll_hasard"),
        "rps_modele": pond("rps_modele"),
        "precision_favori": float(sum(l["precision"] * l["n"] for l in lignes) / total),
        "detail": [{k: v for k, v in l.items() if k != "p_modele"} for l in lignes],
    }
    gain = rapport["logloss_hasard"] - rapport["logloss_modele"]
    rapport["gain_vs_hasard"] = gain

    print(f"\n  {'-' * 74}")
    print(f"  BILAN sur {total} matchs de contrôle")
    print(f"    log-loss modèle       {rapport['logloss_modele']:.4f}")
    print(f"    log-loss Elo seul     {rapport['logloss_elo']:.4f}")
    print(f"    log-loss hasard       {rapport['logloss_hasard']:.4f}")
    print(f"    RPS                   {rapport['rps_modele']:.4f}")
    print(f"    favori gagne          {rapport['precision_favori']:.1%}")
    print(f"    gain vs hasard        {gain:+.4f}")
    verdict = ("le modèle bat l'Elo seul" if rapport["logloss_modele"] < rapport["logloss_elo"]
               else "l'Elo seul reste devant : la chaîne de Markov n'ajoute rien ici")
    print(f"    verdict               {verdict}")

    print(f"\n  CALIBRATION (dernière année évaluée)")
    for t in lignes[-1]["calibration"]:
        print(f"    prédit {t['de']:>4.0%}-{t['a']:<4.0%} n={t['n']:>5} "
              f"réel {t['reel']:>6.1%}  écart {t['ecart']:+6.1%}")

    if ecrit:
        DATA.mkdir(exist_ok=True)
        (DATA / "backtest_tennis.json").write_text(
            json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  → data/backtest_tennis.json écrit")
    return rapport


# ============================================================ points d'entrée
FONCTIONS = {"tennis": backtest_tennis}


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    ecrit = "--ecrit" in argv
    cibles = args or list(FONCTIONS)
    rc = 0
    for c in cibles:
        if c not in FONCTIONS:
            print(f"sport inconnu : {c}")
            rc = 1
            continue
        r = FONCTIONS[c](ecrit=ecrit)
        if r.get("erreur"):
            print(f"  ! {r['erreur']}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
