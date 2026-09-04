"""
Serveur de l'application IMPACT GAMES.

Stdlib uniquement (http.server). Les modèles sont pré-entraînés
dans data/modeles.json → réponse instantanée.
"""
from __future__ import annotations

import datetime
import gzip
import io
import json
import os
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import moteurs as M

PORT = int(os.environ.get("PORT", 8000))
RACINE = os.path.dirname(os.path.abspath(__file__))
CHEMIN_DB = os.path.join(RACINE, "data", "modeles.json")

with open(CHEMIN_DB, encoding="utf-8") as f:
    DB = json.load(f)


def ligue(sport, div):
    return ((DB.get("sports") or {}).get(sport) or {}).get("ligues", {}).get(div)


def pronostic(sport, div, home, away, extra=None):
    extra = extra or {}
    L = ligue(sport, div)
    if not L:
        return None
    if sport == "basket":
        p = M.pronostic_basket(L, home, away)
    elif sport == "hockey":
        p = M.pronostic_hockey(L, home, away)
    elif sport == "tennis":
        p = M.pronostic_tennis(L, home, away,
                               surface=extra.get("surface") or "Hard",
                               best_of=int(extra.get("best_of") or 3))
    else:
        return None
    if not p:
        return None
    p["ligue"] = div
    p["sport"] = sport
    # comparaison marché
    for fx in DB.get("fixtures") or []:
        if (fx.get("sport") == sport and fx.get("div") == div
                and fx.get("home") == home and fx.get("away") == away):
            c1, c2 = fx.get("cote_1"), fx.get("cote_2")
            dv = M.devig(c1, c2) if c1 and c2 else None
            if dv:
                p["marche"] = {
                    "victoire_1": round(dv[0], 4), "victoire_2": round(dv[1], 4),
                    "cote_1": c1, "cote_2": c2,
                    "ecart_1": round(p["victoire_1"] - dv[0], 4),
                    "ecart_2": round(p["victoire_2"] - dv[1], 4),
                    "ou_line": fx.get("ou_line") or fx.get("total"),
                }
            p["date"] = fx.get("date")
            p["heure"] = fx.get("heure")
            break
    return p


def api_ligues():
    out = []
    for sport, sp in (DB.get("sports") or {}).items():
        for div, L in (sp.get("ligues") or {}).items():
            n = len(L.get("equipes_actuelles") or L.get("joueurs") or {})
            out.append({
                "sport": sport, "div": div, "nom": L.get("nom", div),
                "pays": L.get("pays"), "saison": L.get("saison"),
                "n": n, "n_historique": L.get("n_historique"),
                "dernier_match": L.get("dernier_match"),
                "points_moy": L.get("points_moy") or L.get("buts_moy"),
            })
    ordre = {"basket": 0, "hockey": 1, "tennis": 2}
    return sorted(out, key=lambda x: (ordre.get(x["sport"], 9), x["nom"]))


def api_classement(sport, div):
    L = ligue(sport, div)
    if not L:
        return None
    if sport == "tennis":
        rows = []
        for nom, j in (L.get("joueurs") or {}).items():
            rows.append({
                "equipe": nom, "elo": j.get("elo"), "elo_hard": j.get("elo_hard"),
                "elo_clay": j.get("elo_clay"), "elo_grass": j.get("elo_grass"),
                "n": j.get("n"), "victoires": j.get("victoires"),
                "rank": j.get("rank"), "dernier": j.get("dernier"),
                "puissance": j.get("elo"),
                "confiance": "haute" if (j.get("n") or 0) >= 40 else
                             "moyenne" if (j.get("n") or 0) >= 15 else "faible",
            })
        rows.sort(key=lambda r: -(r.get("elo") or 0))
        for i, r in enumerate(rows):
            r["rang"] = i + 1
        return {"ligue": L["nom"], "sport": "tennis", "equipes": rows[:200],
                "n_historique": L.get("n_historique"), "dernier_match": L.get("dernier_match")}
    rows = []
    for t in L.get("equipes_actuelles") or []:
        f = (L.get("forces") or {}).get(t)
        s = (L.get("stats") or {}).get(t) or {}
        if not f:
            continue
        ne = f.get("n_eff") or 0
        conf = "haute" if ne >= 40 else "moyenne" if ne >= 18 else "faible"
        rows.append({"equipe": t, "attaque": f["att"], "defense": f["dfn"],
                     "puissance": f.get("puissance"), "n_eff": ne,
                     "n_brut": f.get("n_brut"), "confiance": conf, **s})
    rows.sort(key=lambda r: -(r.get("puissance") or 0))
    for i, r in enumerate(rows):
        r["rang"] = i + 1
    return {
        "ligue": L.get("nom"), "sport": sport, "pays": L.get("pays"),
        "saison": L.get("saison"), "n_historique": L.get("n_historique"),
        "dernier_match": L.get("dernier_match"), "equipes": rows,
        "mu_home": L.get("mu_home"), "mu_away": L.get("mu_away"),
        "gamma": L.get("gamma"), "s_away": L.get("s_away"), "rho": L.get("rho"),
        "sigma_margin": L.get("sigma_margin"), "sigma_total": L.get("sigma_total"),
    }


