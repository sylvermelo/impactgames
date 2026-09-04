"""
MOTEUR HOCKEY SUR GLACE (NHL) — Poisson bivarié attaques/défenses
============================================================================
Le hockey est un sport à score bas (≈ 6 buts par match) : comme au football,
une loi de Poisson convient, et on peut dériver TOUS les marchés d'une seule
matrice de scores.

Une spécificité que le football n'a pas, et qu'il ne faut surtout pas rater :
**le hockey n'admet pas de match nul au classement**, mais il en admet un au
bout des 60 minutes réglementaires. Il y a donc DEUX marchés distincts :

    · le 1X2 « temps réglementaire » (3 issues, dont le nul)
    · le « moneyline » prolongation et fusillade comprises (2 issues)

Le second se déduit du premier en répartissant la masse du nul selon la part
de victoires du domicile en prolongation — un paramètre mesuré, pas inventé.

Deuxième point critique : quand un match va en prolongation, l'API renvoie le
score FINAL, but décisif compris. Pour modéliser les buts réglementaires il
faut retirer ce but au vainqueur, sinon on surestime systématiquement les
attaques.

Source : `api.nhle.com/stats/rest/en/game` — API publique officielle, sans clé,
75 698 matchs au compteur au moment de l'écriture.
"""
from __future__ import annotations

import csv
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm, poisson

MAX_BUTS = 10                 # la matrice de scores va de 0 à 10 buts

# Part des matchs dépassant les 60 minutes que le DOMICILE finit par gagner
# (prolongation + fusillade confondues). Ordre de grandeur NHL : 53-55 %.
PART_DOMICILE_APRES_REGLEMENT = 0.545


# ============================================================== chargement
def charger_matchs(fichier: str | Path = "data/nhl_matchs.csv") -> list[dict]:
    """Lit le CSV produit par `sources.py`.

    Colonnes attendues : date, saison, domicile, exterieur, buts_dom, buts_ext,
    apres_reglement (0/1).
    """
    fichier = Path(fichier)
    if not fichier.exists():
        return []
    out = []
    with open(fichier, newline="", encoding="utf-8") as fh:
        for l in csv.DictReader(fh):
            try:
                hd, ha = int(l["buts_dom"]), int(l["buts_ext"])
            except (KeyError, ValueError):
                continue
            if l.get("domicile") == l.get("exterieur"):
                continue
            out.append({
                "date": l["date"],
                "saison": l.get("saison", ""),
                "domicile": l["domicile"],
                "exterieur": l["exterieur"],
                "buts_dom": hd,
                "buts_ext": ha,
                "apres_reglement": l.get("apres_reglement", "0") == "1",
            })
    out.sort(key=lambda m: m["date"])
    return out


def buts_reglementaires(m: dict) -> tuple[int, int]:
    """Retire le but décisif de prolongation/fusillade.

    Un match 4-3 en prolongation n'a pas produit 7 buts en 60 minutes : il en
    a produit 6 (3-3). Sans cette correction, les attaques sont surestimées
    sur tous les matchs serrés — c'est-à-dire sur un quart de la ligue.
    """
    hd, ha = m["buts_dom"], m["buts_ext"]
    if m["apres_reglement"] and hd != ha:
        if hd > ha:
            hd -= 1
        else:
            ha -= 1
    return max(hd, 0), max(ha, 0)


# ======================================================== modèle de Poisson
def correction_dixon_coles(x, y, lam, mu, rho):
    """Facteur τ de Dixon-Coles : les 0-0, 1-0, 0-1 et 1-1 sont plus fréquents
    que ne le prédit une Poisson indépendante. Ce sont exactement les scores
    qui décident du marché « prolongation ou pas » en hockey."""
    tau = np.ones_like(lam, dtype=float)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    tau[m00] = 1 - lam[m00] * mu[m00] * rho
    tau[m01] = 1 + lam[m01] * rho
    tau[m10] = 1 + mu[m10] * rho
    tau[m11] = 1 - rho
    return np.clip(tau, 1e-9, None)


