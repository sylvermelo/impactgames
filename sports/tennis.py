"""
MOTEUR TENNIS (ATP) — Elo par surface + chaîne de Markov jeu → set → match
============================================================================
Contrairement au football, le tennis n'a pas de « score » modélisable par une
loi de Poisson : c'est un empilement de points → jeux → sets → match. La bonne
approche est donc une **chaîne de Markov** qui remonte cette hiérarchie.

Le modèle tient en UN SEUL paramètre ajusté sur les données réelles (`beta`,
la sensibilité du gain de point à l'écart de classement). Tout le reste en
découle de façon cohérente :

    écart Elo  →  probabilité de gagner un point (service / retour)
               →  probabilité de gagner un jeu      (Markov)
               →  probabilité de gagner un set      (Markov)
               →  probabilité de gagner le match    (Markov)
               →  score exact en sets, total de jeux, handicap

L'avantage décisif : **un seul modèle, tous les marchés**, exactement comme la
matrice de scores du football. Et le format 5 sets (Grand Chelem) amplifie
automatiquement l'écart entre les deux joueurs — pas besoin d'une règle.

Source de données : dépôt GitHub `Kadantte/tennis_atp`, fork de la base de
Jeff Sackmann (le dépôt original a disparu de GitHub en 2026).
"""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path

import numpy as np

TAILLE_DP = 131              # cases de la DP : la valeur 0 est à l'indice 65,
                             # donc ±65 autour. Un 5 sets plafonne à 65 jeux
                             # (5 × 7-6) et l'écart maximal vaut aussi 65.

# ------------------------------------------------------------------ surfaces
# Probabilités de base de gagner UN POINT, à niveau égal, selon la surface.
# Ordres de grandeur observés sur le circuit ATP moderne : le service pèse
# beaucoup plus sur gazon que sur terre battue.
BASE_SERVICE = {"Hard": 0.640, "Clay": 0.615, "Grass": 0.668, "Carpet": 0.655}
BASE_RETOUR = {k: 1.0 - v for k, v in BASE_SERVICE.items()}

# Poids d'importance du match pour le pas d'apprentissage Elo.
POIDS_NIVEAU = {"G": 1.35,    # Grand Chelem
                "M": 1.15,    # Masters 1000
                "F": 1.20,    # ATP Finals
                "A": 1.00,    # ATP 250 / 500
                "D": 0.00,    # Davis Cup : écartée (format par équipe, surface variable)
                "O": 0.00}    # Jeux olympiques : écartée (hors classement)
NIVEAUX_CONSERVES = {"G", "M", "A", "F"}

K_ELO = 24.0
ELO_INITIAL = 1500.0


# =============================================================== chargement
def charger_matchs(dossier: str | Path = "data",
                   annees: range | None = None) -> list[dict]:
    """Lit les fichiers `atp_matches_AAAA.csv` et renvoie une liste de dicts
    triés chronologiquement.

    On conserve : identifiants, surface, niveau, date, format (best_of) et le
    score en sets — c'est tout ce dont le moteur a besoin.
    """
    dossier = Path(dossier)
    if annees is None:
        fichiers = sorted(dossier.glob("atp_matches_[0-9][0-9][0-9][0-9].csv"))
    else:
        fichiers = [dossier / f"atp_matches_{a}.csv" for a in annees]

    matchs = []
    for f in fichiers:
        if not f.exists():
            continue
        annee = int(f.stem[-4:])
        with open(f, newline="", encoding="utf-8") as fh:
            for ligne in csv.DictReader(fh):
                m = _nettoyer(ligne, annee)
                if m is not None:
                    matchs.append(m)
    matchs.sort(key=lambda m: (m["date"], m["match_num"]))
    return matchs