def api_matchs():
    auj = datetime.date.today().isoformat()
    out = []
    for fx in DB.get("fixtures") or []:
        if (fx.get("date") or "") < auj:
            continue
        sport, div = fx.get("sport"), fx.get("div") or fx.get("ligue")
        extra = {"surface": fx.get("surface"), "best_of": fx.get("best_of") or 3}
        p = pronostic(sport, div, fx.get("home"), fx.get("away"), extra)
        L = ligue(sport, div)
        try:
            delta = (datetime.date.fromisoformat(fx["date"]) - datetime.date.today()).days
        except (ValueError, TypeError):
            delta = 0
        item = {
            "sport": sport, "div": div,
            "ligue": (L or {}).get("nom") or div,
            "pays": (L or {}).get("pays") or "",
            "date": fx.get("date"), "heure": fx.get("heure"),
            "home": fx.get("home"), "away": fx.get("away"),
            "source": fx.get("source") or "ESPN",
            "cote_1": fx.get("cote_1"), "cote_2": fx.get("cote_2"),
            "ou_line": fx.get("ou_line") or fx.get("total"),
            "surface": fx.get("surface"), "best_of": fx.get("best_of"),
            "tournoi": fx.get("tournoi"),
            "disponible": p is not None,
            "jour_delta": delta,
            "jour": ("Aujourd'hui" if delta == 0 else "Demain" if delta == 1
                     else f"Dans {delta} jours"),
        }
        if p:
            item.update({
                "p1": p["victoire_1"], "pX": p.get("nul") or 0, "p2": p["victoire_2"],
                "confiance": (p.get("fiabilite") or {}).get("niveau"),
                "over": p.get("over"), "under": p.get("under"),
                "lambda_home": p.get("lambda_home"), "lambda_away": p.get("lambda_away"),
            })
            if sport == "basket":
                item["points"] = p.get("points_attendus")
                item["marge"] = p.get("marge")
                item["over_ref"] = p.get("over_ref")
                item["under_ref"] = p.get("under_ref")
                item["line_totale"] = p.get("line_totale")
                item["spread"] = p.get("spread")
                item["ecart_10_home"] = p.get("ecart_10_home")
            elif sport == "hockey":
                item["buts"] = p.get("buts_attendus")
                item["over55"] = (p.get("over") or {}).get("5.5")
                item["btts"] = p.get("btts_oui")
                item["puck_home"] = p.get("puck_home")
                item["scores_top"] = p.get("scores_top")
                item["regulation_X"] = p.get("regulation_X")
            elif sport == "tennis":
                item["sets"] = p.get("sets")
                item["jeux"] = p.get("jeux_attendus")
                item["elo_1"] = p.get("elo_1")
                item["elo_2"] = p.get("elo_2")
                item["straight"] = p.get("straight_sets_1")
            m = p.get("marche")
            if m:
                item["ecart_1"] = m.get("ecart_1")
                item["ecart_2"] = m.get("ecart_2")
                item["meilleur_ecart"] = max((m.get("ecart_1") or 0, m.get("ecart_2") or 0),
                                             key=abs)
                item["meilleur_pari"] = "1" if (m.get("ecart_1") or 0) >= (m.get("ecart_2") or 0) else "2"
        out.append(item)
    out.sort(key=lambda x: (x.get("date") or "9999", x.get("heure") or "", x.get("sport") or ""))
    return out