def ajuster(matchs: list[dict], demi_vie_jours: float = 270.0,
            ridge: float = 0.08) -> dict:
    """Estime attaque, défense et avantage du domicile par maximum de
    vraisemblance pondéré.

    Paramétrage : log λ_dom = a_h + b_a + γ et log λ_ext = a_a + b_h, avec
    `a` = attaque, `b` = −défense. La contrainte moyenne(a) + moyenne(b) = 0
    lève l'indétermination (ajouter une constante à toutes les attaques et la
    retirer à toutes les défenses ne change rien) : sans elle, l'optimiseur
    divague.

    `demi_vie_jours` = 270 (≈ 9 mois) : un match de la saison dernière compte
    pour moitié. C'est le compromis NHL, où les effectifs bougent beaucoup
    (échanges, ballottage) mais moins qu'au football.

    Contrainte d'identifiabilité, et pourquoi une seule :

      · ajouter c à toutes les attaques et retirer c à toutes les défenses ne
        change AUCUNE probabilité — il faut donc ancrer quelque chose ;
      · pénaliser `moyenne(a) + moyenne(b)` (première version) ne sert à rien :
        cette somme est invariante sous exactement cette dérive ;
      · ancrer moyenne(a) = 0 **et** moyenne(b) = 0 (deuxième version) est
        pire : ça supprime le paramètre qui porte le NIVEAU de buts de la
        ligue (≈ 3 par équipe), que γ est alors forcé d'absorber. Résultat
        mesuré : γ = 1,12 au lieu de 0,25 — l'avantage du domicile était
        contaminé par le niveau général.

    La bonne contrainte est donc **moyenne(b) = 0, moyenne(a) libre** :
    moyenne(a) porte le niveau de buts (exp(moyenne(a)) ≈ 3), et γ redevient
    l'avantage du domicile pur.
    """
    if len(matchs) < 100:
        return {}
    equipes = sorted({m["domicile"] for m in matchs} | {m["exterieur"] for m in matchs})
    idx = {e: i for i, e in enumerate(equipes)}
    n = len(equipes)

    hi = np.array([idx[m["domicile"]] for m in matchs])
    aw = np.array([idx[m["exterieur"]] for m in matchs])
    hg = np.array([buts_reglementaires(m)[0] for m in matchs])
    ag = np.array([buts_reglementaires(m)[1] for m in matchs])

    aujourdhui = max(datetime.fromisoformat(m["date"]) for m in matchs)
    age = np.array([(aujourdhui - datetime.fromisoformat(m["date"])).days
                    for m in matchs], dtype=float)
    w = np.exp(-math.log(2.0) * age / demi_vie_jours)

    def moins_log_v(p):
        a, b = p[:n], p[n:2 * n]
        gam, rho = p[2 * n], math.tanh(p[2 * n + 1])
        lam = np.clip(np.exp(a[hi] + b[aw] + gam), 1e-6, 20)
        mu = np.clip(np.exp(a[aw] + b[hi]), 1e-6, 20)
        ll = poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu)
        ll = ll + np.log(correction_dixon_coles(hg, ag, lam, mu, rho))
        # identifiabilité + régularisation : une équipe promue n'a que quelques
        # matchs, sans pénalité le modèle lui invente une attaque délirante
        # `b` seul est ancré ; `a` reste libre de porter le niveau de la ligue.
        # La pénalité ridge s'applique aux ÉCARTS à la moyenne, pas au niveau,
        # sinon elle tire artificiellement le niveau de buts vers zéro.
        ecart_a = a - a.mean()
        pen = (1e4 * b.mean() ** 2
               + ridge * float(np.sum(ecart_a ** 2 + (b - b.mean()) ** 2)))
        return -float(np.sum(w * ll)) + pen

    p0 = np.zeros(2 * n + 2)
    res = minimize(moins_log_v, p0, method="L-BFGS-B",
                   options={"maxiter": 500, "maxfun": 20000, "ftol": 1e-11})
    p = res.x
    return {"attaque": p[:n], "defense": p[n:2 * n],
            "gamma": float(p[2 * n]), "rho": float(math.tanh(p[2 * n + 1])),
            "idx": idx, "equipes": equipes,
            "converge": bool(res.success), "n_matchs": len(matchs)}


