# Impact Games — conception

Même architecture que pronos-foot, transposée à trois sports.

```
COUCHE 1 — LE MOTEUR (Python, déterministe, backtestable)
  Basket  : att × def, totaux ~ N(μ, σ)
  Hockey  : Poisson bivarié + τ (Dixon-Coles)
  Tennis  : Elo global + surface, sets i.i.d.
            ↓ JSON
COUCHE 2 — L'INTERFACE (HTML, zéro CDN)
  Anatomie de chaque événement, coupon, simulateur, calibration
            ↓
COUCHE 3 — LA PUBLICATION
  GitHub Actions toutes les 3 h → HTML autonome → Pages
```

Un LLM ne produit **aucune** probabilité. Tout chiffre affiché sort du moteur
ou du backtest.

## Pourquoi ces modèles

**Basket.** Un match NBA dépasse 200 points : la Poisson (faite pour les petits
entiers) est un mauvais outil. La loi normale sur la marge et le total est le
standard industrie (plus simple qu'un modèle de possessions, et calibrable
avec des box-scores publics).

**Hockey.** 5 à 6 buts par match, comme le football. Dixon-Coles s'applique
tel quel. Le moneyline NHL partage le nul réglementaire 50/50 (prolongation /
fusillade).

**Tennis.** Pas d'équipe, pas de domicile au même titre. Un Elo (K=24) + Elo
surface (pondération 65/35), inversé en P(set) puis développé en score 2-0 /
2-1 / etc. Les totaux de jeux sont une normale centrée sur 9,7 jeux/set.

## Données

Tout est gratuit, sans clé :

1. Archive Sportsbook Review 2011-2021 (NBA + NHL) **avec cotes de clôture**
   — c'est le juge de paix du backtest moneyline.
2. ESPN API publique — calendrier 8 jours et complément de saisons récentes.
3. tennis-data.co.uk — ATP/WTA + cotes Pinnacle/Bet365, quand le site répond.
4. Miroir Sackmann (GitHub) — filet de sécurité tennis 2012-2022.

Si ESPN tombe, le calendrier existant est conservé. Si tennis-data.co.uk
tombe, Sackmann suffit à l'Elo.

## Backtest

- Basket / hockey : walk-forward **par saison** (on n'utilise jamais le futur).
- Tennis : l'Elo est déjà en ligne (chaque match est prédit *avant* mise à jour).
- Référence : cotes de clôture SBR déviggées (là où elles existent).
- On publie le ROI, même s'il est négatif.

## Limites assumées

Pas de compositions, pas de xG / Corsi, pas de blessés, pas de surface
« indoor vs outdoor » au-delà du label Hard/Clay/Grass. Un marché peut être
prévisible et déjà correctement coté.
