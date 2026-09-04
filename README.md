# Impact Games

Moteur statistique **basketball · hockey sur glace · tennis**.
Même philosophie que [pronos-foot](https://sylvermelo.github.io/pronos-foot/) :
des probabilités calculées, calibrées, honnêtes — pas une IA qui invente des scores.

**Site (après publication GitHub Pages) :** `https://sylvermelo.github.io/impactgames/`

## Ce que ça fait

| Sport | Modèle | Marchés |
|---|---|---|
| **Basket** (NBA, WNBA, Euroleague) | Attaque × défense, totaux ~ loi normale | Moneyline, spread, over/under points |
| **Hockey** (NHL) | Poisson bivarié + τ (Dixon-Coles) | Moneyline (avec OT), 1X2 réglementaire, puck line −1.5, O/U, BTTS |
| **Tennis** (ATP, WTA) | Elo global + surface, sets i.i.d. | Vainqueur, score en sets, over/under jeux |

Le robot s'entraîne sur des **résultats publics gratuits**, met à jour sa base tout seul
(GitHub Actions, toutes les 3 h), et analyse chaque événement à venir.

## Ce que ça ne fait pas

- Ça **ne prédit pas** le résultat d'un match. Ça donne des probabilités, souvent fausses sur un cas isolé.
- Ça **ne dit pas quoi parier**. Le backtest walk-forward ne bat pas les cotes de clôture.
- Ça ne connaît ni les blessés, ni les rotations, ni les forfeits.

C'est un **outil d'analyse**, pas une machine à gains.

## Lancer en local

```bash
chmod +x lancer.sh
./lancer.sh          # premier lancement : télécharge + entraîne, puis http://localhost:8000
python3 maj.py       # rafraîchir
python3 test_moteurs.py
```

Aucune bibliothèque Python obligatoire. Le fichier `impactgames-autonome.html`
s'ouvre d'un double-clic, hors-ligne.

## Sources (toutes gratuites, zéro clé API)

- Archive 10 ans NBA / NHL + cotes de clôture (Sportsbook Review, miroir GitHub)
- ESPN API publique — calendrier ~8 jours + saisons récentes
- tennis-data.co.uk (ATP / WTA + cotes) quand le site répond
- Miroir Sackmann ATP 2012-2022 en secours

## Mise à jour automatique

Le workflow `.github/workflows/maj.yml` tourne toutes les 3 heures sur GitHub,
ré-entraîne si les archives ont bougé, reconstruit le calendrier ESPN, et publie
le HTML autonome sur GitHub Pages.
