"""
INGESTION — d'où viennent les données, et comment on les rafraîchit
================================================================================
Trois sports, trois sources, toutes GRATUITES et SANS CLÉ API :

┌──────────┬──────────────────────────────────┬──────────────────────────────┐
│ Sport    │ Résultats (entraînement)         │ Calendrier à venir           │
├──────────┼──────────────────────────────────┼──────────────────────────────┤
│ Tennis   │ dépôt GitHub `Kadantte/tennis_atp`│ ESPN (tournois ATP)          │
│          │ fork de la base Jeff Sackmann     │                              │
│          │ (l'original a disparu en 2026)    │                              │
│ Hockey   │ api.nhle.com — API officielle     │ api-web.nhle.com/v1/schedule │
│          │ 75 698 matchs, sans clé           │                              │
│ Basket   │ stats.nba.com — endpoints publics │ ESPN (scoreboard NBA)        │
└──────────┴──────────────────────────────────┴──────────────────────────────┘

Aucune cote historique gratuite n'existe pour le hockey ni le basket : les
rapports de ces deux moteurs comparent donc au hasard et à des modèles de
référence, pas à Pinnacle. C'est écrit noir sur blanc plutôt que maquillé.

Règles de robustesse (reprises du projet foot, elles ont fait leurs preuves) :
  · on télécharge dans un fichier `.part` puis on déplace : jamais de CSV tronqué
  · une source injoignable ne touche à RIEN : les données existantes restent
  · chaque source échoue indépendamment des autres
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import shutil
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; impactgames/1.0)"}

# stats.nba.com refuse les requêtes sans en-têtes de navigateur
ENTETES_NBA = {**ENTETES,
               "Accept": "application/json, text/plain, */*",
               "Referer": "https://www.nba.com/",
               "Origin": "https://www.nba.com",
               "x-nba-stats-origin": "stats",
               "x-nba-stats-token": "true"}

# Source de secours du basket : le scoreboard ESPN. Vérifié le 2026-09-04 :
# il accepte une plage de dates (dates=20250217-20250218 renvoie bien
# « events: [] », les deux jours tombant pendant la pause du All-Star Game) et
# ne demande ni clé ni en-tête particulier.
#
# L'HÔTE COMPTE : depuis les serveurs de GitHub, site.api.espn.com répond 403
# (protection anti-robot) alors que site.web.api.espn.com répond 200 pour le
# même chemin. Mesuré par l'étape « Sonder les sources de basket » du workflow,
# résultat dans data/sonde.log du run 33914446553. Le User-Agent n'y change
# rien : le blocage porte sur l'adresse, pas sur l'en-tête.
ESPN_BASKET = ("https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/"
               "scoreboard?dates={a}-{b}&limit=100")
FENETRE_ESPN = 5              # 5 jours ≈ 75 matchs, sous la limite de 100
# 2 = saison régulière, 3 = playoffs. Le scoreboard ESPN renvoie AUSSI la
# pré-saison (1), la Summer League et le Rising Stars : sans ce filtre, la base
# contenait 56 « équipes » au lieu des 30 franchises NBA — dont GUANGZHOU,
# HAPOEL, REAL (clubs invités en pré-saison), EAST/WEST (Rising Stars) ou
# STRIPES, et le moteur leur attribuait des forces absurdes (rythme -46,5).
# C'est l'équivalent du SeasonType=Regular Season/Playoffs de stats.nba.com.
TYPES_SAISON_BASKET = (2, 3)
PAUSE_ESPN = 0.12             # politesse entre deux requêtes

ANNEES_TENNIS = range(2013, dt.date.today().year + 1)
SAISONS_HOCKEY = 6            # saisons NHL conservées
SAISONS_BASKET = 6            # saisons NBA conservées

# Budgets de temps PAR SOURCE. Sans eux, une API lente (stats.nba.com est
# notoirement capricieuse) mange tout le budget du job et les autres sports
# ne sont jamais traités.
BUDGET_HOCKEY = 180
BUDGET_BASKET = 240
BUDGET_TENNIS = 300
# Budget distinct pour le repli ESPN du basket : si on le partageait avec
# stats.nba.com, une source qui traîne laisserait zéro seconde au repli.
BUDGET_REPLI_BASKET = 180
MAX_PAGES = 12                # 12 × 1000 matchs : très au-delà du besoin réel


# Dernière erreur par URL. `stats.nba.com` échoue sans dire pourquoi dans les
# journaux (et ces journaux ne sont pas téléchargeables de partout) : on remonte
# donc le code HTTP exact dans le rapport d'exécution.
DERNIERES_ERREURS: list[str] = []

# Code HTTP du dernier appel (None si la requête n'a pas abouti). Sert à
# distinguer « l'hôte nous bloque » (403, inutile d'insister 300 fois) de
# « l'hôte est lent » (il faut réessayer).
DERNIER_CODE: int | None = None


def _get(url: str, entetes=None, timeout=45) -> bytes | None:
    global DERNIER_CODE
    DERNIER_CODE = None
    # La liste alimente le rapport d'exécution : on garde le début (la première
    # erreur est la plus parlante) et la fin, sans jamais croître sans limite.
    if len(DERNIERES_ERREURS) >= 40:
        del DERNIERES_ERREURS[10:-10]
    try:
        req = urllib.request.Request(url, headers=entetes or ENTETES)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            DERNIER_CODE = r.status
            return r.read()
    except urllib.error.HTTPError as e:
        DERNIER_CODE = e.code
        msg = f"HTTP {e.code} sur {url[:90]}"
        print(f"    ! {msg}")
        DERNIERES_ERREURS.append(msg)
        return None
    except Exception as e:
        msg = f"{type(e).__name__} sur {url[:90]} : {str(e)[:80]}"
        print(f"    ! {msg}")
        DERNIERES_ERREURS.append(msg)
        return None


def _ecrire_atomic(dest: Path, contenu: bytes, minimum=200) -> bool:
    if len(contenu) < minimum:
        print(f"    ! réponse trop courte ({len(contenu)} o), ignorée")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(contenu)
    shutil.move(str(tmp), str(dest))
    return True


# ==================================================================== TENNIS
def maj_tennis(dossier: Path = DATA) -> dict:
    """Télécharge les CSV ATP de l'archive Sackmann.

    Stratégie : une seule archive complète (`codeload.github.com`) plutôt que
    14 requêtes séparées. C'est plus rapide, plus poli avec GitHub, et ça
    évite l'état « moitié des années à jour ».
    """
    print("  tennis — archive Sackmann (fork Kadantte)")
    dossier.mkdir(parents=True, exist_ok=True)

    # L'archive pèse ~55 Mo : on ne la reprend que si le dépôt a bougé.
    # Une requête d'en-tête de quelques centaines d'octets remplace un
    # téléchargement de 55 Mo — c'est ce qui faisait durer l'étape 3 minutes.
    marqueur = dossier / ".version-tennis"
    url = "https://codeload.github.com/Kadantte/tennis_atp/tar.gz/refs/heads/master"
    version = _version_depot()
    deja_pret = (marqueur.exists() and version
                 and marqueur.read_text(encoding="utf-8").strip() == version
                 and any(dossier.glob("atp_matches_*.csv")))
    if deja_pret:
        n = len(list(dossier.glob("atp_matches_*.csv")))
        print(f"    dépôt inchangé ({version[:10]}) : {n} saisons déjà présentes")
        return {"sport": "tennis", "fichiers": n, "source": "github/inchange"}
    brut = _get(url, timeout=BUDGET_TENNIS)
    if brut is None:
        # repli : fichier par fichier, pour les petites mises à jour
        return _maj_tennis_fichier_par_fichier(dossier)

    n = 0
    with tarfile.open(fileobj=io.BytesIO(brut), mode="r:gz") as tf:
        for membre in tf.getmembers():
            nom = Path(membre.name).name
            if not (nom.startswith("atp_matches_") and nom.endswith(".csv")):
                continue
            if "_" in nom[len("atp_matches_"):-4]:
                continue          # on écarte qual_chall, futures, doubles
            annee = nom[len("atp_matches_"):-4]
            if not annee.isdigit() or int(annee) not in ANNEES_TENNIS:
                continue
            f = tf.extractfile(membre)
            if f is None:
                continue
            if _ecrire_atomic(dossier / nom, f.read()):
                n += 1
    if n and version:
        marqueur.write_text(version, encoding="utf-8")
    print(f"    {n} saisons ATP écrites")
    return {"sport": "tennis", "fichiers": n, "source": "github"}


def _version_depot() -> str | None:
    """Empreinte du dernier commit du dépôt de données tennis.

    Sert à décider s'il faut re-télécharger l'archive. Un échec renvoie None :
    dans ce cas on re-télécharge, ce qui est le comportement sûr.
    """
    import json as _json
    brut = _get("https://api.github.com/repos/Kadantte/tennis_atp/commits/master",
                {**ENTETES, "Accept": "application/vnd.github+json"}, timeout=25)
    if not brut:
        return None
    try:
        return _json.loads(brut).get("sha")
    except (ValueError, AttributeError):
        return None


def _maj_tennis_fichier_par_fichier(dossier: Path) -> dict:
    n = 0
    for a in ANNEES_TENNIS:
        url = (f"https://raw.githubusercontent.com/Kadantte/tennis_atp/"
               f"master/atp_matches_{a}.csv")
        brut = _get(url)
        if brut and _ecrire_atomic(dossier / f"atp_matches_{a}.csv", brut):
            n += 1
        time.sleep(0.2)
    print(f"    {n} saisons ATP écrites (mode fichier par fichier)")
    return {"sport": "tennis", "fichiers": n, "source": "github/fichier"}


# ==================================================================== HOCKEY
def _equipes_nhl() -> dict[int, str]:
    """id numérique NHL → code à trois lettres (MTL, BOS…)."""
    brut = _get("https://api.nhle.com/stats/rest/en/team?limit=100")
    if not brut:
        return {}
    try:
        rows = json.loads(brut)["data"]
    except (KeyError, json.JSONDecodeError):
        return {}
    out = {}
    for r in rows:
        code = r.get("triCode") or r.get("abbreviation")
        if code and r.get("id"):
            out[int(r["id"])] = code
    return out


def maj_hockey(dossier: Path = DATA, saisons: int = SAISONS_HOCKEY) -> dict:
    """Aspire la liste des matchs NHL saison régulière.

    L'endpoint renvoie toute l'histoire de la ligue paginée ; on filtre sur la
    saison et on ne garde que le type 2 (saison régulière).
    """
    print("  hockey — api.nhle.com")
    equipes = _equipes_nhl()
    if not equipes:
        print("    ! liste des équipes injoignable : rien n'est modifié")
        return {"sport": "hockey", "matchs": 0, "erreur": "equipes_injoignables",
                "diagnostic": list(DERNIERES_ERREURS[-4:])}

    aujourdhui = dt.date.today()
    # la saison NHL 2025-26 s'écrit 20252026 ; en septembre la nouvelle n'a pas
    # encore commencé, donc on part de la saison qui vient de se jouer
    debut = aujourdhui.year - (1 if aujourdhui.month >= 9 else 2)
    premiere = f"{debut - saisons + 1}{debut - saisons + 2}"

    # Les champs s'appellent `season` et `gameType` — PAS `seasonId` /
    # `gameTypeId`, que l'API rejette (« Invalid path 'seasonId' for 'Game' »).
    # Un filtre rejeté, c'est 75 698 matchs paginés au lieu de 4 000 : la
    # première exécution a tenu 25 minutes là-dessus.
    cayenne = urllib.parse.quote(f"season>={premiere} and gameType=2")
    lignes, depart, total = [], 0, None
    t_debut = time.time()
    while True:
        # garde-fous : ni la pagination ni une source lente ne doivent pouvoir
        # consommer tout le budget du job (25 min dans le workflow)
        if time.time() - t_debut > BUDGET_HOCKEY:
            print(f"    ! budget de {BUDGET_HOCKEY} s atteint, "
                  f"{depart} matchs récupérés")
            break
        if depart >= MAX_PAGES * 1000:
            print(f"    ! plafond de {MAX_PAGES} pages atteint")
            break
        url = ("https://api.nhle.com/stats/rest/en/game?"
               f"isGame=true&cayenneExp={cayenne}&limit=1000&start={depart}"
               "&sort=%5B%7B%22property%22%3A%22id%22%7D%5D")
        brut = _get(url, timeout=60)
        if not brut:
            break
        try:
            j = json.loads(brut)
        except json.JSONDecodeError:
            break
        total = j.get("total", 0)
        bloc = j.get("data", [])
        if not bloc:
            break
        lignes.extend(bloc)
        depart += len(bloc)
        if total is not None and depart >= total:
            break
        time.sleep(0.15)

    if not lignes:
        print("    ! aucun match reçu : le fichier existant est conservé")
        return {"sport": "hockey", "matchs": 0, "erreur": "aucun_match",
                "diagnostic": list(DERNIERES_ERREURS[-4:])}

    ecris = 0
    tampon = io.StringIO()
    w = csv.writer(tampon)
    w.writerow(["date", "saison", "domicile", "exterieur", "buts_dom",
                "buts_ext", "apres_reglement"])
    for g in lignes:
        hd, ha = equipes.get(int(g.get("homeTeamId", 0))), equipes.get(int(g.get("visitingTeamId", 0)))
        if not hd or not ha or hd == ha:
            continue
        d = str(g.get("gameDate", ""))[:10]
        if not d or d >= aujourdhui.isoformat():
            continue                      # pas encore joué
        bs, vs = g.get("homeScore"), g.get("visitingScore")
        if bs is None or vs is None or (bs == 0 and vs == 0):
            continue                      # reporté ou non saisi
        # `period` vaut 3 en fin de temps réglementaire, 4 en prolongation et
        # 5 après une fusillade : tout ce qui dépasse 3 a produit un but
        # décisif qu'il faudra retirer avant d'entraîner.
        apres = 1 if int(g.get("period") or 3) > 3 else 0
        w.writerow([d, g.get("season", ""), hd, ha, bs, vs, apres])
        ecris += 1

    if ecris:
        _ecrire_atomic(dossier / "nhl_matchs.csv", tampon.getvalue().encode("utf-8"))
    print(f"    {ecris} matchs NHL écrits (sur {len(lignes)} reçus)")
    return {"sport": "hockey", "matchs": ecris, "recus": len(lignes)}


# ==================================================================== BASKET
def _lignes_basket(par_match: dict) -> list[dict]:
    """Ne garde que les matchs complets (deux scores, deux équipes distinctes)."""
    lignes = [v for v in par_match.values()
              if {"date", "domicile", "exterieur", "pts_dom", "pts_ext"} <= set(v)
              and v["domicile"] != v["exterieur"]]
    lignes.sort(key=lambda v: v["date"])
    return lignes


def _maj_basket_espn(depart: dt.date, jusqu_a: dt.date, budget: float,
                     dossier: Path = DATA) -> dict:
    """Repli : lit le scoreboard ESPN, fenêtre de quelques jours par fenêtre.

    `stats.nba.com` renvoie 0 match dans le job GitHub (il bloque les requêtes
    qui ne viennent pas d'un navigateur). ESPN fournit les mêmes informations :
    score final, équipes, date, et le nombre de périodes — donc les
    prolongations. On part du plus récent vers le plus ancien, pour qu'une
    coupure de budget conserve d'abord les saisons utiles.
    """
    print("    → repli sur le scoreboard ESPN")
    par_match: dict[str, dict] = {}
    echantillon: bytes | None = None   # première réponse brute, pour diagnostic
    refus = 0                       # 403 consécutifs : l'hôte bloque ce serveur
    hors_saison = 0                 # pré-saison, Summer League, Rising Stars
    sans_type = 0                   # événements sans saison.type lisible
    b = jusqu_a
    while b >= depart and time.time() < budget:
        a = max(b - dt.timedelta(days=FENETRE_ESPN - 1), depart)
        if a.month in (7, 8, 9) and b.month in (7, 8, 9):
            b = a - dt.timedelta(days=1)
            continue                            # intersaison : aucun match
        url = ESPN_BASKET.format(a=a.strftime("%Y%m%d"), b=b.strftime("%Y%m%d"))
        brut = _get(url, timeout=20)
        if not brut:
            # Un 403 ne se soigne pas en insistant : les serveurs de GitHub sont
            # bloqués par la protection anti-robot. Trois refus d'affilée et on
            # arrête, au lieu de brûler 330 requêtes pour rien.
            refus = refus + 1 if DERNIER_CODE == 403 else 0
            if refus >= 3:
                print("    ! 403 à répétition : cet hôte bloque le serveur, "
                      "on arrête le repli")
                break
        if brut:
            refus = 0
            if echantillon is None:
                echantillon = brut
            try:
                evs = json.loads(brut).get("events", [])
            except (json.JSONDecodeError, AttributeError):
                evs = []
            for ev in evs:
                type_saison = (ev.get("season") or {}).get("type")
                if type_saison is None:
                    sans_type += 1        # on garde : mieux vaut un match de
                elif type_saison not in TYPES_SAISON_BASKET:
                    hors_saison += 1      # trop qu'une base vide
                    continue
                comps = ev.get("competitions") or []
                if not comps:
                    continue
                c0 = comps[0]
                etat = ((c0.get("status") or {}).get("type") or {})
                # « completed » est le champ habituel, « state: post » son
                # équivalent sur certaines variantes de l'API ESPN. Sans l'un
                # des deux on n'ose pas : un match en cours a déjà des scores
                # entiers, et l'avaler reviendrait à entraîner sur l'avenir.
                if not (etat.get("completed") is True
                        or etat.get("state") == "post"):
                    continue                    # match à venir ou en cours
                dom = ext = None
                for c in c0.get("competitors", []):
                    if c.get("homeAway") == "home":
                        dom = c
                    elif c.get("homeAway") == "away":
                        ext = c
                if not dom or not ext:
                    continue
                try:
                    pts_d, pts_e = int(dom.get("score")), int(ext.get("score"))
                except (TypeError, ValueError):
                    continue
                nom = lambda c: ((c.get("team") or {}).get("abbreviation") or "").strip()
                if not nom(dom) or not nom(ext) or nom(dom) == nom(ext):
                    continue
                date = str(ev.get("date") or "")[:10]
                if len(date) != 10:
                    continue
                annee = int(date[:4]) - (1 if int(date[5:7]) < 10 else 0)
                par_match[ev.get("id") or f"{date}-{nom(dom)}"] = {
                    "date": date, "saison": f"{annee}-{str(annee + 1)[-2:]}",
                    "domicile": nom(dom), "exterieur": nom(ext),
                    "pts_dom": pts_d, "pts_ext": pts_e}
        b = a - dt.timedelta(days=1)            # fenêtre suivante, sans chevauchement
        time.sleep(PAUSE_ESPN)
    if time.time() >= budget:
        print(f"    ! budget atteint, {len(par_match)} matchs récupérés")
    if hors_saison:
        print(f"    {hors_saison} événements hors saison régulière/playoffs écartés")
    if sans_type:
        # Si un jour ce nombre explose, c'est que la forme des données a changé
        # et que le filtre ne protège plus rien : il faut le savoir.
        print(f"    ! {sans_type} événements sans saison.type lisible (non filtrés)")
    if not par_match and echantillon:
        # L'hôte répond mais on ne comprend pas ce qu'il renvoie : on garde un
        # échantillon brut pour pouvoir lire la vraie forme des données, au lieu
        # de deviner pendant des heures.
        cible = dossier / "echantillon-espn.json"
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(echantillon[:6000])
        print(f"    ! 0 match lu alors que l'hôte répond : "
              f"échantillon écrit dans {cible.name}")
    return par_match


def maj_basket(dossier: Path = DATA, saisons: int = SAISONS_BASKET) -> dict:
    """Aspire les relevés d'équipe NBA via `leaguegamefinder`.

    Une requête par saison renvoie DEUX lignes par match (une par équipe) ; on
    les réassemble en une ligne « domicile vs extérieur » grâce à la colonne
    MATCHUP, qui vaut `BOS vs. LAL` à domicile et `BOS @ LAL` à l'extérieur.
    """
    print("  basket — stats.nba.com")
    aujourdhui = dt.date.today()
    depart = aujourdhui.year - (1 if aujourdhui.month >= 10 else 2)

    par_match: dict[str, dict] = {}
    t_debut = time.time()
    for k in range(saisons):
        if time.time() - t_debut > BUDGET_BASKET:
            print(f"    ! budget de {BUDGET_BASKET} s atteint, "
                  f"{len(par_match)} matchs récupérés")
            break
        y = depart - k
        saison = f"{y}-{str(y + 1)[-2:]}"
        for type_ in ("Regular Season", "Playoffs"):
            url = ("https://stats.nba.com/stats/leaguegamefinder?"
                   f"LeagueID=00&Season={saison}&SeasonType="
                   f"{urllib.parse.quote_plus(type_)}&PlayerOrTeam=T")
            # 25 s et non 60 : une source qui traîne ne doit pas manger le
            # budget du repli ESPN qui vient derrière.
            brut = _get(url, ENTETES_NBA, timeout=25)
            if not brut:
                continue
            try:
                j = json.loads(brut)
                rs = j["resultSets"][0]
                cols = rs["headers"]
                rows = rs["rowSet"]
            except (KeyError, IndexError, json.JSONDecodeError):
                continue
            ix = {c: i for i, c in enumerate(cols)}
            for r in rows:
                matchup = r[ix["MATCHUP"]]
                if " vs. " not in matchup and " @ " not in matchup:
                    continue
                a_domicile = " vs. " in matchup
                moi, adversaire = (matchup.split(" vs. ") if a_domicile
                                   else matchup.split(" @ "))
                cle = r[ix["GAME_ID"]]
                e = par_match.setdefault(cle, {})
                pts, date = r[ix["PTS"]], str(r[ix["GAME_DATE"]])[:10]
                if a_domicile:
                    e.update({"date": date, "saison": saison, "domicile": moi.strip(),
                              "exterieur": adversaire.strip(), "pts_dom": pts})
                else:
                    e.update({"date": date, "saison": saison, "domicile": adversaire.strip(),
                              "exterieur": moi.strip(), "pts_ext": pts})
            time.sleep(0.25)              # stats.nba.com limite le débit

    lignes = _lignes_basket(par_match)
    repli = False
    if not lignes:
        # stats.nba.com n'a rien donné : on tente ESPN avant d'abandonner.
        par_match = _maj_basket_espn(
            dt.date(depart - saisons + 1, 10, 1), aujourdhui,
            t_debut + BUDGET_BASKET + BUDGET_REPLI_BASKET, dossier)
        lignes = _lignes_basket(par_match)
        repli = True
    if not lignes:
        print("    ! aucun match reçu : le fichier existant est conservé")
        return {"sport": "basket", "matchs": 0, "erreur": "aucun_match",
                "diagnostic": list(DERNIERES_ERREURS[-4:])}

    tampon = io.StringIO()
    w = csv.writer(tampon)
    w.writerow(["date", "saison", "domicile", "exterieur", "pts_dom", "pts_ext"])
    for v in lignes:
        w.writerow([v["date"], v["saison"], v["domicile"], v["exterieur"],
                    v["pts_dom"], v["pts_ext"]])
    source = "espn" if repli else "stats.nba.com"
    # Un échantillon de diagnostic d'une exécution précédente n'a plus de raison
    # d'être là maintenant qu'on lit les matchs : le laisser traîner ferait
    # croire à un problème résolu.
    vieil_echantillon = dossier / "echantillon-espn.json"
    if vieil_echantillon.exists():
        vieil_echantillon.unlink()
    if not _ecrire_atomic(dossier / "nba_matchs.csv",
                          tampon.getvalue().encode("utf-8")):
        # Le fichier existant est conservé : il ne faut surtout pas annoncer
        # une mise à jour qui n'a pas eu lieu.
        return {"sport": "basket", "matchs": 0, "source": source,
                "erreur": "fichier_non_ecrit", "recus": len(lignes)}
    print(f"    {len(lignes)} matchs NBA écrits ({source})")
    return {"sport": "basket", "matchs": len(lignes), "recus": len(par_match),
            "source": source}


# ================================================================== orchestre
def tout_mettre_a_jour(sports=("tennis", "hockey", "basket")) -> dict:
    """Chaque source est isolée : si le hockey tombe, le tennis passe quand même."""
    DATA.mkdir(parents=True, exist_ok=True)
    res = {}
    for s in sports:
        try:
            if s == "tennis":
                res[s] = maj_tennis()
            elif s == "hockey":
                res[s] = maj_hockey()
            elif s == "basket":
                res[s] = maj_basket()
        except Exception as e:                # une source ne doit jamais tout casser
            print(f"    ! {s} : {type(e).__name__} {e}")
            res[s] = {"sport": s, "erreur": f"{type(e).__name__}: {e}"}
    return res


if __name__ == "__main__":
    print(json.dumps(tout_mettre_a_jour(), ensure_ascii=False, indent=1))
