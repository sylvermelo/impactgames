"""
Mise à jour automatique — à lancer tous les jours, ou par GitHub Actions.

  python3 maj.py          télécharge, entraîne si besoin, régénère l'app
  python3 maj.py --check  inspection seulement
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
LOG = DATA / "maj.log"
APP = RACINE / "impactgames-autonome.html"


def log(msg, niveau="INFO"):
    ligne = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} [{niveau}] {msg}"
    print(ligne, flush=True)
    try:
        DATA.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
        if LOG.exists() and LOG.stat().st_size > 400_000:
            lignes = LOG.read_text(encoding="utf-8").splitlines()[-500:]
            LOG.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    except OSError:
        pass


def lancer(script, duree):
    log(f"→ {script} ({duree})")
    t0 = dt.datetime.now()
    r = subprocess.run([sys.executable, str(RACINE / script)],
                       cwd=str(RACINE), capture_output=True, text=True)
    if r.returncode != 0:
        log(f"{script} a ÉCHOUÉ : {(r.stderr or r.stdout or '')[-800:]}", "ERROR")
        if r.stdout:
            log(r.stdout[-1200:], "ERROR")
        return False
    if r.stdout:
        for ligne in r.stdout.strip().splitlines()[-12:]:
            log("  " + ligne)
    log(f"  {script} terminé en {(dt.datetime.now()-t0).seconds} s")
    return True


def main():
    args = set(sys.argv[1:])
    log("=" * 62)
    log("MISE À JOUR — impactgames (basket · hockey · tennis)")
    DATA.mkdir(exist_ok=True)

    if "--check" in args:
        log("mode --check : on vérifie seulement la présence des archives")
        ok = (DATA / "nba_archive_10Y.json").exists() and (DATA / "modeles.json").exists()
        log("archives et modèles présents" if ok else "il manque des fichiers — lancer sans --check")
        return 0 if ok else 2

    # 1. archives GitHub + ESPN + tennis-data + entraînement
    if not lancer("entraine.py", "≈1 à 4 min"):
        if not (DATA / "modeles.json").exists():
            log("pas de modèle existant, abandon", "ERROR")
            return 1
        log("entraînement échoué : on conserve le modèle précédent", "WARN")

    # 2. calendrier ESPN (même si l'entraînement a utilisé un cache)
    try:
        import json as _json
        with open(DATA / "modeles.json", encoding="utf-8") as f:
            db = _json.load(f)
        os.chdir(RACINE)
        import calendrier as CAL
        journal = CAL.appliquer(db)
        (DATA / "modeles.json").write_text(
            _json.dumps(db, ensure_ascii=False), encoding="utf-8")
        src = journal.get("sources") or {}
        log(f"calendrier : {journal.get('total', 0)} matchs "
            f"(ESPN {src.get('ESPN', 0)}) | {journal.get('statut')}")
    except Exception as e:
        log(f"calendrier : {e}", "WARN")

    # 3. fichier autonome
    if not lancer("genere_app.py", "≈2 s"):
        log("génération du fichier autonome échouée", "ERROR")
        return 1

    log("mise à jour terminée")
    return 0


if __name__ == "__main__":
    sys.exit(main())
