"""
MOTEUR BASKET (NBA) — normales bivariées sur les points
============================================================================
Le basket est l'opposé du football : 220 points par match, pas de nul, et des
écarts qui suivent remarquablement bien une loi normale. Une loi de Poisson
serait ici une absurdité.

Le modèle décompose chaque match en deux grandeurs :

    T = points_dom + points_ext   (le « total », piloté par le RYTHME)
    D = points_dom − points_ext   (l'« écart », piloté par la FORCE RELATIVE)

et leur donne à chaque équipe deux notes :

    o_i = rendement offensif (points marqués au-dessus de la moyenne)
    d_i = rendement défensif (points encaissés au-dessus de la moyenne)

D'où, par simple algèbre :

    D = (o_h + d_h) − (o_a + d_a) + avantage_domicile     ← la FORCE NETTE
    T = 2·moyenne + (o_h − d_h) + (o_a − d_a) + avantage_domicile   ← le RYTHME

C'est le point le plus utile du modèle : **la force nette décide du vainqueur
et du handicap, le rythme décide du total**. Une équipe peut être très forte
et jouer lentement (peu de points, écarts nets) — les deux marchés sont
indépendants, ce qu'un modèle à une seule note ne peut pas exprimer.

T et D étant corrélés (un match rapide produit à la fois plus de points et,
souvent, un écart plus large), on estime explicitement leur corrélation.

Source : endpoints publics de `stats.nba.com`, sans clé API.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import norm

AVANTAGE_DOMICILE_DEFAUT = 2.6     # points, ordre de grandeur NBA moderne

# Part des prolongations gagnées par le domicile. Environ 6 % des matchs NBA
# finissent à égalité après 48 minutes : il faut savoir quoi faire de cette
# masse, sinon les deux côtés du moneyline ne somment pas à 1.
PART_DOMICILE_PROLONGATION = 0.535


# ============================================================== chargement
def charger_matchs(fichier: str | Path = "data/nba_matchs.csv") -> list[dict]:
    """Lit le CSV produit par `sources.py`.

    Colonnes : date, saison, domicile, exterieur, pts_dom, pts_ext.
    """
    fichier = Path(fichier)
    if not fichier.exists():
        return []
    out = []
    vu = set()
    with open(fichier, newline="", encoding="utf-8") as fh:
        for l in csv.DictReader(fh):
            try:
                pd_, pa = int(l["pts_dom"]), int(l["pts_ext"])
            except (KeyError, ValueError):
                continue
            dom, ext = l.get("domicile"), l.get("exterieur")
            if not dom or not ext or dom == ext:
                continue
            cle = (l["date"], dom, ext)
            if cle in vu:                      # l'API renvoie parfois des doublons
                continue
            vu.add(cle)
            out.append({"date": l["date"], "saison": l.get("saison", ""),
                        "domicile": dom, "exterieur": ext,
                        "pts_dom": pd_, "pts_ext": pa})
    out.sort(key=lambda m: m["date"])
    return out


# ================================================================== estimation
def ajuster(matchs: list[dict], demi_vie_jours: float = 400.0,
            ridge: float = 3.0) -> dict:
    """Deux moindres carrés pondérés (un pour la force nette, un pour le
    rythme), résolus en une seule fois par numpy.

    Pourquoi des moindres carrés plutôt qu'un maximum de vraisemblance complet ?
    Parce que la cible est gaussienne : les deux coïncident exactement, et la
    solution est alors en forme close — pas d'optimiseur à faire diverger.

    `demi_vie_jours` = 400 : la NBA tourne beaucoup (échanges, blessures,
    « load management »), mais sur 82 matchs une équipe reste reconnaissable
    d'une saison à l'autre.
    """
    if len(matchs) < 150:
        return {}
    equipes = sorted({m["domicile"] for m in matchs} | {m["exterieur"] for m in matchs})
    idx = {e: i for i, e in enumerate(equipes)}
    n = len(equipes)

    hi = np.array([idx[m["domicile"]] for m in matchs])
    aw = np.array([idx[m["exterieur"]] for m in matchs])
    T = np.array([m["pts_dom"] + m["pts_ext"] for m in matchs], dtype=float)
    D = np.array([m["pts_dom"] - m["pts_ext"] for m in matchs], dtype=float)

    aujourdhui = max(datetime.fromisoformat(m["date"]) for m in matchs)
    age = np.array([(aujourdhui - datetime.fromisoformat(m["date"])).days
                    for m in matchs], dtype=float)
    w = np.exp(-math.log(2.0) * age / demi_vie_jours)

    # --- force nette : D = 1·net_h − 1·net_a + hfa
    X_d = np.zeros((len(matchs), n + 1))
    X_d[np.arange(len(matchs)), hi] = 1.0
    X_d[np.arange(len(matchs)), aw] = -1.0
    X_d[:, n] = 1.0                                   # avantage du domicile
    net, hfa_d, res_d = _wls(X_d, D, w, ridge, contrainte_somme=True)

    # --- rythme : T = 1·ryt_h + 1·ryt_a + (2·moyenne + hfa)
    X_t = np.zeros((len(matchs), n + 1))
    X_t[np.arange(len(matchs)), hi] = 1.0
    X_t[np.arange(len(matchs)), aw] = 1.0
    X_t[:, n] = 1.0                                   # ordonnée à l'origine globale
    ryt, base_t, res_t = _wls(X_t, T, w, ridge, contrainte_somme=True)

    sigma_t = float(np.sqrt(np.average(res_t ** 2, weights=w)))
    sigma_d = float(np.sqrt(np.average(res_d ** 2, weights=w)))
    # corrélation des résidus : un match rapide produit des écarts plus larges
    corr = float(np.average(res_t * res_d, weights=w) / max(sigma_t * sigma_d, 1e-9))

    return {"net": net, "rythme": ryt, "idx": idx, "equipes": equipes,
            "hfa": float(hfa_d), "base_total": float(base_t),
            "sigma_total": sigma_t, "sigma_ecart": sigma_d,
            "correlation": float(np.clip(corr, -0.9, 0.9)),
            "n_matchs": len(matchs)}


def _wls(X, y, w, ridge, contrainte_somme=True):
    """Moindres carrés pondérés avec régularisation ridge.

    La dernière colonne (intercept) n'est JAMAIS pénalisée : la ridge doit
    ramener les notes d'équipes vers zéro, pas l'avantage du domicile.
    """
    k = X.shape[1]
    W = w[:, None]
    pen = ridge * np.eye(k)
    pen[k - 1, k - 1] = 0.0
    if contrainte_somme:
        # les notes d'équipes doivent sommer à zéro, sinon « moyenne de la
        # ligue » et « note moyenne des équipes » se confondent
        c = np.zeros(k)
        c[:k - 1] = 1.0
        pen += 1e4 * np.outer(c, c)
    beta = np.linalg.solve(X.T @ (W * X) + pen, X.T @ (w * y))
    residus = y - X @ beta
    return beta[:k - 1], float(beta[k - 1]), residus


# ================================================================== marchés
def parametrer(modele: dict, dom: str, ext: str) -> dict:
    """Moyennes et écarts-types du total et de l'écart pour une rencontre."""
    if dom not in modele["idx"] or ext not in modele["idx"]:
        return {"erreur": f"équipe inconnue : {dom if dom not in modele['idx'] else ext}"}
    i, j = modele["idx"][dom], modele["idx"][ext]
    mu_d = modele["net"][i] - modele["net"][j] + modele["hfa"]
    mu_t = modele["base_total"] + modele["rythme"][i] + modele["rythme"][j]
    return {"mu_total": float(mu_t), "mu_ecart": float(mu_d),
            "sigma_total": modele["sigma_total"],
            "sigma_ecart": modele["sigma_ecart"],
            "correlation": modele["correlation"]}


