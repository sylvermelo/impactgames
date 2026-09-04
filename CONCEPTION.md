# Conception technique — Impact Games

**Objet :** les choix mathématiques des trois moteurs, ce qu'on a mesuré, et ce
qu'on ne peut pas encore mesurer.

---

## 1. Le principe non négociable

Un modèle de langage ne produit **aucune** probabilité dans ce projet. Les
chiffres sortent de trois moteurs déterministes, testés, rejouables à l'identique.
Un LLM qui invente des statistiques n'est ni backtestable ni reproductible : il
donne une belle interface et des pronostics au hasard.

Chaque sport a sa propre mathématique. C'est le point le plus important de la
conception : **il n'existe pas de « modèle de sport » universel.**

---

## 2. Tennis — Elo par surface + chaîne de Markov

### Pourquoi pas une loi de Poisson

Un match de tennis n'a pas de « score » comparable à un total de buts : c'est un
empilement **points → jeux → sets → match**, avec des seuils (6 jeux, 2 jeux
d'écart, tie-break à 6-6). La bonne modélisation remonte cette hiérarchie.

### L'architecture

```
écart Elo par surface
   → probabilité de gagner un point (service / retour / tie-break)
   → probabilité de gagner un jeu        (Markov, ~150 états)
   → probabilité de gagner un set        (Markov)
   → probabilité de gagner le match      (convolution sur 3 ou 5 sets)
   → score exact en sets, total de jeux, handicap
```

Un seul modèle, tous les marchés — le même principe que la matrice de scores du
football. Et le format 5 sets amplifie **automatiquement** l'écart entre les
joueurs : aucune règle spéciale.

### La décision qui a changé le modèle

La première version laissait la chaîne décider de la probabilité de match, avec
un unique paramètre `beta` ajusté par maximum de vraisemblance. **Mesure sur
1 310 matchs de contrôle (2026) :**

| Modèle | Log-loss |
|---|---|
| Chaîne de Markov seule | 0,6372 |
| Logistique sur l'écart Elo | **0,6268** |

La chaîne perdait. Sa courbe est trop raide : le circuit ATP est plus
imprévisible qu'un modèle génératif de points ne le suppose (abandons, méforme,
enjeu variable).

D'où l'architecture actuelle :

- la **logistique calibrée** décide de la probabilité de gagner le match ;
- la **chaîne de Markov est ré-inversée** — on cherche l'écart fictif qui lui
  ferait annoncer exactement cette probabilité, puis on la laisse dérouler sets
  et jeux. Les marchés dérivés restent parfaitement cohérents avec le marché
  principal.

### L'effet Grand Chelem, mesuré et non supposé

L'échelle de la logistique est ajustée **par surface et par format**. Résultat
sur 34 445 matchs :

| Groupe | Échelle | Effet |
|---|---|---|
| Dur, 3 sets | 1,12 | courbe plate |
| Dur, 5 sets | **0,84** | courbe raide |
| Terre, 3 sets | 1,20 | |
| Terre, 5 sets | **0,60** | |
| Gazon, 3 sets | 1,34 | |
| Gazon, 5 sets | **0,76** | |

L'échelle 5 sets est systématiquement plus petite : le favori gagne réellement
plus souvent en Grand Chelem. Le modèle le retrouve tout seul au lieu de le
supposer.

### Le paramètre `beta`

Il ne décide plus du vainqueur : il fixe la **forme** du match. Un `beta` élevé
donne des services dominateurs, donc beaucoup de 2-0 et des matchs courts. Il
est ajusté par log-loss sur les **scores en sets réellement observés**
(2-0, 2-1, 3-2…), ce qui est le critère honnête.

---

## 3. Hockey — Poisson bivarié, et deux pièges

Score bas (≈ 6 buts) : comme au football, une matrice de scores 11×11 dérive
tous les marchés par simple somme de zones.

### Piège 1 : le but de prolongation

Un 4-3 en prolongation n'a pas produit 7 buts en 60 minutes — il en a produit 6.
L'API renvoie le score final, but décisif compris. **Sans le retirer, toutes les
attaques sont surestimées sur les matchs serrés**, soit environ un quart de la
ligue. Le champ `period` (> 3) dit si le match est allé au-delà.

### Piège 2 : il y a deux marchés, pas un

Le hockey n'admet pas de nul au classement, mais en admet un à 60 minutes :

- **1X2 temps réglementaire** — trois issues, dont le nul
- **Moneyline** — deux issues, prolongation et fusillade comprises

Le second se déduit du premier en répartissant la masse du nul selon la part de
victoires du domicile après 60 minutes (≈ 54 %), un paramètre mesuré.

### La contrainte d'identifiabilité, ratée deux fois

`log λ_dom = a_h + b_a + γ` : ajouter *c* à toutes les attaques et retirer *c* à
toutes les défenses ne change **aucune** probabilité. Il faut ancrer quelque
chose.

| Version | Contrainte | Résultat |
|---|---|---|
| 1 | `moyenne(a) + moyenne(b) = 0` | **ne sert à rien** : cette somme est invariante sous la dérive qu'on veut interdire |
| 2 | `moyenne(a) = 0` **et** `moyenne(b) = 0` | **pire** : supprime le paramètre qui porte le niveau de buts de la ligue (≈ 3). Mesuré : γ = 1,12 au lieu de 0,25 — l'avantage du domicile était contaminé par le niveau général |
| 3 | `moyenne(b) = 0`, `moyenne(a)` libre | γ = 0,25 retrouvé ; `exp(moyenne(a))` ≈ 3 retrouvé |

La pénalité ridge s'applique aux **écarts à la moyenne**, pas au niveau, sinon
elle tire artificiellement le niveau de buts vers zéro.

---

## 4. Basket — normales, et la séparation force/rythme