def api_conseils(seuil=0.70, sport=None):
    seuil = float(seuil)
    jours = {}
    for m in api_matchs():
        if sport and m.get("sport") != sport:
            continue
        if not m.get("disponible"):
            continue
        cands = [("1", m.get("p1")), ("2", m.get("p2"))]
        if m["sport"] == "basket":
            cands += [("over", m.get("over_ref")), ("under", m.get("under_ref"))]
            if m.get("over"):
                for k, v in m["over"].items():
                    cands.append((f"over {k}", v))
                for k, v in (m.get("under") or {}).items():
                    cands.append((f"under {k}", v))
        elif m["sport"] == "hockey":
            o, u = m.get("over") or {}, m.get("under") or {}
            cands += [("over 5.5", o.get("5.5")), ("under 5.5", u.get("5.5")),
                      ("over 6.5", o.get("6.5")), ("under 6.5", u.get("6.5")),
                      ("les deux marquent", m.get("btts")),
                      ("puck line -1.5", m.get("puck_home"))]
        elif m["sport"] == "tennis":
            sets = m.get("sets") or {}
            cands += [("sets 2-0", sets.get("2-0") or sets.get("3-0")),
                      ("sets 2-1", sets.get("2-1") or sets.get("3-1")),
                      (f"over 22.5 jeux", (m.get("over") or {}).get("22.5")),
                      (f"under 22.5 jeux", (m.get("under") or {}).get("22.5"))]
        cands = [(k, v) for k, v in cands if v is not None]
        if not cands:
            continue
        opt, p = max(cands, key=lambda z: z[1])
        if p < seuil:
            continue
        item = {
            "sport": m["sport"], "div": m["div"], "ligue": m["ligue"],
            "date": m["date"], "heure": m["heure"], "jour": m["jour"],
            "jour_delta": m["jour_delta"], "home": m["home"], "away": m["away"],
            "option": opt, "p": round(p, 4),
            "cote_juste": round(1 / p, 2) if p else None,
            "confiance": m.get("confiance"),
            "cote_marche": m.get("cote_1") if opt == "1" else m.get("cote_2") if opt == "2" else None,
        }
        jours.setdefault(m["jour_delta"], []).append(item)
    liste = []
    for delta in sorted(jours):
        sel = sorted(jours[delta], key=lambda x: -x["p"])
        liste.append({"jour": sel[0]["jour"], "jour_delta": delta,
                      "date": sel[0]["date"], "nb": len(sel), "selections": sel})
    return {"seuil": seuil, "jours": liste,
            "note": "Probabilités du moteur statistique (normale / Poisson / Elo). "
                    "Une option à 75 % se réalise environ 3 fois sur 4 en moyenne, "
                    "pas à chaque fois. Rentabilité face aux cotes non démontrée "
                    "(onglet Fiabilité)."}


def api_extremes(sport="basket"):
    ms = [m for m in api_matchs() if m.get("sport") == sport and m.get("disponible")]
    if sport == "basket":
        ms.sort(key=lambda m: -(m.get("points") or 0))
        haut, bas = ms[:12], list(reversed(ms))[:12]
        return {"sport": sport, "plus_prolifiques": haut, "plus_fermes": bas,
                "cle": "points"}
    if sport == "hockey":
        ms.sort(key=lambda m: -(m.get("buts") or 0))
        return {"sport": sport, "plus_prolifiques": ms[:12],
                "plus_fermes": list(reversed(ms))[:12], "cle": "buts"}
    ms.sort(key=lambda m: abs((m.get("p1") or 0.5) - 0.5), reverse=True)
    return {"sport": sport, "plus_prolifiques": ms[:12],
            "plus_fermes": list(reversed(ms))[:12], "cle": "p1"}


def api_bilan():
    b = DB.get("bilan") or {}
    meta = DB.get("meta") or {}
    return {
        "volume": meta,
        "par_sport": b.get("par_sport") or {},
        "sources": meta.get("sources") or [],
        "protocole": "Backtest walk-forward par saison (basket, hockey) ; "
                     "Elo en ligne (tennis). Aucune donnée postérieure au match prédit.",
        "verdict": "Les probabilités sont calibrées (l'onglet montre l'écart annoncé/réalisé). "
                   "Le marché (cotes de clôture) reste généralement devant. "
                   "Outil d'analyse, pas une machine à gains.",
        "avertissement": "Aucun modèle ne garantit de gain. Le jeu d'argent peut créer une dépendance.",
        "genere_le": DB.get("genere_le"),
        "calendrier": DB.get("calendrier_log") or {},
    }


