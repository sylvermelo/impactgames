"""
Calendrier multi-sports — ESPN (API publique, sans clé).

Fenêtre glissante ~8 jours, matchs déjà joués exclus.
Si ESPN est injoignable, le calendrier existant est conservé.
"""
from __future__ import annotations

import datetime
from sources import (
    NBA_CANON, NHL_CANON, canon, curl_json, extraire_espn_events, _norme,
)

JOURS = 8

SLUGS = [
    ("basket", "NBA", "basketball/nba", NBA_CANON),
    ("basket", "WNBA", "basketball/wnba", {}),
    ("basket", "Euroleague", "basketball/euroleague", {}),
    ("hockey", "NHL", "hockey/nhl", NHL_CANON),
]


def _espn_jour(slug, jour: datetime.date):
    iso = jour.strftime("%Y%m%d")
    return curl_json(
        f"https://site.api.espn.com/apis/site/v2/sports/{slug}/scoreboard?dates={iso}"
    )


def _tennis_scoreboard(circuit: str):
    """ATP / WTA : le scoreboard ESPN a une forme un peu différente (tournois)."""
    return curl_json(
        f"https://site.api.espn.com/apis/site/v2/sports/tennis/{circuit}/scoreboard"
    )


def extraire_tennis(payload, ligue: str, auj: datetime.date):
    out = []
    if not payload:
        return out
    events = payload.get("events") or []
    # parfois les matchs sont dans leagues[].events, parfois à la racine
    if not events:
        for lg in payload.get("leagues") or []:
            events.extend(lg.get("events") or [])
    for e in events:
        st = (e.get("status") or {}).get("type") or {}
        if st.get("completed"):
            continue
        # compétitions = un match
        comps = e.get("competitions") or [e]
        for comp in comps:
            if (comp.get("status") or {}).get("type", {}).get("completed"):
                continue
            joueurs = []
            for c in comp.get("competitors") or []:
                ath = c.get("athlete") or c.get("team") or {}
                nom = ath.get("displayName") or ath.get("shortName") or ath.get("name")
                if nom:
                    joueurs.append(nom)
            if len(joueurs) < 2:
                # format "Novak Djokovic vs Carlos Alcaraz"
                name = e.get("name") or e.get("shortName") or ""
                if " vs " in name.lower() or " v " in f" {name.lower()} ":
                    parts = name.replace(" vs. ", " vs ").replace(" v ", " vs ").split(" vs ")
                    if len(parts) == 2:
                        joueurs = [p.strip() for p in parts]
            if len(joueurs) < 2:
                continue
            dt = comp.get("date") or e.get("date") or ""
            try:
                utc = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
                loc = utc + datetime.timedelta(hours=1)
                d_iso, heure = loc.date().isoformat(), loc.strftime("%H:%M")
            except Exception:
                d_iso, heure = (dt[:10] if dt else auj.isoformat()), ""
            if d_iso and d_iso < auj.isoformat():
                continue
            surface = None
            venue = (comp.get("venue") or e.get("venue") or {})
            # ESPN met parfois la surface dans notes / league
            notes = " ".join(n.get("text", "") for n in (e.get("notes") or []) if isinstance(n, dict))
            lg = (e.get("group") or {})
            tournoi = (e.get("name") or lg.get("name") or ligue)
            # best of : Grand Chelem hommes = 5, sinon 3
            slam = any(k in (tournoi or "").lower() for k in
                       ("australian open", "roland", "wimbledon", "us open", "u.s. open"))
            best_of = 5 if slam and ligue == "ATP" else 3
            out.append({
                "sport": "tennis", "ligue": ligue, "div": ligue,
                "date": d_iso, "heure": heure,
                "home": joueurs[0], "away": joueurs[1],
                "surface": "Hard", "best_of": best_of,
                "tournoi": tournoi, "source": "ESPN",
                "cote_1": None, "cote_2": None, "ou_line": None,
            })
    return out


def construire(db, jours=JOURS):
    auj = datetime.date.today()
    dates = [auj + datetime.timedelta(days=i) for i in range(jours)]
    out, vus = [], set()
    par = {"ESPN": 0}

    def ajouter(m):
        cle = (m["sport"], m.get("ligue"), m["home"], m["away"], m["date"])
        if cle in vus:
            return
        if (m.get("date") or "") < auj.isoformat():
            return
        vus.add(cle)
        m.setdefault("div", m.get("ligue"))
        out.append(m)
        par["ESPN"] += 1

    # un test : si ESPN ne répond pas, on sort tout de suite
    probe = _espn_jour("basketball/nba", auj)
    espn_ok = probe is not None

    if espn_ok:
        for sport, ligue, slug, table in SLUGS:
            for d in dates:
                payload = _espn_jour(slug, d)
                for m in extraire_espn_events(payload, sport, ligue, table, completed_only=False):
                    m["div"] = ligue
                    m["cote_1"] = None
                    m["cote_2"] = None
                    # moneyline américain → décimal si présent
                    from moteurs import american_to_decimal
                    if m.get("ml_h") is not None:
                        m["cote_1"] = american_to_decimal(m["ml_h"])
                    if m.get("ml_a") is not None:
                        m["cote_2"] = american_to_decimal(m["ml_a"])
                    ajouter(m)
        for circuit in ("atp", "wta"):
            payload = _tennis_scoreboard(circuit)
            for m in extraire_tennis(payload, circuit.upper(), auj):
                ajouter(m)

    # rattacher les joueurs/équipes au modèle (tennis : matching flou)
    _rapprocher_tennis(out, db)

    out.sort(key=lambda x: (x.get("date") or "9999", x.get("heure") or "", x.get("sport") or ""))
    log = {
        "sources": par, "total": len(out), "espn_ok": espn_ok,
        "par_sport": _compte(out),
        "genere_le": datetime.datetime.now().isoformat(timespec="minutes"),
        "statut": "ok" if out else ("vide" if espn_ok else "espn_injoignable"),
    }
    return out, log


def _compte(matchs):
    d = {}
    for m in matchs:
        k = f"{m.get('sport')}:{m.get('ligue')}"
        d[k] = d.get(k, 0) + 1
    return d


def _rapprocher_tennis(matchs, db):
    """Aligne les noms ESPN sur ceux du modèle Elo (sans accent, tiret, etc.)."""
    tennis = ((db.get("sports") or {}).get("tennis") or {}).get("ligues") or {}
    noms = []
    for lig, L in tennis.items():
        noms.extend((lig, n) for n in (L.get("joueurs") or {}))
    if not noms:
        return
    index = {}
    for lig, n in noms:
        index.setdefault(_norme(n), []).append((lig, n))
    for m in matchs:
        if m.get("sport") != "tennis":
            continue
        for champ in ("home", "away"):
            k = _norme(m.get(champ))
            cands = index.get(k) or []
            if len(cands) == 1:
                m["ligue"] = m["div"] = cands[0][0]
                m[champ] = cands[0][1]


def appliquer(db):
    matchs, log = construire(db)
    if matchs:
        db["fixtures"] = matchs
        log["statut"] = "ok"
    else:
        log["statut"] = ("echec — calendrier existant conservé"
                         if db.get("fixtures") else "aucun match")
    db["calendrier_log"] = log
    return log