220 points par match, pas de nul : la Poisson serait absurde. On décompose :

```
T = points_dom + points_ext      le total, piloté par le RYTHME
D = points_dom − points_ext      l'écart, piloté par la FORCE RELATIVE
```

Avec `o_i` (rendement offensif) et `d_i` (rendement défensif) :

```
D = (o_h + d_h) − (o_a + d_a) + avantage_domicile     ← la FORCE NETTE
T = 2·moyenne + (o_h − d_h) + (o_a − d_a) + avantage  ← le RYTHME
```

**C'est le point le plus utile du modèle.** Une équipe peut être très forte et
jouer lentement : peu de points, écarts nets. Les deux marchés sont
indépendants, ce qu'un modèle à une seule note ne peut pas exprimer.

La cible étant gaussienne, moindres carrés et maximum de vraisemblance
coïncident : la solution est en forme close, aucun optimiseur à faire diverger.

### La correction de continuité — où elle s'applique, où non

L'écart est un **entier** :

- « le domicile gagne » = écart ≥ 1, donc `P(normale > 0,5)` — le 0,5 est
  **nécessaire** ;
- un handicap à 6,5 n'a jamais de mise remboursée : « dom −6,5 » = écart ≥ 7,
  soit `P(normale > 6,5)` **tel quel**. Remettre un 0,5 ici — l'erreur
  commise — décale toutes les lignes d'un demi-point.

Et l'égalité à 48 minutes (~6 % des matchs) doit être répartie entre les deux
équipes, sinon les deux côtés du moneyline ne somment pas à 1.

---

## 5. La méthode de test

### Le test qui attrape les vrais bugs

La chaîne de Markov est comparée à une **simulation de Monte-Carlo écrite
autrement**, sans code partagé : 200 000 matchs simulés jeu par jeu, 10 jeux de
paramètres, tolérance fixée à 4 erreurs-types (pas un chiffre arbitraire).

C'est ce test qui a attrapé la fuite de convolution : deux distributions centrées
se convoluent en une distribution décalée de 2×offset. Sans re-trancher après
**chaque** convolution, tout part hors du tableau et le résultat s'effondre à
zéro. Symptôme visible : tous les handicaps à 0,0 %.

### Les estimateurs doivent retrouver la vérité

Pour le hockey et le basket, on génère des milliers de matchs à partir de
paramètres **connus**, puis on vérifie que l'estimateur les retrouve
(corrélation > 0,90, avantage du domicile à ±0,12, niveau de buts à ±0,35).
S'il n'y arrive pas sur des données propres, il n'y arrivera pas sur des données
réelles.

### Les bugs que ces tests ont attrapés

| Bug | Symptôme | Comment il a été trouvé |
|---|---|---|
| Convolution de la DP écart | tous les handicaps à 0,0 % | Monte-Carlo |
| Force nette hockey en `a + b` au lieu de `a − b` | corrélation **−0,32** avec la vérité | test de récupération |
| Contrainte d'identifiabilité | γ = 1,12 au lieu de 0,25 | test de récupération |
| Correction de continuité sur les handicaps | 0,5 point de décalage sur toutes les lignes | test à écart = ligne |
| Vecteur de calibration mal construit | ~50 % dans toutes les tranches | test d'appariement |
| Grille d'ajustement trop courte | optimum collé à la borne | valeur intérieure vérifiée |

---

## 6. Ce qui est mesuré, et ce qui ne l'est pas

**Tennis** — backtest walk-forward sur 29 262 matchs de contrôle (2019 → 2026).
Log-loss 0,6274 contre 0,6931 au hasard. Calibration : écarts ≤ 2,7 points sur
toutes les tranches.

**Hockey et basket** — estimateurs validés sur données synthétiques. **Pas
encore de backtest sur données réelles**, et surtout : il n'existe **aucune
source gratuite de cotes historiques** pour la NHL ni la NBA. Le football avait
les cotes de clôture Pinnacle comme juge de paix ; ici, ce juge n'existe pas.

Conséquence à assumer : on peut dire « l'estimateur est correct », pas « le
modèle bat le marché ». La seconde phrase demanderait des cotes payantes, ou un
suivi prospectif sur plusieurs centaines de matchs.

---

## 7. Les pièges qui restent devant nous

1. **Le sur-ajustement.** Le tennis ajuste 6 échelles + 1 `beta` sur 34 000
   matchs : confortable. Le hockey ajuste 2 paramètres par équipe sur ~1 200
   matchs par saison : il faut la décroissance temporelle et la ridge.
2. **Les effectifs qui bougent.** Échanges NHL et NBA, « load management »,
   blessures. La demi-vie (270 jours NHL, 400 jours NBA) est un compromis, pas
   une vérité.
3. **L'intersaison.** En septembre, la NBA et la NHL n'ont pas de calendrier.
   L'application doit afficher « aucun match » plutôt que de recycler l'ancien
   calendrier — d'où le filtre anti-passé.
4. **Les matchs sans enjeu.** Fin de saison régulière NBA : les équipes
   qualifiées font tourner. Aucun paramètre ne le capture encore.
5. **L'illusion du petit échantillon.** 30 paris ne prouvent rien. Il en faut
   1 000 minimum pour distinguer la compétence de la chance.

---

## 8. L'étape suivante, par ordre de valeur

1. **Backtest walk-forward hockey et basket** sur données réelles — la même
   rigueur que pour le tennis, même sans cotes de référence.
2. **Blessures et absences.** Le seul facteur majeur absent des trois modèles.
3. **Suivi prospectif public.** Publier chaque pronostic avant le match et
   afficher le bilan : c'est la seule preuve qui vaille.
4. **WTA.** Les données existent, le moteur tennis fonctionne déjà à l'identique.