def _nettoyer(l: dict, annee: int) -> dict | None:
    """Renvoie None si la ligne est inexploitable."""
    if l.get("tourney_level") not in NIVEAUX_CONSERVES:
        return None
    w, lo = l.get("winner_id"), l.get("loser_id")
    if not w or not lo or w == lo:
        return None
    surface = (l.get("surface") or "").strip()
    if surface not in BASE_SERVICE:
        return None
    sets = _lire_score(l.get("score", ""))
    if not sets:
        return None
    try:
        best_of = int(float(l.get("best_of") or 3))
    except ValueError:
        best_of = 3
    try:
        date = str(l.get("tourney_date") or "")
        date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    except Exception:
        return None
    return {
        "date": date,
        "annee": annee,
        "match_num": int(l.get("match_num") or 0),
        "tourney_id": l.get("tourney_id", ""),
        "tourney": l.get("tourney_name", ""),
        "surface": surface,
        "niveau": l.get("tourney_level"),
        "round": l.get("round", ""),
        "best_of": 5 if best_of >= 5 else 3,
        "joueur_a": w,                     # A = vainqueur réel
        "joueur_b": lo,                    # B = perdant réel
        "nom_a": l.get("winner_name", ""),
        "nom_b": l.get("loser_name", ""),
        "sets": sets,                      # [(jeux_a, jeux_b), ...] réordonnés
        # `sets_bruts` conserve le sens d'écriture : c'est lui qui dit QUI a
        # gagné chaque set, donc le score en sets (2-1 et non 3-0).
        "sets_bruts": _lire_score_brut(l.get("score", "")),
        "pays_a": l.get("winner_ioc", ""),
        "pays_b": l.get("loser_ioc", ""),
    }


def _lire_score_brut(txt: str) -> list[tuple[int, int]]:
    """Comme `_lire_score`, mais SANS réordonner.

    Dans la base Sackmann le score est écrit du point de vue du vainqueur du
    match : `6-7(5) 6-4 6-3` signifie qu'il a PERDU le premier set. Cette
    information est indispensable pour connaître le score en sets (2-1 et non
    3-0) et donc pour ajuster `beta` sur des données réelles.
    """
    out = []
    for bloc in str(txt).split():
        base = bloc.split("(")[0]
        if "-" not in base:
            continue
        a, _, b = base.partition("-")
        try:
            out.append((int(a), int(b)))
        except ValueError:
            continue
    return out


def _lire_score(txt: str) -> list[tuple[int, int]]:
    """`'7-6(5) 6-4'` → [(7,6),(6,4)] en ramenant tout du côté du vainqueur.

    Les sets peuvent être écrits à l'envers (`6-7(5)` quand le vainqueur du
    match a perdu ce set) : on remet systématiquement le plus grand devant.
    """
    sets = []
    for bloc in str(txt).split():
        base = bloc.split("(")[0]
        if "-" not in base:
            continue
        a, _, b = base.partition("-")
        try:
            x, y = int(a), int(b)
        except ValueError:
            continue
        if x == y:
            continue
        sets.append((max(x, y), min(x, y)))
    return sets


# ==================================================================== Elo
def entrainer_elo(matchs: list[dict], k: float = K_ELO) -> dict:
    """Parcourt les matchs dans l'ordre et met à jour deux classements :

    · `global`  — le niveau général du joueur
    · `surface` — un classement PAR SURFACE, initialisé sur le classement
      global puis ramené vers lui : un joueur sans historique sur gazon part
      de son niveau général plutôt que de zéro (régularisation).

    Renvoie aussi l'historique des classements **avant** chaque match : c'est
    ce qui garantit l'absence de fuite de données dans le backtest.
    """
    elo_g: dict[str, float] = {}
    elo_s: dict[tuple[str, str], float] = {}
    historique = []

    for m in matchs:
        a, b, surf = m["joueur_a"], m["joueur_b"], m["surface"]
        ra = elo_s.get((a, surf), elo_g.get(a, ELO_INITIAL))
        rb = elo_s.get((b, surf), elo_g.get(b, ELO_INITIAL))
        historique.append((ra, rb))

        poids = POIDS_NIVEAU.get(m["niveau"], 1.0)
        if poids <= 0:
            continue
        attendue = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        delta = k * poids * (1.0 - attendue)        # a a gagné → a progresse
        elo_g[a] = elo_g.get(a, ELO_INITIAL) + delta
        elo_g[b] = elo_g.get(b, ELO_INITIAL) - delta
        elo_s[(a, surf)] = ra + delta
        elo_s[(b, surf)] = rb - delta

    return {"elo_surface": elo_s, "elo_global": elo_g, "avant": historique}