def matrice_scores(modele: dict, dom: str, ext: str) -> np.ndarray:
    """Matrice P(buts_dom = i, buts_ext = j) au bout des 60 minutes."""
    idx, a, b = modele["idx"], modele["attaque"], modele["defense"]
    lam = float(np.clip(np.exp(a[idx[dom]] + b[idx[ext]] + modele["gamma"]), 1e-6, 20))
    mu = float(np.clip(np.exp(a[idx[ext]] + b[idx[dom]]), 1e-6, 20))
    rho = modele["rho"]
    k = np.arange(MAX_BUTS + 1)
    M = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
    M[0, 0] *= max(1 - lam * mu * rho, 1e-9)
    M[0, 1] *= max(1 + lam * rho, 1e-9)
    M[1, 0] *= max(1 + mu * rho, 1e-9)
    M[1, 1] *= max(1 - rho, 1e-9)
    M = np.clip(M, 0, None)
    return M / max(M.sum(), 1e-12)


# ================================================================== marchés
def marches(M: np.ndarray, part_dom: float = PART_DOMICILE_APRES_REGLEMENT) -> dict:
    """Dérive TOUS les marchés d'une seule matrice de scores.

    C'est le principe qui rend le modèle rentable à écrire : on ne construit
    pas un modèle par marché, on construit une matrice et on somme des zones.
    """
    n = M.shape[0]
    i = np.arange(n)
    total = np.add.outer(i, i)
    ecart = np.subtract.outer(i, i)

    p_1 = float(M[ecart > 0].sum())          # domicile gagne à 60 minutes
    p_x = float(M[ecart == 0].sum())         # prolongation
    p_2 = float(M[ecart < 0].sum())          # extérieur gagne à 60 minutes

    out = {
        "1": p_1, "X": p_x, "2": p_2,
        # moneyline, prolongation et fusillade comprises : la masse du nul est
        # répartie selon la part mesurée de victoires du domicile après 60 min
        "ml_dom": p_1 + p_x * part_dom,
        "ml_ext": p_2 + p_x * (1 - part_dom),
        "p_prolongation": p_x,
        "buts_attendus": float((M * total).sum()),
        "buts_dom_attendus": float((M * np.add.outer(i, np.zeros(n))).sum()),
        "buts_ext_attendus": float((M * np.add.outer(np.zeros(n), i)).sum()),
        "double_chance_1X": p_1 + p_x,
        "double_chance_12": p_1 + p_2,
        "double_chance_X2": p_x + p_2,
        "les_deux_marquent": float(M[1:, 1:].sum()),
        "blanchissage": float(M[0, :].sum() + M[:, 0].sum() - M[0, 0]),
    }
    for seuil in (3.5, 4.5, 5.5, 6.5, 7.5):
        out[f"O{seuil}"] = float(M[total > seuil].sum())
        out[f"U{seuil}"] = float(M[total < seuil].sum())
    for h in (0.5, 1.5, 2.5):
        out[f"handicap_dom_{h}"] = float(M[ecart > h].sum())
        out[f"handicap_ext_plus_{h}"] = float(M[ecart < h].sum())
    plat = [(f"{a}-{b}", float(M[a, b])) for a in range(7) for b in range(7)]
    out["scores_probables"] = sorted(plat, key=lambda z: -z[1])[:3]
    return out


def pronostic(modele: dict, dom: str, ext: str) -> dict:
    if dom not in modele["idx"] or ext not in modele["idx"]:
        return {"erreur": f"équipe inconnue : {dom if dom not in modele['idx'] else ext}"}
    return marches(matrice_scores(modele, dom, ext))


# ================================================================= classement
def classement(modele: dict) -> list[dict]:
    """Indice de force nette, en buts de différence par match.

    Attention au signe : dans la paramétrisation du modèle,
    `log λ_dom = a_h + b_a + γ`, donc `b` mesure la FAIBLESSE défensive de
    l'adversaire. La différence de buts attendue entre i et j vaut

        (a_i + b_j) − (a_j + b_i) = (a_i − b_i) − (a_j − b_j)

    La force nette est donc **a − b**, pas a + b. Écrire a + b — l'erreur
    qu'on a faite — inverse presque le classement : les tests mesuraient une
    corrélation de −0,32 avec la vérité au lieu de +0,9.
    """
    a, b, idx = modele["attaque"], modele["defense"], modele["idx"]
    rows = []
    for e in modele["equipes"]:
        i = idx[e]
        rows.append({"equipe": e,
                     "attaque": float(a[i]),
                     "faiblesse_defensive": float(b[i]),
                     "force": float(a[i] - b[i])})
    rows.sort(key=lambda r: -r["force"])
    for r in rows:
        r["rang"] = rows.index(r) + 1
    return rows
