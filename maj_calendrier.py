"""
CALENDRIER — les événements à venir, passés au moteur
================================================================================
Récupère les rencontres des 8 prochains jours, puis leur applique IMMÉDIATEMENT
le modèle entraîné. Le fichier `data/calendrier.json` qui en sort contient donc
des pronostics déjà calculés : l'application n'a plus qu'à les afficher, ce qui
lui permet de fonctionner hors ligne et sur un simple fichier HTML.

Le filtrage anti-passé est le point le plus important : un match déjà joué ne
doit JAMAIS apparaître, sinon l'application affiche des « pronostics » dont on
connaît le résultat — exactement ce qui ruine la crédibilité du produit.

Sources (gratuites, sans clé) :
    · tennis → ESPN, tournois ATP
    · hockey → api-web.nhle.com/v1/schedule
    · basket → ESPN, scoreboard NBA
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
sys.path.insert(0, str(RACINE))

from sources import _get                      # noqa: E402

JOURS_A_VENIR = 8
SORTIE = DATA / "calendrier.json"


def _normalise(nom: str) -> str:
    """`'Novak Đoković'` → `'novak djokovic'` : indispensable pour retrouver
    un joueur quel que soit l'accent utilisé par la source."""
    s = unicodedata.normalize("NFKD", str(nom or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace(".", " ").split())


def _dates_a_venir(n: int = JOURS_A_VENIR) -> list[dt.date]:
    aujourdhui = dt.date.today()
    return [aujourdhui + dt.timedelta(days=k) for k in range(n)]


# ==================================================================== TENNIS
def calendrier_tennis(modeles: dict) -> list[dict]:
    """Cartographie ESPN (noms de joueurs) → identifiants Sackmann.

    C'est le seul point délicat du tennis : les deux sources n'ont pas la même
    clé. On construit un index nom → identifiant à partir du modèle entraîné,
    et on écarte tout joueur introuvable plutôt que de deviner.
    """
    m = modeles.get("tennis")
    if not m:
        return []
    index = {_normalise(nom): pid for pid, nom in m["noms"].items()}

    out = []
    for d in _dates_a_venir():
        url = (f"https://site.api.espn.com/apis/site/v2/sports/tennis/atp/"
               f"scoreboard?dates={d:%Y%m%d}")
        brut = _get(url, timeout=30)
        if not brut:
            continue
        try:
            evs = json.loads(brut).get("events", [])
        except json.JSONDecodeError:
            continue
        for e in evs:
            comp = (e.get("competitions") or [{}])[0]
            comps = comp.get("competitors") or []
            if len(comps) != 2:
                continue
            if comp.get("status", {}).get("type", {}).get("completed"):
                continue                       # déjà joué : on ne montre PAS
            noms = [c.get("athlete", {}).get("displayName") for c in comps]
            if not all(noms):
                continue
            ids = [index.get(_normalise(n)) for n in noms]
            surface = _devine_surface(e.get("season", {}), e.get("name", ""))
            best_of = 5 if _est_grand_chelem(e.get("name", "")) else 3
            out.append({"sport": "tennis", "date": d.isoformat(),
                        "heure": (e.get("date") or "")[11:16],
                        "competition": e.get("name", ""),
                        "surface": surface, "best_of": best_of,
                        "joueur_a": ids[0], "joueur_b": ids[1],
                        "nom_a": noms[0], "nom_b": noms[1],
                        "connu": all(ids)})
    return out


GRANDS_CHELEMS = ("australian open", "roland garros", "french open",
                  "wimbledon", "us open")


def _est_grand_chelem(nom: str) -> bool:
    n = _normalise(nom)
    return any(g in n for g in GRANDS_CHELEMS)


def _devine_surface(_saison, nom: str) -> str:
    n = _normalise(nom)
    if "wimbledon" in n or "queen" in n or "halle" in n or "eastbourne" in n:
        return "Grass"
    if any(x in n for x in ("roland garros", "french open", "monte carlo",
                            "madrid", "rome", "barcelona", "buenos aires")):
        return "Clay"
    return "Hard"


# ==================================================================== HOCKEY
def calendrier_hockey(modeles: dict) -> list[dict]:
    m = modeles.get("hockey")
    if not m:
        return []
    connus = set(m["equipes"])
    out = []
    for d in _dates_a_venir():
        url = f"https://api-web.nhle.com/v1/schedule/{d.isoformat()}"
        brut = _get(url, timeout=30)
        if not brut:
            continue
        try:
            jours = json.loads(brut).get("gameWeek", [])
        except json.JSONDecodeError:
            continue
        for jour in jours:
            if jour.get("date") != d.isoformat():
                continue
            for g in jour.get("games", []):
                if g.get("gameState") != "FUT":
                    continue                   # joué ou en cours
                hd = (g.get("homeTeam") or {}).get("abbrev")
                ad = (g.get("awayTeam") or {}).get("abbrev")
                if not hd or not ad:
                    continue
                out.append({"sport": "hockey", "date": d.isoformat(),
                            "heure": (g.get("startTimeUTC") or "")[11:16],
                            "competition": "NHL",
                            "domicile": hd, "exterieur": ad,
                            "connu": hd in connus and ad in connus})
    return out


# ==================================================================== BASKET
def calendrier_basket(modeles: dict) -> list[dict]:
    m = modeles.get("basket")
    if not m:
        return []
    connus = set(m["equipes"])
    out = []
    for d in _dates_a_venir():
        url = (f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
               f"scoreboard?dates={d:%Y%m%d}")
        brut = _get(url, timeout=30)
        if not brut:
            continue
        try:
            evs = json.loads(brut).get("events", [])
        except json.JSONDecodeError:
            continue
        for e in evs:
            comp = (e.get("competitions") or [{}])[0]
            if comp.get("status", {}).get("type", {}).get("completed"):
                continue
            dom = ext = None
            for c in comp.get("competitors", []):
                code = (c.get("team") or {}).get("abbreviation")
                if c.get("homeAway") == "home":
                    dom = code
                else:
                    ext = code
            if not dom or not ext:
                continue
            out.append({"sport": "basket", "date": d.isoformat(),
                        "heure": (e.get("date") or "")[11:16],
                        "competition": "NBA",
                        "domicile": dom, "exterieur": ext,
                        "connu": dom in connus and ext in connus})
    return out


# ================================================================= orchestre
def construire(modeles: dict) -> dict:
    from entraine import pronostiquer

    evenements = []
    for f in (calendrier_tennis, calendrier_hockey, calendrier_basket):
        try:
            lot = f(modeles)
        except Exception as e:
            print(f"  ! {f.__name__} : {type(e).__name__}: {e}")
            lot = []
        print(f"  {f.__name__.replace('calendrier_', ''):<8} {len(lot):>4} événements")
        evenements.extend(lot)

    # passage au moteur : c'est ici que le calendrier devient un pronostic
    predits = 0
    for ev in evenements:
        p = pronostiquer(modeles, ev)
        if p and "erreur" not in p:
            ev["pronostic"] = p
            predits += 1

    evenements.sort(key=lambda e: (e["date"], e.get("heure", "")))
    print(f"  → {predits}/{len(evenements)} événements analysés par le moteur")
    return {"genere_le": dt.datetime.now().isoformat(timespec="seconds"),
            "n_evenements": len(evenements), "n_analyses": predits,
            "evenements": evenements}


def main() -> int:
    print("=" * 70)
    print(f"CALENDRIER — {JOURS_A_VENIR} prochains jours — "
          f"{dt.datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 70)
    if not (DATA / "modeles.json").exists():
        print("  ! data/modeles.json absent : lance d'abord entraine.py")
        return 1
    modeles = json.loads((DATA / "modeles.json").read_text(encoding="utf-8"))["modeles"]

    cal = construire(modeles)
    if cal["n_evenements"] == 0:
        print("  aucun événement reçu : le calendrier existant est conservé")
        return 2
    SORTIE.write_text(json.dumps(cal, ensure_ascii=False), encoding="utf-8")
    print(f"→ {SORTIE.name} écrit ({SORTIE.stat().st_size / 1024:.0f} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