# ================================================== chaîne de Markov (jeu/set)
def distribution_set(p_serv: float, p_ret: float, p_tb: float) -> list[tuple]:
    """Distribution du score en jeux d'UN set.

    Renvoie une liste de `(vainqueur, jeux_vainqueur, jeux_perdant, proba)`
    où `vainqueur` vaut 0 pour le joueur A et 1 pour le joueur B.

    Le serveur alterne à chaque jeu, A servant en premier. À 6-6, le
    tie-break est joué en un bloc avec la probabilité `p_tb`.
    """
    etats: dict[tuple[int, int], float] = {(0, 0): 1.0}
    sort: list[tuple[int, int, int, float]] = []

    for _ in range(13):                       # 12 jeux max avant le tie-break
        if not etats:
            break
        suivant: dict[tuple[int, int], float] = {}
        for (ja, jb), p in etats.items():
            if (ja, jb) == (6, 6):
                suivant[(6, 6)] = suivant.get((6, 6), 0.0) + p
                continue
            p_a = p_serv if (ja + jb) % 2 == 0 else p_ret
            for gagne_a, prob in ((True, p_a), (False, 1.0 - p_a)):
                na, nb = (ja + 1, jb) if gagne_a else (ja, jb + 1)
                if max(na, nb) >= 6 and abs(na - nb) >= 2:
                    v, jv, jp = (0, na, nb) if gagne_a else (1, nb, na)
                    sort.append((v, jv, jp, p * prob))
                else:
                    suivant[(na, nb)] = suivant.get((na, nb), 0.0) + p * prob
        etats = suivant

    p_66 = etats.get((6, 6), 0.0)             # tie-break : 7-6, donc 13 jeux
    if p_66 > 0:
        sort.append((0, 7, 6, p_66 * p_tb))
        sort.append((1, 7, 6, p_66 * (1.0 - p_tb)))

    # regrouper les doublons (même score, même vainqueur)
    fusion: dict[tuple, float] = {}
    for v, jv, jp, p in sort:
        fusion[(v, jv, jp)] = fusion.get((v, jv, jp), 0.0) + p
    return [(v, jv, jp, p) for (v, jv, jp), p in fusion.items() if p > 1e-12]


def dp_match(entrees: list[tuple], sets_gagnants: int, taille: int,
             mode: str) -> np.ndarray:
    """Programme dynamique sur les sets : remonte la distribution demandée.

    `mode="total"` → distribution du nombre TOTAL de jeux du match
    `mode="ecart"`  → distribution de l'ÉCART de jeux (A − B)

    Les deux se calculent par convolution successive de la distribution d'un
    set, sur les 3 ou 5 sets possibles. C'est exact à l'hypothèse près que les
    sets sont indépendants à probabilités de service constantes.

    Convention d'indexation : la case `OFFSET` représente la valeur 0, ce qui
    permet de stocker des écarts négatifs. Deux distributions centrées se
    convoluent en une distribution décalée de 2×OFFSET : on re-tranche donc
    `[OFFSET : OFFSET+taille]` après CHAQUE convolution, sinon tout part hors
    du tableau et le résultat s'effondre à zéro.
    """
    offset = taille // 2
    unitaire = np.zeros(taille)
    unitaire[offset] = 1.0
    etats = {(0, 0): unitaire}
    termine = np.zeros(taille)

    for _ in range(2 * sets_gagnants - 1):
        suivant: dict[tuple, np.ndarray] = {}
        for (sa, sb), arr in etats.items():
            if sa == sets_gagnants or sb == sets_gagnants:
                termine = termine + arr
                continue
            for v, jv, jp, p in entrees:
                if p <= 0:
                    continue
                if mode == "total":
                    val = jv + jp
                else:
                    val = (jv - jp) if v == 0 else (jp - jv)
                pos = offset + val
                if pos < 0 or pos >= taille:
                    continue
                piece = np.zeros(taille)
                piece[pos] = p
                conv = np.convolve(arr, piece)[offset:offset + taille]
                cle = (sa + (1 if v == 0 else 0), sb + (1 if v == 1 else 0))
                suivant[cle] = conv if cle not in suivant else suivant[cle] + conv
        etats = suivant
        if not etats:
            break
    for arr in etats.values():
        termine = termine + arr
    return termine


def scores_en_sets(entrees: list[tuple], sets_gagnants: int) -> dict[str, float]:
    """Probabilité de chaque score final en sets (`2-0`, `2-1`, `1-2`, `0-2`…)."""
    etats = {(0, 0): 1.0}
    out: dict[str, float] = {}
    for _ in range(2 * sets_gagnants - 1):
        suivant: dict[tuple, float] = {}
        for (sa, sb), p in etats.items():
            if sa == sets_gagnants or sb == sets_gagnants:
                out[f"{sa}-{sb}"] = out.get(f"{sa}-{sb}", 0.0) + p
                continue
            for v, _jv, _jp, ps in entrees:
                cle = (sa + (1 if v == 0 else 0), sb + (1 if v == 1 else 0))
                suivant[cle] = suivant.get(cle, 0.0) + p * ps
        etats = suivant
        if not etats:
            break
    for (sa, sb), p in etats.items():
        out[f"{sa}-{sb}"] = out.get(f"{sa}-{sb}", 0.0) + p
    return out