_MAJ = {"etat": "arrete", "log": "", "fin": None}
_MAJ_VERROU = threading.Lock()


def _lancer_maj():
    global DB
    try:
        import subprocess
        p = subprocess.run([sys.executable, os.path.join(RACINE, "maj.py")],
                           capture_output=True, text=True, timeout=1800, cwd=RACINE)
        _MAJ["log"] = ((p.stdout or "")[-2000:] + (p.stderr or "")[-800:])
        with open(CHEMIN_DB, encoding="utf-8") as f:
            DB = json.load(f)
        _MAJ["etat"] = "termine"
    except Exception as e:
        _MAJ["log"] = str(e)
        _MAJ["etat"] = "erreur"
    _MAJ["fin"] = datetime.datetime.now().isoformat(timespec="seconds")


def api_refresh():
    with _MAJ_VERROU:
        if _MAJ["etat"] == "en_cours":
            return {"etat": "en_cours"}
        _MAJ["etat"] = "en_cours"
        threading.Thread(target=_lancer_maj, daemon=True).start()
        return {"etat": "demarre"}


def api_maj():
    mtime = None
    try:
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(CHEMIN_DB)).isoformat(timespec="minutes")
    except OSError:
        pass
    return {"etat": _MAJ["etat"], "fin": _MAJ["fin"], "log": (_MAJ["log"] or "")[-1200:],
            "calendrier": DB.get("calendrier_log") or {}, "genere_le": mtime}


def _q(q, k, default=""):
    v = q.get(k, [default])
    return v[0] if v else default


ROUTES = {
    "/api/ligues": lambda q: api_ligues(),
    "/api/matchs": lambda q: api_matchs(),
    "/api/conseils": lambda q: api_conseils(float(_q(q, "seuil", "0.70")), _q(q, "sport") or None),
    "/api/classement": lambda q: api_classement(_q(q, "sport"), _q(q, "div")),
    "/api/pronostic": lambda q: pronostic(_q(q, "sport"), _q(q, "div"),
                                          _q(q, "home"), _q(q, "away"),
                                          {"surface": _q(q, "surface", "Hard"),
                                           "best_of": _q(q, "best_of", "3")}),
    "/api/extremes": lambda q: api_extremes(_q(q, "sport", "basket")),
    "/api/bilan": lambda q: api_bilan(),
    "/api/refresh": lambda q: api_refresh(),
    "/api/maj": lambda q: api_maj(),
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype, gz=False):
        raw = body.encode() if isinstance(body, str) else body
        hdrs = {"Content-Type": ctype, "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": "*", "Content-Length": str(len(raw))}
        if gz:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as g:
                g.write(raw)
            raw = buf.getvalue()
            hdrs["Content-Encoding"] = "gzip"
            hdrs["Content-Length"] = str(len(raw))
        try:
            self.send_response(code)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        gz = "gzip" in self.headers.get("Accept-Encoding", "")
        if u.path in ("/", "/index.html"):
            p = os.path.join(RACINE, "static", "index.html")
            if os.path.exists(p):
                return self._send(200, open(p, "rb").read(), "text/html; charset=utf-8", gz)
            return self._send(404, "index.html manquant", "text/plain")
        if u.path in ROUTES:
            try:
                r = ROUTES[u.path](q)
            except Exception as e:
                return self._send(500, json.dumps({"erreur": str(e)}), "application/json")
            if r is None:
                return self._send(404, json.dumps({"erreur": "introuvable"}), "application/json")
            return self._send(200, json.dumps(r, ensure_ascii=False),
                              "application/json; charset=utf-8", gz)
        return self._send(404, "route inconnue", "text/plain")


if __name__ == "__main__":
    class Serveur(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

        def handle_error(self, request, client_address):
            exc = sys.exc_info()[1]
            if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                return
            super().handle_error(request, client_address)

    srv = Serveur(("0.0.0.0", PORT), H)
    nlig = sum(len(sp.get("ligues") or {}) for sp in (DB.get("sports") or {}).values())
    print(f"IMPACT GAMES sur 0.0.0.0:{PORT}  |  {nlig} ligues  |  "
          f"{len(DB.get('fixtures') or [])} matchs à venir")
    srv.serve_forever()
