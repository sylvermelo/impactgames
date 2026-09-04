"""
ENTRAÎNEMENT — transforme les données brutes en modèles publiables
================================================================================
Écrit `data/modeles.json`, le SEUL fichier dont l'application a besoin pour
calculer un pronostic hors ligne. Chaque sport y occupe une section autonome :
si un sport échoue à s'entraîner, les deux autres sont quand même publiés.

Usage :
    python3 entraine.py            # les trois sports
    python3 entraine.py tennis     # un seul
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
sys.path.insert(0, str(RACINE))

SORTIE = DATA / "modeles.json"


def _arrondi(v, n=5):
    """Arrondit pour garder le JSON léger : 5 décimales suffisent largement."""
    if isinstance(v, float):
        return round(v, n)
    if isinstance(v, dict):
        return {k: _arrondi(x, n) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_arrondi(x, n) for x in v]
    return v


# ==================================================================== TENNIS
def entrainer_tennis() -> dict | None:
    from sports import tennis as T

    matchs = T.charger_matchs(DATA)
    if len(matchs) < 2000:
        print(f"  tennis : {len(matchs)} matchs seulement, entraînement annulé")
        return None
    t0 = time.time()
    elo = T.entrainer_elo(matchs)
    params = T.ajuster_logistique(matchs, elo)
    beta = T.ajuster_beta(matchs, elo, params)["beta"]

    # classements par surface, au format "joueur|surface" — c'est ce que
    # l'application interrogera pour n'importe quelle paire de joueurs
    notes = {f"{j}|{s}": round(v, 1) for (j, s), v in elo["elo_surface"].items()}
    globales = {j: round(v, 1) for j, v in elo["elo_global"].items()}
    noms = {}
    for m in matchs[-4000:]:
        noms.setdefault(m["joueur_a"], m["nom_a"])
        noms.setdefault(m["joueur_b"], m["nom_b"])

    actifs = {j for j in noms if j in globales}
    classement = sorted(((j, globales[j]) for j in actifs), key=lambda z: -z[1])

    print(f"  tennis : {len(matchs)} matchs, {len(globales)} joueurs, "
          f"beta={beta:.3f}, {time.time() - t0:.0f} s")
    return {
        "sport": "tennis",
        "moteur": "Elo par surface + chaîne de Markov jeu→set→match",
        "beta": beta,
        "parametres": params,
        "notes_surface": notes,
        "notes_globales": globales,
        "noms": {j: noms.get(j, j) for j in actifs},
        "classement": [{"id": j, "nom": noms.get(j, j), "elo": v}
                       for j, v in classement[:60]],
        "n_matchs": len(matchs),
        "periode": [matchs[0]["date"], matchs[-1]["date"]],
    }


# ==================================================================== HOCKEY
def entrainer_hockey() -> dict | None:
    from sports import hockey as H

    matchs = H.charger_matchs(DATA / "nhl_matchs.csv")
    if len(matchs) < 200:
        print(f"  hockey : {len(matchs)} matchs seulement, entraînement annulé")
        return None
    t0 = time.time()
    modele = H.ajuster(matchs)
    if not modele or not modele.get("converge"):
        print("  hockey : l'optimiseur n'a pas convergé")
        return None
    idx = modele["idx"]
    print(f"  hockey : {len(matchs)} matchs, {len(modele['equipes'])} équipes, "
          f"γ={modele['gamma']:+.3f} (×{2.718281828 ** modele['gamma']:.3f}), "
          f"ρ={modele['rho']:+.3f}, {time.time() - t0:.0f} s")
    return {
        "sport": "hockey",
        "moteur": "Poisson bivarié attaques/défenses (correction Dixon-Coles)",
        "equipes": modele["equipes"],
        "attaque": [float(modele["attaque"][i]) for i in range(len(modele["equipes"]))],
        "defense": [float(modele["defense"][i]) for i in range(len(modele["equipes"]))],
        "gamma": float(modele["gamma"]),
        "rho": float(modele["rho"]),
        "classement": H.classement(modele),
        "n_matchs": len(matchs),
        "periode": [matchs[0]["date"], matchs[-1]["date"]],
    }


# ==================================================================== BASKET
def entrainer_basket() -> dict | None:
    from sports import basket as B

    matchs = B.charger_matchs(DATA / "nba_matchs.csv")
    if len(matchs) < 300:
        print(f"  basket : {len(matchs)} matchs seulement, entraînement annulé")
        return None
    t0 = time.time()
    modele = B.ajuster(matchs)
    if not modele:
        return None
    print(f"  basket : {len(matchs)} matchs, {len(modele['equipes'])} équipes, "
          f"avantage domicile {modele['hfa']:+.2f} pts, "
          f"σ total {modele['sigma_total']:.1f} / σ écart {modele['sigma_ecart']:.1f}, "
          f"{time.time() - t0:.0f} s")
    return {
        "sport": "basket",
        "moteur": "Normales bivariées total/écart (force nette + rythme)",
        "equipes": modele["equipes"],
        "net": [float(x) for x in modele["net"]],
        "rythme": [float(x) for x in modele["rythme"]],
        "hfa": float(modele["hfa"]),
        "base_total": float(modele["base_total"]),
        "sigma_total": float(modele["sigma_total"]),
        "sigma_ecart": float(modele["sigma_ecart"]),
        "correlation": float(modele["correlation"]),
        "classement": B.classement(modele),
        "n_matchs": len(matchs),
        "periode": [matchs[0]["date"], matchs[-1]["date"]],
    }


# ================================================================ prédiction
def pronostiquer(modeles: dict, evenement: dict) -> dict | None:
    """Applique le bon moteur à un événement du calendrier.

    C'est la fonction utilisée à la fois par `maj_calendrier.py` et par
    l'application autonome — une seule implémentation, pas deux qui divergent.
    """
    sport = evenement.get("sport")
    if sport == "hockey":
        m = modeles.get("hockey")
        if not m:
            return None
        from sports import hockey as H
        modele = {"equipes": m["equipes"], "idx": {e: i for i, e in enumerate(m["equipes"])},
                  "attaque": __import__("numpy").array(m["attaque"]),
                  "defense": __import__("numpy").array(m["defense"]),
                  "gamma": m["gamma"], "rho": m["rho"]}
        return H.pronostic(modele, evenement["domicile"], evenement["exterieur"])

    if sport == "basket":
        m = modeles.get("basket")
        if not m:
            return None
        from sports import basket as B
        modele = {"equipes": m["equipes"], "idx": {e: i for i, e in enumerate(m["equipes"])},
                  "net": __import__("numpy").array(m["net"]),
                  "rythme": __import__("numpy").array(m["rythme"]),
                  "hfa": m["hfa"], "base_total": m["base_total"],
                  "sigma_total": m["sigma_total"], "sigma_ecart": m["sigma_ecart"],
                  "correlation": m["correlation"]}
        return B.pronostic(modele, evenement["domicile"], evenement["exterieur"])

    if sport == "tennis":
        m = modeles.get("tennis")
        if not m:
            return None
        from sports import tennis as T
        a, b = evenement["joueur_a"], evenement["joueur_b"]
        surf = evenement.get("surface", "Hard")
        ea = m["notes_surface"].get(f"{a}|{surf}", m["notes_globales"].get(a))
        eb = m["notes_surface"].get(f"{b}|{surf}", m["notes_globales"].get(b))
        if ea is None or eb is None:
            return {"erreur": "joueur sans historique"}
        return T.pronostic(ea, eb, surf, evenement.get("best_of", 3),
                           m["beta"], m["parametres"])
    return None


# ====================================================================== main
FONCTIONS = {"tennis": entrainer_tennis, "hockey": entrainer_hockey,
             "basket": entrainer_basket}


def main(argv) -> int:
    cibles = [a for a in argv[1:] if a in FONCTIONS] or list(FONCTIONS)
    print("=" * 70)
    print(f"ENTRAÎNEMENT — {', '.join(cibles)} — {dt.datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 70)

    anciens = {}
    if SORTIE.exists():
        try:
            anciens = json.loads(SORTIE.read_text(encoding="utf-8")).get("modeles", {})
        except (json.JSONDecodeError, OSError):
            anciens = {}

    modeles = {}
    for c in cibles:
        try:
            r = FONCTIONS[c]()
        except Exception as e:
            print(f"  {c} : ÉCHEC {type(e).__name__}: {e}")
            r = None
        # un sport qui échoue ne doit pas effacer son modèle précédent
        modeles[c] = r if r else anciens.get(c)
        if not r:
            print(f"  {c} : aucun modèle produit"
                  + (" — l'ancien est conservé" if anciens.get(c) else ""))

    actifs = {k: v for k, v in modeles.items() if v}
    if not actifs:
        print("\nAucun modèle entraîné : data/modeles.json n'est PAS écrasé.")
        return 1

    DATA.mkdir(exist_ok=True)
    SORTIE.write_text(json.dumps(
        {"genere_le": dt.datetime.now().isoformat(timespec="seconds"),
         "modeles": _arrondi(actifs)}, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {SORTIE.name} écrit ({SORTIE.stat().st_size / 1024:.0f} Ko) "
          f"pour {len(actifs)} sport(s) : {', '.join(actifs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
