#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -f data/modeles.json ]; then
  echo "Premier lancement : téléchargement des archives et entraînement…"
  python3 maj.py
fi
echo "Serveur → http://0.0.0.0:8000"
exec python3 serveur.py
