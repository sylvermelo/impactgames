"""
MISE À JOUR COMPLÈTE — le script que GitHub exécute tout seul, toutes les 3 h
================================================================================
Enchaîne les quatre étapes, dans l'ordre, sans jamais tout casser :

    1. sources.py        télécharge ce qui a changé (3 sports, isolés)
    2. entraine.py       ré-entraîne les moteurs
    3. maj_calendrier.py récupère les 8 prochains jours et les fait analyser
    4. genere_app.py     reconstruit le fichier HTML autonome

Trois règles héritées du projet foot, toutes les trois gagnées à la dure :

  · **Une source injoignable ne touche à rien.** Les données existantes restent
    utilisables, l'application continue d'afficher la dernière version saine.
  · **Un sport qui échoue n'efface pas les autres.** Chaque section est isolée.
  · **On ne publie jamais un fichier vide.** `genere_app.py` refuse d'écrire si
    aucun modèle n'existe, et le workflow vérifie la taille avant de publier.

Usage :
    python3 maj.py             mise à jour complète
    python3 maj.py --check     regarde seulement s'il y a du nouveau
    python3 maj.py tennis      un seul sport
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
LOG = DATA / "maj.log"
APP = RACINE / "impactgames-autonome.html"

SPORTS = ("tennis", "hockey", "basket")


def log(msg: str, niveau: str = "INFO") -> None:
    ligne = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} [{niveau}] {msg}"
    print(ligne, flush=True)
    try:
        DATA.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
        if LOG.stat().st_size > 400_000:            # on garde le journal lisible
            dernier = LOG.read_text(encoding="utf-8").splitlines()[-500:]
            LOG.write_text("\n".join(dernier) + "\n", encoding="utf-8")
    except OSError:
        pass


def lancer(script: str, duree: str, *args: str) -> bool:
    """Lance un script fils. Un échec est signalé mais n'arrête pas la suite."""
    log(f"→ {script} {' '.join(args)} ({duree})")
    t0 = time.time()
    r = subprocess.run([sys.executable, str(RACINE / script), *args],
                       cwd=str(RACINE), capture_output=True, text=True)
    for ligne in (r.stdout or "").strip().splitlines():
        log(f"    {ligne}")
    if r.returncode != 0:
        log(f"{script} a ÉCHOUÉ (code {r.returncode}) : "
            f"{(r.stderr or '').strip()[-500:]}", "ERROR")
        return False
    log(f"  {script} terminé en {time.time() - t0:.0f} s")
    return True


def verifier_app() -> bool:
    """Garde-fou avant publication : un fichier anormal ne doit JAMAIS partir.

    Un fichier sain pèse entre 40 Ko (un seul sport, calendrier vide) et 8 Mo.
    En dessous, quelque chose s'est mal passé ; au-dessus, on a probablement
    sérialisé des données brutes par erreur.
    """
    if not APP.exists():
        log("impactgames-autonome.html absent", "ERROR")
        return False
    taille = APP.stat().st_size
    log(f"  taille du fichier : {taille / 1024:.0f} Ko")
    if taille < 40_000:
        log("fichier anormalement petit : publication à éviter", "ERROR")
        return False
    if taille > 8_000_000:
        log("fichier anormalement gros : publication à éviter", "ERROR")
        return False
    contenu = APP.read_text(encoding="utf-8", errors="ignore")
    if "const DATA = " not in contenu:
        log("données absentes du fichier", "ERROR")
        return False
    if "/*__DATA__*/" in contenu:
        log("l'espace réservé n'a pas été remplacé", "ERROR")
        return False
    log("  vérifications passées")
    return True


def main() -> int:
    args = sys.argv[1:]
    cibles = [a for a in args if a in SPORTS] or list(SPORTS)

    log("=" * 66)
    log(f"MISE À JOUR — impactgames — {', '.join(cibles)}")

    # 1. données -------------------------------------------------------------
    from sources import tout_mettre_a_jour
    res = tout_mettre_a_jour(tuple(cibles))
    for sport, r in res.items():
        if r.get("erreur"):
            log(f"  {sport} : {r['erreur']} — les données existantes sont conservées",
                "WARN")
        else:
            cle = "fichiers" if sport == "tennis" else "matchs"
            log(f"  {sport} : {r.get(cle, 0)} élément(s) mis à jour")

    if "--check" in args:
        log("mode --check : aucune autre étape exécutée")
        return 0

    # 2. entraînement --------------------------------------------------------
    if not lancer("entraine.py", "≈1 min", *cibles):
        log("entraînement échoué : l'ancienne application reste en place", "ERROR")
        return 1

    # 3. calendrier ----------------------------------------------------------
    # Étape séparée et tolérante : hors saison, ou si ESPN/NHL sont injoignables,
    # on garde le calendrier précédent plutôt que de publier une app vide.
    if not lancer("maj_calendrier.py", "≈1 min"):
        log("calendrier non reconstruit : le précédent est conservé", "WARN")

    # 4. application ---------------------------------------------------------
    if not lancer("genere_app.py", "≈2 s"):
        log("génération de l'application échouée", "ERROR")
        return 1

    return 0 if verifier_app() else 1


if __name__ == "__main__":
    sys.exit(main())
