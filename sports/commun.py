"""
Brique commune aux trois moteurs (tennis, hockey, basket).
============================================================================
Tout ce qui est identique quel que soit le sport vit ici : les métriques de
qualité (log-loss, RPS, calibration), le déviggage des cotes, les poids de
décroissance temporelle et la régularisation ridge.

Principe non négociable : ce module ne contient AUCUNE donnée et AUCUNE
hypothèse métier. Il est testable isolément.
"""
from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------- métriques


def log_loss(probas: np.ndarray, resultats: np.ndarray) -> float:
    """Pénalité logarithmique moyenne. Plus basse = meilleures probabilités.

    probas    : matrice (n_matchs, n_issues), lignes normalisées à 1
    resultats : indice de l'issue réellement survenue, par match
    """
    probas = np.asarray(probas, dtype=float)
    resultats = np.asarray(resultats, dtype=int)
    n = len(resultats)
    if n == 0:
        return float("nan")
    # normalisation défensive : une ligne peut ne pas sommer à 1 après troncature
    probas = probas / np.clip(probas.sum(axis=1, keepdims=True), 1e-12, None)
    prises = probas[np.arange(n), resultats]
    return float(-np.mean(np.log(np.clip(prises, 1e-9, 1.0))))


def rps(probas: np.ndarray, resultats: np.ndarray) -> float:
    """Ranked Probability Score — adapté aux issues ORDONNÉES (1X2, écart).

    Contrairement à la log-loss, il ne punit pas de la même façon « j'ai dit
    victoire domicile alors que c'était nul » et « j'ai dit victoire domicile
    alors que c'était victoire extérieur ».
    """
    probas = np.asarray(probas, dtype=float)
    resultats = np.asarray(resultats, dtype=int)
    probas = probas / np.clip(probas.sum(axis=1, keepdims=True), 1e-12, None)
    cum_p = np.cumsum(probas, axis=1)
    cum_o = np.cumsum(np.eye(probas.shape[1])[resultats], axis=1)
    return float(np.mean(np.mean((cum_p - cum_o) ** 2, axis=1)))


def brier(probas: np.ndarray, resultats: np.ndarray) -> float:
    """Score de Brier : distance quadratique moyenne aux issues réalisées."""
    probas = np.asarray(probas, dtype=float)
    probas = probas / np.clip(probas.sum(axis=1, keepdims=True), 1e-12, None)
    reel = np.eye(probas.shape[1])[np.asarray(resultats, dtype=int)]
    return float(np.mean(np.sum((probas - reel) ** 2, axis=1)))


def calibration(probas: np.ndarray, resultats: np.ndarray,
                bornes=((0.0, 0.25), (0.25, 0.40), (0.40, 0.55),
                        (0.55, 0.70), (0.70, 1.01))):
    """« Quand je dis 70 %, ça arrive-t-il 70 % du temps ? »

    Renvoie une liste de dicts : tranche, effectif, probabilité moyenne prédite,
    taux réel observé, écart. Les tranches de moins de 30 observations sont
    écartées : en dessous, l'écart observé ne veut rien dire.
    """
    probas = np.asarray(probas, dtype=float).ravel()
    resultats = np.asarray(resultats, dtype=int).ravel()
    out = []
    for a, b in bornes:
        masque = (probas >= a) & (probas < b)
        if masque.sum() < 30:
            continue
        p, r = probas[masque], resultats[masque]
        out.append({"de": a, "a": min(b, 1.0), "n": int(masque.sum()),
                    "predite": float(p.mean()), "reel": float(r.mean()),
                    "ecart": float(r.mean() - p.mean())})
    return out


# ------------------------------------------------------------------------ cotes


def devig(*cotes) -> np.ndarray:
    """Retire la marge du bookmaker d'un jeu de cotes pour retrouver ses
    probabilités implicites.

    Les cotes d'un bookmaker somment toujours à plus de 100 % (sa marge).
    La méthode proportionnelle répartit cette marge uniformément : c'est la
    plus simple et, sur des marchés liquides, la plus proche de la vérité.

    Renvoie un tableau de NaN si une cote manque ou est absurde : on préfère
    écarter le match plutôt que de comparer le modèle à du bruit.
    """
    propres = []
    for c in cotes:
        try:
            v = float(c)
        except (TypeError, ValueError):
            return np.full(len(cotes), np.nan)
        if not np.isfinite(v) or v <= 1.01:
            return np.full(len(cotes), np.nan)
        propres.append(v)
    if len(propres) < 2:
        return np.full(len(cotes), np.nan)
    inverses = np.array([1.0 / v for v in propres])
    return inverses / inverses.sum()


def clv(proba_modele: float, cote: float) -> float:
    """Closing Line Value : > 0 signifie qu'on a trouvé un pari rentable.

    Un pari à la cote `cote` avec une probabilité réelle `proba_modele` vaut
    en espérance `proba_modele * (cote - 1) - (1 - proba_modele)`.
    """
    return float(proba_modele * (float(cote) - 1.0) - (1.0 - proba_modele))


def bilan_mise_a_plat(probas: np.ndarray, cotes: np.ndarray,
                      resultats: np.ndarray, edge_min: float):
    """Simule une mise à plat sur chaque issue dont notre probabilité dépasse
    la probabilité implicite de la cote de `edge_min`.

    Renvoie un dict {nb_paris, reussite, pnl_unites, roi}.
    """
    probas = np.asarray(probas, dtype=float)
    resultats = np.asarray(resultats, dtype=int)
    nb = gagnes = 0
    pnl = 0.0
    for i in range(len(resultats)):
        for j in range(probas.shape[1]):
            c = cotes[i, j]
            if not np.isfinite(c) or c <= 1.01:
                continue
            implicite = 1.0 / c
            if probas[i, j] > implicite * (1.0 + edge_min):
                nb += 1
                pnl += (c - 1.0) if resultats[i] == j else -1.0
                gagnes += int(resultats[i] == j)
    return {"nb_paris": nb,
            "reussite": (gagnes / nb) if nb else float("nan"),
            "pnl_unites": pnl,
            "roi": (pnl / nb) if nb else float("nan")}


# ------------------------------------------------------------------ pondération


def poids_decay(jours: np.ndarray, demi_vie_jours: float) -> np.ndarray:
    """Poids exponentiel : un match vieux d'une demi-vie compte pour moitié.

    C'est LE paramètre qui fait la différence entre un modèle qui prédit la
    saison dernière et un modèle qui prédit le match de demain.
    """
    jours = np.asarray(jours, dtype=float)
    if demi_vie_jours <= 0:
        return np.ones_like(jours)
    return np.exp(-np.log(2.0) * jours / demi_vie_jours)


def normaliser_lignes(M: np.ndarray) -> np.ndarray:
    """Renormalise une matrice de probabilités pour qu'elle somme à 1."""
    M = np.clip(np.asarray(M, dtype=float), 0.0, None)
    total = M.sum()
    return M / total if total > 1e-12 else np.full_like(M, 1.0 / M.size)