# ============================================================ probabilités
def points_depuis_elo(d: float, surface: str, beta: float) -> tuple[float, float, float]:
    """Écart Elo normalisé → probabilités de gain de point + tie-break.

    `d` = (Elo_A − Elo_B) / 400.  `beta` est l'unique paramètre ajusté : il
    dit de combien de points de pourcentage un écart de 400 points Elo
    déplace la probabilité de gagner un point.
    """
    bs = BASE_SERVICE.get(surface, 0.640)
    br = BASE_RETOUR.get(surface, 0.360)
    p_serv = min(max(bs + beta * d, 0.42), 0.88)
    p_ret = min(max(br + beta * d, 0.12), 0.58)
    p_tb = min(max(0.5 + 0.6 * (p_serv + p_ret - 1.0), 0.05), 0.95)
    return p_serv, p_ret, p_tb


_CACHE: dict[tuple, list[tuple]] = {}


def distribution_set_cachee(p_serv: float, p_ret: float,
                            p_tb: float) -> list[tuple]:
    """Mémoïse la DP de set : quantifiée au millième, elle ne prend que
    quelques centaines de valeurs distinctes sur toute une base de matchs."""
    cle = (round(p_serv, 3), round(p_ret, 3), round(p_tb, 3))
    if cle not in _CACHE:
        _CACHE[cle] = distribution_set(*cle)
    return _CACHE[cle]


# ============================================================ ajustement
def _logistique(d: float, decalage: float, echelle: float) -> float:
    """P(A gagne) = 1 / (1 + 10^(-(d - decalage) / echelle)).

    `d` = (Elo_A − Elo_B) / 400.  `echelle` dit à quelle vitesse l'écart se
    transforme en probabilité ; `decalage` absorbe un éventuel biais
    systématique du plateau.
    """
    return 1.0 / (1.0 + 10.0 ** (-(d - decalage) / echelle))


def ajuster_logistique(matchs: list[dict], elo: dict,
                       grille=None) -> dict:
    """Ajuste, PAR SURFACE ET PAR FORMAT, l'échelle de la logistique par
    maximum de vraisemblance. Les clés du résultat sont des tuples
    `(surface, best_of)`.

    Pourquoi ne pas laisser la chaîne de Markov décider seule ? Parce qu'on l'a
    mesuré : sur 1 310 matchs de contrôle (2026), la chaîne donnait une
    log-loss de 0,6372 contre 0,6268 à la logistique. Sa courbe est trop
    raide — le circuit ATP est plus imprévisible qu'un modèle génératif de
    points ne le suppose (abandons, méforme, enjeu variable).

    On garde donc le meilleur des deux :
      · la **logistique** décide de la probabilité de gagner le match ;
      · la **chaîne de Markov** est ré-inversée pour produire des sets, des
        totaux de jeux et des handicaps COHÉRENTS avec cette probabilité.

    Ajuster par `(surface, best_of)` n'est pas un raffinement cosmétique :
    c'est ce qui restitue l'effet Grand Chelem. En 5 sets le favori gagne
    réellement plus souvent qu'en 3 sets, et l'échelle ajustée le montre au
    lieu de le supposer.
    """
    if grille is None:
        grille = [round(0.30 + 0.02 * i, 2) for i in range(111)]  # 0.30 → 2.50
    avant = elo["avant"]
    derniere = max(m["annee"] for m in matchs)

    par_groupe: dict[tuple, list[float]] = {}
    controle: dict[tuple, list[float]] = {}
    for i, m in enumerate(matchs):
        ra, rb = avant[i]
        d = (ra - rb) / 400.0
        cle = (m["surface"], m["best_of"])
        cible = par_groupe if m["annee"] < derniere else controle
        cible.setdefault(cle, []).append(d)          # A a toujours gagné

    # groupes trop petits : on les rattache au même format, toutes surfaces
    def _repli(cle):
        if cle in par_groupe and len(par_groupe[cle]) >= 400:
            return cle
        meme_format = [c for c in par_groupe if c[1] == cle[1]]
        return max(meme_format, key=lambda c: len(par_groupe[c])) if meme_format else cle

    out = {}
    for cle, echant in par_groupe.items():
        test = controle.get(cle, [])
        scores = []
        for ech in grille:
            ll = -sum(math.log(min(max(_logistique(d, 0.0, ech), 1e-9), 1 - 1e-9))
                      for d in echant) / len(echant)
            scores.append((ll, ech))
        scores.sort()
        meilleur = scores[0][1]
        out[f"{cle[0]}|{cle[1]}"] = {
            "surface": cle[0], "best_of": cle[1],
            "echelle": meilleur,
            "decalage": 0.0,
            "logloss_ajustement": scores[0][0],
            "n_ajustement": len(echant),
            "logloss_controle": (-sum(math.log(min(max(_logistique(d, 0.0, meilleur),
                                                        1e-9), 1 - 1e-9))
                                      for d in test) / len(test)) if test else None,
            "n_controle": len(test),
        }
    return out


