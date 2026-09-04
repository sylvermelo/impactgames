# Impact Games — moteur de pronostics multi-sports

Un moteur statistique qui s'entraîne seul sur des résultats **réels et gratuits**,
met à jour sa base en continu, et calcule les probabilités de chaque événement à
venir en **basket (NBA)**, **hockey sur glace (NHL)** et **tennis (ATP)**.

C'est le petit frère de [Pronos Foot](https://sylvermelo.github.io/pronos-foot/),
construit sur la même idée : **les mathématiques calculent, jamais une IA**.

---

## Ce que c'est — et ce que ce n'est pas

| C'est | Ce n'est pas |
|---|---|
| Un moteur statistique déterministe, testé et backtesté | Une IA qui « devine » des scores |
| Des probabilités, avec leur niveau de fiabilité affiché | Des pronostics garantis |
| Un outil d'analyse, gratuit, sans compte | Un site de paris |

**Aucun pari n'est pris ici.** Le jeu peut créer une dépendance.

---

## Ouvrir l'application

Deux façons, aucune installation :

1. **En ligne** — l'adresse GitHub Pages du dépôt (Settings → Pages), rafraîchie
   automatiquement toutes les 3 heures.
2. **Le fichier seul** — télécharge `impactgames-autonome.html`, ouvre-le dans un
   navigateur. Tout est dedans : les modèles, le calendrier, les pronostics.
   Ça marche dans un avion, sur téléphone, et tu peux l'envoyer par message.

---

## Comment ça tourne tout seul

```
toutes les 3 h, sur les serveurs de GitHub (gratuit, aucun ordinateur allumé)

  sources.py        télécharge ce qui a changé
       │            tennis → archive GitHub · hockey → api.nhle.com · basket → stats.nba.com puis ESPN
       ▼
  entraine.py       ré-entraîne les trois moteurs
       ▼
  maj_calendrier.py récupère les 8 prochains jours et les fait analyser
       ▼
  genere_app.py     reconstruit le fichier HTML autonome
       ▼
  publication GitHub Pages (seulement si les tests passent)
```

Trois règles, toutes héritées d'incidents réels sur le projet foot :

- **Une source injoignable ne touche à rien.** Les données existantes restent.
- **Un sport qui échoue n'efface pas les deux autres.** Chaque section est isolée.
- **On ne publie jamais un fichier suspect.** Taille, présence des données et
  suite de tests sont vérifiées avant publication.

---

## Les trois moteurs

Chaque sport a sa propre mathématique. Utiliser le même modèle partout serait
une faute :

| Sport | Modèle | Pourquoi celui-là |
|---|---|---|
| **Tennis** | Elo par surface + chaîne de Markov jeu → set → match | Un match de tennis est un empilement de points. On remonte la hiérarchie au lieu de deviner un score. |
| **Hockey** | Poisson bivarié attaques/défenses, correction Dixon-Coles | Score bas (≈ 6 buts) : comme au football, une matrice de scores suffit à dériver tous les marchés. |
| **Basket** | Normales sur le total et l'écart (force nette + rythme) | 220 points par match, pas de nul : la Poisson serait absurde. La force nette décide du vainqueur, le rythme décide du total. |

### Les marchés produits

- **Tennis** — vainqueur, score exact en sets, total de jeux, handicap de jeux
- **Hockey** — 1X2 à 60 minutes, moneyline (prolongation incluse), over/under,
  les deux marquent, blanchissage, handicap, score exact
- **Basket** — vainqueur, handicap, over/under total, prolongation, écart le plus probable

---

## Le relancer à la main

```bash
pip install -r requirements.txt
python3 maj.py                # mise à jour complète
python3 maj.py --check        # juste regarder s'il y a du nouveau
python3 backtest.py tennis    # mesurer ce que le moteur vaut vraiment
python3 -m unittest discover -s tests -v    # la suite de tests
node tests/test_app.js                      # vérifier que l'app s'affiche
```

---

## Ce que le moteur vaut — sans arrondi

Le rapport complet est dans l'onglet **Fiabilité** de l'application. En résumé,
sur **29 262 matchs de tennis ATP jamais servis à l'ajustement** :

| Mesure | Moteur | Elo seul | Hasard |
|---|---|---|---|
| Log-loss (plus bas = meilleur) | **0,6274** | 0,6268 | 0,6931 |
| Favori gagne | 63,9 % | — | 50 % |

Lecture honnête : sur le seul marché « qui gagne le match », le moteur fait
**jeu égal** avec un Elo par surface bien réglé. Sa valeur ajoutée est ailleurs —
il produit de façon cohérente les scores en sets, les totaux de jeux et les
handicaps, qu'un Elo seul ne sait pas calculer.

**Hockey et basket :** les moteurs sont entraînés et leurs estimateurs sont
validés sur données synthétiques à vérité connue. En revanche il n'existe
**aucune source gratuite de cotes historiques** pour la NHL ni la NBA : on ne
peut donc pas encore les comparer à un bookmaker, contrairement au football où
les cotes de clôture Pinnacle servent de juge de paix. C'est l'étape suivante,
et c'est dit ici plutôt que maquillé.

---

## Structure du dépôt

```
sports/
  commun.py     métriques partagées : log-loss, RPS, calibration, déviggage
  tennis.py     Elo par surface + chaîne de Markov
  hockey.py     Poisson bivarié + gestion prolongation/fusillade
  basket.py     normales total/écart (force nette + rythme)
sources.py      ingestion des trois sports
entraine.py     entraînement → data/modeles.json
maj_calendrier.py  8 prochains jours → data/calendrier.json
genere_app.py   → impactgames-autonome.html (l'application)
maj.py          orchestrateur des quatre étapes
backtest.py     mesure walk-forward de la qualité réelle
tests/          59 tests Python + test de rendu de l'application
CONCEPTION.md   les choix mathématiques, et pourquoi
```

---

## Sources de données

Toutes gratuites, toutes sans clé API :

| Sport | Résultats | Calendrier |
|---|---|---|
| Tennis | dépôt GitHub `Kadantte/tennis_atp`, fork de la base de Jeff Sackmann (l'original a disparu de GitHub en 2026) | ESPN |
| Hockey | `api.nhle.com/stats/rest/en/game` — API officielle, filtrée sur les saisons régulières récentes | `api-web.nhle.com/v1/schedule` |
| Basket | scoreboard ESPN sur `site.web.api.espn.com` (l'hôte `site.api.espn.com` et `stats.nba.com` renvoient 403 depuis les serveurs de GitHub — mesuré par le workflow, voir `data/sonde.log`) | ESPN |

Merci à Jeff Sackmann pour trente ans de données de tennis patiemment rassemblées.
