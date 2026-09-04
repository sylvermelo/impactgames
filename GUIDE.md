# Guide — Impact Games en 2 minutes

## Ouvrir l'application

### 1. Fichier autonome (le plus simple)

`impactgames-autonome.html`

1. Double-clic
2. Ça s'ouvre dans le navigateur

Pas de Python, pas d'internet, pas d'installation. Toutes les forces d'équipe,
les Elo tennis et le moteur sont *dans* le fichier.

### 2. Serveur local (données fraîches)

```bash
./lancer.sh
```

Puis `http://localhost:8000`.

### 3. Site web

Après activation de GitHub Pages : `https://sylvermelo.github.io/impactgames/`

Le site se met à jour tout seul toutes les 3 heures (heure de Cotonou : +1 h sur UTC).

## Les onglets

| Onglet | Usage |
|---|---|
| **Matchs à venir** | Calendrier ESPN, trié aujourd'hui → J+7. Clic = anatomie (toutes les options). |
| **Sélection conseillée** | Pour chaque événement, l'option la plus probable si elle dépasse le seuil (65-80 %). |
| **Mon coupon** | Combiné : le moteur multiplie les vraies probabilités, pas les cotes. |
| **Simulateur** | N'importe quelle paire d'une ligue couverte, même hors calendrier. |
| **Extrêmes** | Matchs les plus ouverts / les plus fermés. |
| **Classement** | Puissance (basket/hockey) ou Elo (tennis) — ce n'est pas le classement officiel. |
| **Fiabilité** | Backtest walk-forward, calibration, ROI. Y compris ce qui ne marche pas. |

Filtre **Tous / Basket / Hockey / Tennis** en haut à droite.

## Lire les chiffres

Les pourcentages sont le point fort : quand le moteur dit 65 %, l'événement
arrive autour de 65 % du temps (voir l'onglet Fiabilité, tableau de calibration).

Un **écart positif vs le marché** veut seulement dire que le moteur est plus
optimiste que les cotes. Sur le backtest, **le marché a généralement raison**.

**Confiance** haute / moyenne / faible = volume de matchs derrière chaque équipe
(ou joueur). Un promu NBA, un joueur ATP avec 10 matchs : méfiance.

## En septembre

NBA et NHL sont souvent en trêve (saison = octobre → juin). Le calendrier
peut être vide de ce côté : ce n'est pas un bug. Le tennis, lui, tourne
toute l'année. Classements et simulateur restent utilisables en toutes saisons.

## Rafraîchir

Le fichier autonome est une photo figée. Un navigateur ne peut pas ré-entraîner
le modèle (sécurité des navigateurs).

Pour des données fraîches :

```bash
python3 maj.py
```

Ou, en ligne : dépôt GitHub → onglet **Actions** → **Run workflow** (~4 min),
puis recharger la page.
