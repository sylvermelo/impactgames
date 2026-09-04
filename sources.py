"""
Téléchargement des données historiques — sources 100 % gratuites, sans clé.

  Basketball / Hockey
    · archive 10 ans + cotes (Sportsbook Review, miroir GitHub)
    · complément récent : API publique ESPN (scoreboard / calendrier d'équipe)

  Tennis
    · tennis-data.co.uk (ATP + WTA, cotes Bet365 / Pinnacle) si joignable
    · miroir GitHub au format Sackmann (ATP 2012-2022) en secours

Rien n'est payant. Si une source tombe, les autres prennent le relais.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"

SBR_REPO = "https://github.com/flancast90/sportsbookreview-scraper.git"
ATP_REPO = "https://github.com/hellojohncruz/atp_tennis_matches.git"

# tennis-data.co.uk — identique à football-data.co.uk, gratuit, sans clé
TD_ATP = "http://www.tennis-data.co.uk/{y}/{y}.csv"
TD_ATP_XLSX = "http://www.tennis-data.co.uk/{y}/{y}.xlsx"
TD_WTA = "http://www.tennis-data.co.uk/{y}w/{y}.csv"
TD_WTA_XLSX = "http://www.tennis-data.co.uk/{y}w/{y}.xlsx"

UA = {"User-Agent": "Mozilla/5.0 (compatible; impactgames/1.0)"}


def log(msg):
    print(msg, flush=True)


def _curl(url: str, dest: Path | None = None, timeout: int = 40) -> bytes | None:
    """curl : ESPN et plusieurs sources refusent l'empreinte TLS d'urllib."""
    cmd = ["curl", "-sS", "-L", "--max-time", str(timeout),
           "-A", UA["User-Agent"], url]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout + 8)
        if p.returncode != 0 or not p.stdout:
            return None
        if dest is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(p.stdout)
            shutil.move(str(tmp), str(dest))
        return p.stdout
    except Exception:
        return None


def curl_json(url: str, timeout: int = 30):
    raw = _curl(url, timeout=timeout)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def git_clone(url: str, dest: Path) -> bool:
    if dest.exists() and any(dest.iterdir()):
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    try:
        p = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True, text=True, timeout=120,
        )
        return p.returncode == 0
    except Exception:
        return False


# --------------------------------------------------------------------------- noms
NBA_CANON = {
    "hawks": "Hawks", "atlanta hawks": "Hawks", "atlanta": "Hawks",
    "celtics": "Celtics", "boston celtics": "Celtics", "boston": "Celtics",
    "nets": "Nets", "brooklyn nets": "Nets", "brooklyn": "Nets",
    "newjersey": "Nets", "new jersey nets": "Nets", "nj nets": "Nets",
    "hornets": "Hornets", "charlotte hornets": "Hornets", "charlotte": "Hornets",
    "bobcats": "Hornets", "charlotte bobcats": "Hornets",
    "bulls": "Bulls", "chicago bulls": "Bulls", "chicago": "Bulls",
    "cavaliers": "Cavaliers", "cleveland cavaliers": "Cavaliers", "cleveland": "Cavaliers",
    "cavs": "Cavaliers",
    "mavericks": "Mavericks", "dallas mavericks": "Mavericks", "dallas": "Mavericks", "mavs": "Mavericks",
    "nuggets": "Nuggets", "denver nuggets": "Nuggets", "denver": "Nuggets",
    "pistons": "Pistons", "detroit pistons": "Pistons", "detroit": "Pistons",
    "warriors": "Warriors", "golden state": "Warriors", "golden state warriors": "Warriors",
    "gsw": "Warriors",
    "rockets": "Rockets", "houston rockets": "Rockets", "houston": "Rockets",
    "pacers": "Pacers", "indiana pacers": "Pacers", "indiana": "Pacers",
    "clippers": "Clippers", "la clippers": "Clippers", "los angeles clippers": "Clippers",
    "l.a. clippers": "Clippers",
    "lakers": "Lakers", "la lakers": "Lakers", "los angeles lakers": "Lakers",
    "l.a. lakers": "Lakers",
    "grizzlies": "Grizzlies", "memphis grizzlies": "Grizzlies", "memphis": "Grizzlies",
    "heat": "Heat", "miami heat": "Heat", "miami": "Heat",
    "bucks": "Bucks", "milwaukee bucks": "Bucks", "milwaukee": "Bucks",
    "timberwolves": "Timberwolves", "minnesota timberwolves": "Timberwolves",
    "minnesota": "Timberwolves", "wolves": "Timberwolves",
    "pelicans": "Pelicans", "new orleans pelicans": "Pelicans", "new orleans": "Pelicans",
    "hornets new orleans": "Pelicans",
    "knicks": "Knicks", "new york knicks": "Knicks", "new york": "Knicks", "ny knicks": "Knicks",
    "thunder": "Thunder", "oklahoma city": "Thunder", "oklahoma city thunder": "Thunder",
    "okc": "Thunder", "seattle supersonics": "Thunder", "sonics": "Thunder",
    "magic": "Magic", "orlando magic": "Magic", "orlando": "Magic",
    "76ers": "76ers", "seventysixers": "76ers", "philadelphia 76ers": "76ers",
    "philadelphia": "76ers", "sixers": "76ers", "phila": "76ers",
    "suns": "Suns", "phoenix suns": "Suns", "phoenix": "Suns",
    "trailblazers": "Trail Blazers", "trail blazers": "Trail Blazers",
    "portland trail blazers": "Trail Blazers", "portland": "Trail Blazers", "blazers": "Trail Blazers",
    "kings": "Kings", "sacramento kings": "Kings", "sacramento": "Kings",
    "spurs": "Spurs", "san antonio spurs": "Spurs", "san antonio": "Spurs",
    "raptors": "Raptors", "toronto raptors": "Raptors", "toronto": "Raptors",
    "jazz": "Jazz", "utah jazz": "Jazz", "utah": "Jazz",
    "wizards": "Wizards", "washington wizards": "Wizards", "washington": "Wizards",
}

NHL_CANON = {
    "ducks": "Ducks", "anaheim ducks": "Ducks", "anaheim": "Ducks",
    "coyotes": "Coyotes", "arizona coyotes": "Coyotes", "arizona": "Coyotes",
    "arizonas": "Coyotes", "phoenix": "Coyotes", "phoenix coyotes": "Coyotes",
    "utah hockey club": "Utah", "utah": "Utah",
    "bruins": "Bruins", "boston bruins": "Bruins", "boston": "Bruins",
    "sabres": "Sabres", "buffalo sabres": "Sabres", "buffalo": "Sabres",
    "flames": "Flames", "calgary flames": "Flames", "calgary": "Flames",
    "hurricanes": "Hurricanes", "carolina hurricanes": "Hurricanes", "carolina": "Hurricanes",
    "blackhawks": "Blackhawks", "chicago blackhawks": "Blackhawks", "chicago": "Blackhawks",
    "avalanche": "Avalanche", "colorado avalanche": "Avalanche", "colorado": "Avalanche",
    "blue jackets": "Blue Jackets", "columbus blue jackets": "Blue Jackets", "columbus": "Blue Jackets",
    "stars": "Stars", "dallas stars": "Dallas Stars" if False else "Stars",
    "dallas stars": "Stars", "dallas": "Stars",
    "red wings": "Red Wings", "detroit red wings": "Red Wings", "detroit": "Red Wings",
    "oilers": "Oilers", "edmonton oilers": "Oilers", "edmonton": "Oilers",
    "panthers": "Panthers", "florida panthers": "Panthers", "florida": "Panthers",
    "kings": "Kings", "los angeles kings": "Kings", "la kings": "Kings",
    "wild": "Wild", "minnesota wild": "Wild", "minnesota": "Wild",
    "canadiens": "Canadiens", "montreal canadiens": "Canadiens", "montreal": "Canadiens", "habs": "Canadiens",
    "predators": "Predators", "nashville predators": "Predators", "nashville": "Predators",
    "devils": "Devils", "new jersey devils": "Devils", "new jersey": "Devils",
    "islanders": "Islanders", "ny islanders": "Islanders", "new york islanders": "Islanders",
    "rangers": "Rangers", "ny rangers": "Rangers", "new york rangers": "Rangers",
    "senators": "Senators", "ottawa senators": "Senators", "ottawa": "Senators",
    "flyers": "Flyers", "philadelphia flyers": "Flyers", "philadelphia": "Flyers",
    "penguins": "Penguins", "pittsburgh penguins": "Penguins", "pittsburgh": "Penguins",
    "sharks": "Sharks", "san jose sharks": "Sharks", "san jose": "Sharks",
    "kraken": "Kraken", "seattle kraken": "Kraken", "seattlekraken": "Kraken", "seattle": "Kraken",
    "blues": "Blues", "st.louis": "Blues", "st louis": "Blues", "st. louis blues": "Blues",
    "st louis blues": "Blues", "st. louis": "Blues", "stlouis": "Blues",
    "tampabay": "Lightning", "nysislanders": "Islanders", "winnipegjets": "Jets",
    "lightning": "Lightning", "tampa": "Lightning", "tampa bay": "Lightning",
    "tampa bay lightning": "Lightning",
    "maple leafs": "Maple Leafs", "toronto maple leafs": "Maple Leafs", "toronto": "Maple Leafs", "leafs": "Maple Leafs",
    "canucks": "Canucks", "vancouver canucks": "Canucks", "vancouver": "Canucks",
    "golden knights": "Golden Knights", "vegas golden knights": "Golden Knights", "vegas": "Golden Knights",
    "capitals": "Capitals", "washington capitals": "Capitals", "washington": "Capitals",
    "jets": "Jets", "winnipeg jets": "Jets", "winnipegjets": "Jets", "winnipeg": "Jets",
}


def canon(nom: str, table: dict) -> str | None:
    if not nom or str(nom).strip() in ("0", "None", "nan"):
        return None
    s = str(nom).strip()
    k = s.lower().replace("-", " ").replace(".", " ").replace("'", "")
    k = " ".join(k.split())
    compact = k.replace(" ", "")
    if k in table:
        return table[k]
    if compact in table:
        return table[compact]
    last = k.split()[-1] if k else ""
    if last in table:
        return table[last]
    return s  # on garde le nom brut si inconnu (Euroleague, WNBA…)


def _num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _date_sbr(x) -> str:
    try:
        v = int(float(x))
        s = f"{v:08d}"
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    except (TypeError, ValueError):
        return ""


# --------------------------------------------------------------------------- archives SBR
def charger_sbr_nba() -> list:
    src = DATA / "nba_archive_10Y.json"
    if not src.exists():
        return []
    raw = json.loads(src.read_text(encoding="utf-8"))
    out = []
    for g in raw:
        h = canon(g.get("home_team"), NBA_CANON)
        a = canon(g.get("away_team"), NBA_CANON)
        if not h or not a or h == a:
            continue
        try:
            hg, ag = int(g["home_final"]), int(g["away_final"])
        except (TypeError, ValueError, KeyError):
            continue
        out.append({
            "sport": "basket", "ligue": "NBA", "date": _date_sbr(g.get("date")),
            "home": h, "away": a, "hg": hg, "ag": ag,
            "saison": int(g.get("season") or 0),
            "ml_h": _num(g.get("home_close_ml")), "ml_a": _num(g.get("away_close_ml")),
            "spread_h": _num(g.get("home_close_spread")),
            "total": _num(g.get("close_over_under")),
            "source": "SBR",
        })
    return out


def charger_sbr_nhl() -> list:
    src = DATA / "nhl_archive_10Y.json"
    if not src.exists():
        return []
    raw = json.loads(src.read_text(encoding="utf-8"))
    out = []
    for g in raw:
        h = canon(g.get("home_team"), NHL_CANON)
        a = canon(g.get("away_team"), NHL_CANON)
        if not h or not a or h == a:
            continue
        try:
            hg, ag = int(float(g["home_final"])), int(float(g["away_final"]))
        except (TypeError, ValueError, KeyError):
            continue
        out.append({
            "sport": "hockey", "ligue": "NHL", "date": _date_sbr(g.get("date")),
            "home": h, "away": a, "hg": hg, "ag": ag,
            "saison": int(g.get("season") or 0),
            "ml_h": _num(g.get("home_close_ml")), "ml_a": _num(g.get("away_close_ml")),
            "spread_h": _num(g.get("home_close_spread")),
            "total": _num(g.get("close_over_under")),
            "source": "SBR",
        })
    return out


def assurer_archives() -> dict:
    """Clone les miroirs GitHub si les JSON/CSV ne sont pas déjà là."""
    DATA.mkdir(exist_ok=True)
    info = {"nba": False, "nhl": False, "atp": False}
    if not (DATA / "nba_archive_10Y.json").exists() or not (DATA / "nhl_archive_10Y.json").exists():
        tmp = DATA / "_sbr"
        log("  clone archive SBR (NBA + NHL, 10 saisons, cotes incluses)…")
        if git_clone(SBR_REPO, tmp):
            for nom in ("nba_archive_10Y.json", "nhl_archive_10Y.json"):
                src = tmp / "data" / nom
                if src.exists():
                    shutil.copy2(src, DATA / nom)
                    info[nom[:3]] = True
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        info["nba"] = info["nhl"] = True

    atp_dir = DATA / "atp"
    if not atp_dir.exists() or not any(atp_dir.glob("atp_matches_*.csv")):
        log("  clone archive ATP (Sackmann 2012-2022)…")
        if git_clone(ATP_REPO, atp_dir):
            info["atp"] = True
    else:
        info["atp"] = True
    return info


# --------------------------------------------------------------------------- ESPN historique (complément post-2021)
ESPN_BASKET = {
    "NBA": "basketball/nba",
    "WNBA": "basketball/wnba",
    "Euroleague": "basketball/euroleague",
}
ESPN_HOCKEY = {"NHL": "hockey/nhl"}


def espn_scoreboard(slug: str, jour: date):
    iso = jour.strftime("%Y%m%d")
    return curl_json(
        f"https://site.api.espn.com/apis/site/v2/sports/{slug}/scoreboard?dates={iso}"
    )


def extraire_espn_events(payload, sport: str, ligue: str, table: dict, completed_only=True):
    out = []
    if not payload:
        return out
    for e in payload.get("events") or []:
        st = (e.get("status") or {}).get("type") or {}
        done = bool(st.get("completed"))
        if completed_only and not done:
            continue
        if not completed_only and done:
            continue
        comps = (e.get("competitions") or [{}])[0]
        home = away = None
        hs = as_ = None
        for c in comps.get("competitors") or []:
            nom = (c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("shortDisplayName")
            nom = canon(nom, table) if table else (nom or "").strip()
            sc = c.get("score")
            try:
                sc = int(float(sc)) if sc not in (None, "") else None
            except (TypeError, ValueError):
                sc = None
            if c.get("homeAway") == "home":
                home, hs = nom, sc
            else:
                away, as_ = nom, sc
        if not home or not away:
            continue
        dt = e.get("date") or ""
        try:
            utc = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            loc = utc + timedelta(hours=1)  # Cotonou UTC+1
            d_iso, heure = loc.date().isoformat(), loc.strftime("%H:%M")
        except Exception:
            d_iso, heure = (dt[:10] if dt else ""), ""
        odds = [o for o in (comps.get("odds") or []) if o]
        ou = ml_h = ml_a = spread = None
        if odds:
            o0 = odds[0]
            ou = _num(o0.get("overUnder"))
            mh = o0.get("homeTeamOdds") or {}
            ma = o0.get("awayTeamOdds") or {}
            ml_h = _num(mh.get("moneyLine"))
            ml_a = _num(ma.get("moneyLine"))
            spread = _num((mh.get("spread") if isinstance(mh, dict) else None) or o0.get("spread"))
        item = {
            "sport": sport, "ligue": ligue, "date": d_iso, "heure": heure,
            "home": home, "away": away, "hg": hs, "ag": as_,
            "ml_h": ml_h, "ml_a": ml_a, "spread_h": spread, "total": ou,
            "source": "ESPN", "termine": done,
            "ou_line": ou,
        }
        out.append(item)
    return out


def espn_historique(sport: str, ligue: str, slug: str, table: dict,
                    depuis: date, jusqua: date | None = None, pause=0.08) -> list:
    """Parcourt jour par jour. Lent mais robuste ; le cache évite de recommencer."""
    jusqua = jusqua or date.today()
    cache = DATA / f"espn_{ligue}_{depuis.isoformat()}_{jusqua.isoformat()}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    out, jour, n_ok = [], depuis, 0
    while jour <= jusqua:
        payload = espn_scoreboard(slug, jour)
        if payload:
            batch = extraire_espn_events(payload, sport, ligue, table, completed_only=True)
            out.extend(batch)
            n_ok += 1
        jour += timedelta(days=1)
        if pause:
            time.sleep(pause)
    # dédoublonnage
    vus, uniq = set(), []
    for m in out:
        cle = (m["date"], m["home"], m["away"])
        if cle in vus:
            continue
        vus.add(cle)
        uniq.append(m)
    cache.write_text(json.dumps(uniq), encoding="utf-8")
    log(f"    ESPN {ligue} : {len(uniq)} matchs ({n_ok} jours joignables)")
    return uniq


def espn_ids_equipes(slug: str) -> list:
    d = curl_json(f"https://site.api.espn.com/apis/site/v2/sports/{slug}/teams")
    ids = []
    if not d:
        return ids
    sports = d.get("sports") or [d]
    for sp in sports:
        for lg in sp.get("leagues") or []:
            for t in lg.get("teams") or []:
                team = t.get("team") or t
                i = team.get("id")
                if i:
                    ids.append(str(i))
    return ids


def espn_depuis_calendriers(sport, ligue, slug, table, saisons) -> list:
    """1 requête par équipe × saison — beaucoup plus léger que jour par jour."""
    ids = espn_ids_equipes(slug)
    if not ids:
        return []
    out = []
    for saison in saisons:
        for tid in ids:
            d = curl_json(
                f"https://site.api.espn.com/apis/site/v2/sports/{slug}/teams/{tid}/schedule?season={saison}",
                timeout=25,
            )
            if not d:
                continue
            events = d.get("events") or []
            fake = {"events": events}
            out.extend(extraire_espn_events(fake, sport, ligue, table, completed_only=True))
            time.sleep(0.05)
    vus, uniq = set(), []
    for m in out:
        cle = (m["date"], m["home"], m["away"])
        if cle in vus or not m.get("hg") or m.get("ag") is None:
            continue
        vus.add(cle)
        uniq.append(m)
    log(f"    ESPN calendriers {ligue} : {len(uniq)} matchs ({len(ids)} équipes)")
    return uniq


def espn_historique_recent(annees=4) -> dict:
    """Ajoute les saisons récentes (post-archive SBR) via ESPN, si joignable."""
    auj = date.today()
    out = {"NBA": [], "NHL": [], "WNBA": [], "Euroleague": []}
    probe = espn_scoreboard("basketball/nba", auj)
    if probe is None:
        log("  ESPN injoignable ici — on s'appuie sur les archives GitHub.")
        return out
    saisons = [auj.year - i for i in range(annees)]
    out["NBA"] = espn_depuis_calendriers("basket", "NBA", ESPN_BASKET["NBA"], NBA_CANON, saisons)
    out["NHL"] = espn_depuis_calendriers("hockey", "NHL", ESPN_HOCKEY["NHL"], NHL_CANON, saisons)
    # WNBA / Euroleague : 90 derniers jours seulement (le jour-par-jour est coûteux)
    debut_court = auj - timedelta(days=90)
    out["WNBA"] = espn_historique("basket", "WNBA", ESPN_BASKET["WNBA"], {}, debut_court, auj, pause=0.05)
    out["Euroleague"] = espn_historique("basket", "Euroleague", ESPN_BASKET["Euroleague"], {},
                                        debut_court, auj, pause=0.05)
    return out


# --------------------------------------------------------------------------- tennis
def charger_atp_sackmann() -> list:
    dossier = DATA / "atp"
    if not dossier.exists():
        return []
    out = []
    for f in sorted(dossier.glob("atp_matches_*.csv")):
        try:
            with open(f, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    td = (r.get("tourney_date") or "").strip()
                    if len(td) == 8 and td.isdigit():
                        d = f"{td[:4]}-{td[4:6]}-{td[6:8]}"
                    else:
                        d = ""
                    w = (r.get("winner_name") or "").strip()
                    l = (r.get("loser_name") or "").strip()
                    if not w or not l:
                        continue
                    out.append({
                        "sport": "tennis", "ligue": "ATP", "date": d,
                        "winner": w, "loser": l,
                        "surface": r.get("surface") or "Hard",
                        "best_of": r.get("best_of") or 3,
                        "wsets": r.get("winner_id") and None,  # placeholder
                        "score": r.get("score"),
                        "wrank": r.get("winner_rank"), "lrank": r.get("loser_rank"),
                        "tournoi": r.get("tourney_name"),
                        "round": r.get("round"),
                        "source": "Sackmann",
                    })
        except OSError:
            continue
    return out


def _parse_sets(score: str):
    if not score or "RET" in score.upper() or "W/O" in score.upper():
        return None, None
    w = l = 0
    for part in str(score).replace(",", " ").split():
        core = part.split("(")[0]
        if "-" not in core:
            continue
        try:
            a, b = core.split("-", 1)
            a, b = int(a), int(b)
        except ValueError:
            continue
        if a > b:
            w += 1
        elif b > a:
            l += 1
    return w, l


def charger_tennis_data() -> list:
    """ATP + WTA depuis tennis-data.co.uk (années récentes)."""
    auj = date.today()
    out = []
    for annee in range(auj.year - 5, auj.year + 1):
        for ligue, url_c, url_x in (
            ("ATP", TD_ATP.format(y=annee), TD_ATP_XLSX.format(y=annee)),
            ("WTA", TD_WTA.format(y=annee), TD_WTA_XLSX.format(y=annee)),
        ):
            dest = DATA / f"td_{ligue}_{annee}.csv"
            raw = None
            if not dest.exists():
                raw = _curl(url_c, dest)
                if raw is None:
                    x = DATA / f"td_{ligue}_{annee}.xlsx"
                    xb = _curl(url_x, x)
                    if xb and x.exists():
                        # conversion xlsx → csv si openpyxl est là ; sinon on ignore
                        try:
                            import openpyxl  # noqa: F401
                            _xlsx_to_csv(x, dest)
                        except Exception:
                            pass
            if dest.exists():
                out.extend(_lire_tennis_data_csv(dest, ligue))
    return out


def _xlsx_to_csv(src: Path, dest: Path):
    import openpyxl
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return
    with open(dest, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(["" if c is None else c for c in r])


def _lire_tennis_data_csv(chemin: Path, ligue: str) -> list:
    out = []
    try:
        with open(chemin, encoding="latin-1", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                w = (r.get("Winner") or "").strip()
                l = (r.get("Loser") or "").strip()
                if not w or not l:
                    continue
                d = (r.get("Date") or "").strip()
                iso = ""
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
                    try:
                        iso = datetime.strptime(d, fmt).date().isoformat()
                        break
                    except ValueError:
                        continue
                bo = 5 if (r.get("Best of") or r.get("BestOf") or "3") in ("5", "5.0") else 3
                out.append({
                    "sport": "tennis", "ligue": ligue, "date": iso,
                    "winner": w, "loser": l,
                    "surface": r.get("Surface") or "Hard",
                    "best_of": bo,
                    "wrank": r.get("WRank"), "lrank": r.get("LRank"),
                    "tournoi": r.get("Tournament") or r.get("Location"),
                    "round": r.get("Round"),
                    "cote_w": _num(r.get("PSW") or r.get("B365W") or r.get("AvgW")),
                    "cote_l": _num(r.get("PSL") or r.get("B365L") or r.get("AvgL")),
                    "source": "tennis-data.co.uk",
                })
    except OSError:
        pass
    return out


def fusionner_tennis(sackmann: list, td: list) -> list:
    """tennis-data (plus récent, avec cotes) prioritaire ; Sackmann complète."""
    vus = set()
    out = []
    def cle(m):
        return (m.get("date"), _norme(m.get("winner")), _norme(m.get("loser")))
    for m in td + sackmann:
        c = cle(m)
        if not c[1] or not c[2] or c in vus:
            continue
        vus.add(c)
        ws, ls = _parse_sets(m.get("score") or "")
        m["wsets"] = ws
        m["lsets"] = ls
        out.append(m)
    out.sort(key=lambda x: x.get("date") or "")
    return out


def _norme(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if c.isalnum()).lower()