def score_reel_en_sets(m: dict) -> str | None:
    """Score en sets du point de vue de A (le vainqueur réel), ex. `'2-1'`."""
    bruts = m.get("sets_bruts") or []
    cible = (m["best_of"] + 1) // 2
    if not (cible <= len(bruts) <= 2 * cible - 1):
        return None                      # abandon, score tronqué → on écarte
    sa = sum(1 for x, y in bruts if x > y)
    if sa != cible:
        # le « vainqueur » n'a pas gagné le nombre de sets requis : abandon,
        # forfait ou score mal écrit. On écarte plutôt que d'ajuster sur du bruit.
        return None
    return f"{sa}-{len(bruts) - sa}"


def ajuster_beta(matchs: list[dict], elo: dict, params: dict,
                 grille=None) -> dict:
    """Ajuste `beta` sur les SCORES EN SETS observés.

    `beta` ne décide plus du vainqueur (c'est la logistique calibrée qui s'en
    charge) : il fixe la forme du match — à quelle vitesse les sets se
    déroulent. Un `beta` élevé donne des services dominateurs, donc beaucoup
    de 2-0 et des matchs courts ; un `beta` faible donne l'inverse. Le bon
    critère est donc la log-loss sur le score en sets réellement observé.
    """
    if grille is None:
        grille = [round(0.06 + 0.005 * i, 3) for i in range(69)]   # 0.06 → 0.40

    # les classements « avant match » sont alignés sur l'indice dans `matchs`
    derniere = max(x["annee"] for x in matchs)
    alignes = []
    for i, m in enumerate(matchs):
        reel = score_reel_en_sets(m)
        if reel is not None and m["annee"] < derniere:
            alignes.append((m, elo["avant"][i], reel))
    if not alignes:
        return {"beta": BETA_DEFAUT, "logloss_ajustement": None,
                "n_ajustement": 0, "grille": grille,
                "erreur": "aucun score en sets exploitable"}

    def logloss(beta: float, lot) -> float:
        tot = 0.0
        for m, (ra, rb), reel in lot:
            sc = pronostic(ra, rb, m["surface"], m["best_of"], beta, params,
                           complet=False)["scores"]
            tot += -math.log(max(sc.get(reel, 1e-9), 1e-9))
        return tot / len(lot)

    sous = alignes[:: max(1, len(alignes) // 6000)]     # 6 000 matchs suffisent
    scores = sorted((logloss(b, sous), b) for b in grille)
    meilleur = scores[0][1]
    return {"beta": meilleur,
            "logloss_ajustement": scores[0][0],
            "n_ajustement": len(sous),
            "grille": grille}


BETA_DEFAUT = 0.155     # valeur de repli ; `ajuster_beta` la recalcule


# ------------------------------------- courbes d'inversion chaîne ↔ logistique
_GRILLE_D = np.round(np.arange(-3.0, 3.0001, 0.05), 4)
_COURBES: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def courbe_chaine(surface: str, best_of: int, beta: float):
    """P(chaîne) en fonction de `d`, pour une surface et un format donnés.

    La courbe est strictement croissante : on peut donc l'inverser. C'est ce
    qui permet d'imposer à la chaîne la probabilité de match issue de la
    logistique, tout en conservant sa cohérence interne.
    """
    cle = (surface, best_of, beta)
    if cle not in _COURBES:
        cible = (best_of + 1) // 2
        ps = []
        for d in _GRILLE_D:
            p_serv, p_ret, p_tb = points_depuis_elo(float(d), surface, beta)
            ent = distribution_set_cachee(p_serv, p_ret, p_tb)
            sc = scores_en_sets(ent, cible)
            ps.append(sum(p for s, p in sc.items()
                          if int(s.split("-")[0]) == cible))
        _COURBES[cle] = (_GRILLE_D, np.array(ps))
    return _COURBES[cle]


def d_equivalent(p_cible: float, surface: str, best_of: int, beta: float) -> float:
    """Quel écart `d` la chaîne doit-elle croire pour annoncer `p_cible` ?"""
    grille, ps = courbe_chaine(surface, best_of, beta)
    p_cible = min(max(p_cible, 1e-6), 1 - 1e-6)
    if p_cible <= ps[0]:
        return float(grille[0])
    if p_cible >= ps[-1]:
        return float(grille[-1])
    return float(np.interp(p_cible, ps, grille))


# ============================================================ prédictions
def pronostic(elo_a: float, elo_b: float, surface: str, best_of: int,
              beta: float, params: dict | None = None,
              complet: bool = True) -> dict:
    """Cœur du moteur : renvoie TOUS les marchés pour une rencontre.

    `params`   = sortie de `ajuster_logistique` (échelle par surface/format).
                 Sans lui, on retombe sur une échelle neutre de 1,0.
    `complet`  = False n'exécute que la partie « sets » et saute les deux
                 programmes dynamiques sur les jeux. Utile pendant
                 l'ajustement, qui n'a besoin que des scores en sets :
                 c'est environ 3× plus rapide.
    """
    d = (elo_a - elo_b) / 400.0
    surf = surface if surface in BASE_SERVICE else "Hard"
    bo = 5 if best_of >= 5 else 3
    ech, dec = 1.0, 0.0
    if params:
        cle = f"{surf}|{bo}"
        if cle not in params:                       # surface rare → même format
            cle = next((c for c in params if c.endswith(f"|{bo}")), None)
        if cle:
            ech = params[cle]["echelle"]
            dec = params[cle].get("decalage", 0.0)
    p_a = _logistique(d, dec, ech)

    # La chaîne est réalignée sur cette probabilité : on lui donne l'écart
    # fictif qui lui ferait annoncer exactement p_a, puis on lui laisse
    # dérouler les sets et les jeux.
    d_eff = d_equivalent(p_a, surf, bo, beta)
    p_serv, p_ret, p_tb = points_depuis_elo(d_eff, surf, beta)
    entrees = distribution_set_cachee(p_serv, p_ret, p_tb)
    cible = (bo + 1) // 2

    sc = scores_en_sets(entrees, cible)
    if not complet:
        return {"p_a": float(p_a), "p_b": float(1.0 - p_a),
                "scores": {k: float(v) for k, v in sc.items()},
                "p_service_a": float(p_serv), "p_retour_a": float(p_ret)}
    offset = TAILLE_DP // 2
    total = dp_match(entrees, cible, TAILLE_DP, "total")
    ecart = dp_match(entrees, cible, TAILLE_DP, "ecart")
    total = total / max(total.sum(), 1e-12)
    ecart = ecart / max(ecart.sum(), 1e-12)
    valeurs = np.arange(TAILLE_DP) - offset          # index → valeur réelle

    out = {
        "p_a": float(p_a),
        "p_b": float(1.0 - p_a),
        "scores": {k: float(v) for k, v in sorted(sc.items(), key=lambda z: -z[1])},
        "jeux_attendus": float((total * valeurs).sum()),
        "ecart_attendu": float((ecart * valeurs).sum()),
        "p_service_a": float(p_serv),
        "p_retour_a": float(p_ret),
    }
    for seuil in (19.5, 21.5, 22.5, 23.5, 25.5, 27.5, 35.5, 39.5):
        out[f"O{seuil}"] = float(total[valeurs > seuil].sum())
        out[f"U{seuil}"] = float(total[valeurs < seuil].sum())
    # Handicap à deux issues, tel que le propose un bookmaker :
    # « A −h jeux » contre « B +h jeux ». L'un des deux gagne toujours, donc
    # les deux probabilités somment exactement à 1. La ligne est en x,5 :
    # jamais d'égalité, donc jamais de mise remboursée.
    for h in (2.5, 3.5, 4.5, 5.5, 6.5):
        out[f"A_moins_{h}"] = float(ecart[valeurs > h].sum())
        out[f"B_plus_{h}"] = float(ecart[valeurs < h].sum())
    out["sans_perdre_set"] = float(sc.get(f"{cible}-0", 0.0))
    return out