def marches(p: dict, part_dom_prolongation: float = PART_DOMICILE_PROLONGATION) -> dict:
    """Vainqueur, handicap et total, à partir de deux normales.

    Deux subtilités qu'il ne faut pas rater :

    1. **Correction de continuité sur le moneyline, pas sur les handicaps.**
       L'écart est un ENTIER. « Le domicile gagne » veut dire écart ≥ 1, donc
       P(normale > 0,5) : le 0,5 est nécessaire. En revanche un handicap à
       6,5 n'a jamais de mise remboursée : « dom −6,5 » veut dire écart ≥ 7,
       soit P(normale > 6,5) tel quel. Remettre un 0,5 ici — l'erreur qu'on a
       faite — décale tous les handicaps d'un demi-point.

    2. **L'égalité à 48 minutes.** Environ 6 % des matchs vont en
       prolongation. Cette masse doit être répartie entre les deux équipes,
       sinon dom_gagne + ext_gagne ≠ 1.
    """
    if "erreur" in p:
        return p
    mt, md = p["mu_total"], p["mu_ecart"]
    st, sd = p["sigma_total"], p["sigma_ecart"]

    p_dom_sup = float(norm.sf((0.5 - md) / sd))           # écart ≥ 1
    p_ext_sup = float(norm.cdf((-0.5 - md) / sd))         # écart ≤ −1
    p_egal = float(norm.cdf((0.5 - md) / sd) - norm.cdf((-0.5 - md) / sd))

    out = {
        "dom_gagne": p_dom_sup + p_egal * part_dom_prolongation,
        "ext_gagne": p_ext_sup + p_egal * (1 - part_dom_prolongation),
        "p_prolongation": p_egal,
        "total_attendu": mt,
        "ecart_attendu": md,
    }
    for ligne in (205.5, 215.5, 220.5, 225.5, 230.5, 240.5):
        out[f"O{ligne}"] = float(norm.sf((ligne - mt) / st))
        out[f"U{ligne}"] = float(norm.cdf((ligne - mt) / st))
    for h in (2.5, 4.5, 6.5, 8.5, 10.5, 12.5):
        out[f"dom_moins_{h}"] = float(norm.sf((h - md) / sd))
        out[f"ext_plus_{h}"] = float(norm.cdf((h - md) / sd))
    # écart exact le plus probable (pour l'affichage)
    entiers = np.arange(-30, 31)
    dens = norm.pdf((entiers - md) / sd)
    out["ecart_le_plus_probable"] = int(entiers[np.argmax(dens)])
    return out


def pronostic(modele: dict, dom: str, ext: str) -> dict:
    return marches(parametrer(modele, dom, ext))


# ================================================================= classement
def classement(modele: dict) -> list[dict]:
    rows = [{"equipe": e,
             "force_nette": float(modele["net"][modele["idx"][e]]),
             "rythme": float(modele["rythme"][modele["idx"][e]])}
            for e in modele["equipes"]]
    rows.sort(key=lambda r: -r["force_nette"])
    for k, r in enumerate(rows, 1):
        r["rang"] = k
    return rows
