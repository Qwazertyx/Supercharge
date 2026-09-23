# ⚡ Supercharge

> **D'un algorithme quantique à un vrai problème d'optimisation.**
> Où placer des bornes de recharge électrique sur la Presqu'île de Lyon —
> résolu deux fois, en force brute exacte et en QAOA quantique, puis comparé
> sur la même carte et avec les mêmes chiffres.

Projet 42 — suite de `ftl_quantum`.

---

## Démarrer

```bash
git clone <ce-dépôt>
cd Supercharge
docker compose up
```

Puis ouvrir **<http://localhost:8000>**.

Rien d'autre. Aucune clé d'API, aucun compte, aucun service payant, aucune
variable d'environnement à fournir. Le premier build prend quelques minutes
(installation de Qiskit) ; les suivants sont quasi instantanés.

L'application démarre **directement sur l'instance de référence** décrite plus
bas et la résout immédiatement.

<details>
<summary>Lancer sans Docker (développement)</summary>

```bash
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Python 3.12 ou plus récent. Qiskit 2.x est requis : la branche 1.x dépend de
`symengine`, qui n'a pas de roue précompilée pour les Python récents.
</details>

---

## L'instance de référence

C'est l'état **exact** dans lequel l'application démarre, pour que l'évaluation
soit reproductible. Le bouton **« Réinitialiser l'instance de référence »** y
revient à tout moment.

| Paramètre | Valeur |
|---|---|
| **Zone** | Lyon — Presqu'île et ses rives (`45.746–45.772 N`, `4.822–4.848 E`, ≈ 5,8 km²) |
| **Candidats `N`** | **9** (le dépôt en embarque 20 ; les 11 autres servent à explorer au-delà) |
| **Budget `B`** | **3** bornes |
| **Rayon `r`** | **300 m** |
| **Poids des zones** | **uniformes** |
| **Zones inaccessibles** | **retirées** (Rhône, Saône, emprise ferroviaire de Perrache) |
| **Zones de demande** | 129 au total, dont **99 actives** après retrait des inaccessibles |
| **Pénalité `P`** | automatique, `1,1 × max Wᵢ = 9,9` |
| **QAOA** | `p = 3` couches, 3 redémarrages, COBYLA, 4096 mesures, graine 42 |

### Résultat attendu

| | Sélection | Couverture | Travail | Temps |
|---|---|---|---|---|
| **Force brute** | `{0, 1, 5}` | **26,26 %** (26/99 zones) | **130** combinaisons | ~2 ms |
| **QAOA** | `{0, 1, 5}` | **26,26 %** | ~360 évaluations | ~1,8 s |
| **Recuit simulé** | `{0, 1, 5}` | **26,26 %** | ~28 800 propositions | ~0,6 s |

> `{0, 1, 5}` = **{Bellecour, Terreaux, Gabriel Péri}** : un représentant par
> rive. L'optimum est **unique** à `B = 3` et `r = 300 m`, donc les trois
> solveurs doivent tomber exactement dessus. C'est le cas le plus sévère pour
> QAOA : il n'a pas de second optimum sur lequel se rabattre.
>
> Faire varier `r` fait apparaître des optima multiples — l'interface les
> signale alors (« Optima équivalents »). C'est un bon réglage à montrer en
> soutenance : à `r = 325 m`, `{Bellecour, Terreaux, Gabriel Péri}` et
> `{Terreaux, Gabriel Péri, Vieux Lyon}` couvrent exactement autant, et
> QAOA alterne entre eux d'une graine à l'autre, ce qui n'est pas une erreur.

### Les 9 candidats de l'instance de référence

| # | Lieu | Latitude | Longitude | Rive |
|---|---|---|---|---|
| 0 | Place Bellecour | 45.7577 | 4.8320 | Presqu'île |
| 1 | Place des Terreaux | 45.7674 | 4.8336 | Presqu'île |
| 2 | Place Beauregard | 45.7578 | 4.8233 | rive droite |
| 3 | Gare de Perrache | 45.7496 | 4.8262 | Presqu'île |
| 4 | Place Saint-Paul | 45.7660 | 4.8274 | rive droite |
| 5 | Place Gabriel Péri | 45.7558 | 4.8434 | rive gauche |
| 6 | Vieux Lyon — Saint-Jean | 45.7605 | 4.8271 | rive droite |
| 7 | Place Maréchal Lyautey | 45.7689 | 4.8411 | rive gauche |
| 8 | Quai Victor Augagneur | 45.7624 | 4.8413 | rive gauche |

Ces emplacements ne sont pas tirés au hasard. Ils sont répartis **trois par
rive**, dans les proportions de la demande elle-même (30 % rive droite, 46 %
Presqu'île, 24 % rive gauche), et à 300 m de rayon ils forment **deux grappes
qui se recouvrent** plus quatre isolés.

```
grappe A (autour de la Saône) : 0 Bellecour · 2 Beauregard · 6 Vieux Lyon   421–675 m
grappe B (nord)               : 1 Terreaux  · 4 Saint-Paul                      505 m
isolés                        : 3 Perrache · 5 Gabriel Péri · 7 Lyautey · 8 Augagneur
```

Avec `B = 3`, un bon solveur doit **choisir un représentant par grappe** plutôt
qu'empiler des bornes redondantes. C'est précisément ce que le terme
anti-redondance du QUBO encode : 4 zones sont à portée de deux candidats à la
fois, aucune n'est à portée de trois — c'est ce qui rend la troncature au
degré 2 exacte ici (voir plus bas). Un jeu de candidats sans recouvrement
aurait rendu le problème séparable, donc sans intérêt.

> Une version antérieure massait 6 des 9 candidats sur la Presqu'île. Le
> problème restait valide, mais la carte laissait croire que les deux rives ne
> comptaient pas, et le budget de 3 n'avait plus de véritable arbitrage
> géographique à faire.

---

## Le problème

**Maximum Coverage sous contrainte de cardinalité**, NP-difficile.

Avec `xᵢ ∈ {0,1}` (« construire la borne `i` ou non »), `wⱼ` le poids de la zone
`j`, et `Cⱼ` l'ensemble des candidats capables de la couvrir :

```
maximiser   Σⱼ wⱼ · 𝟙[ Σᵢ∈Cⱼ xᵢ ≥ 1 ]
sous        Σᵢ xᵢ ≤ B
```

Le point dur : **une zone couverte par trois bornes rapporte `wⱼ`, pas `3wⱼ`**.
C'est cette non-linéarité qui interdit une solution triviale.

---

## Les deux solveurs

### Force brute — la vérité terrain

Énumère `Σₖ≤B C(N,k)` combinaisons, les évalue, garde la meilleure. **Exacte par
construction.** C'est la référence contre laquelle QAOA est jugé, et elle est
testée contre une énumération indépendante écrite autrement
(`tests/test_solvers.py`).

### QAOA — approché, quantique, en simulation locale

Le chemin complet, tout écrit à la main :

```
problème contraint
      │  ① linéarisation de la couverture : 1 − Π(1−xᵢ), tronqué au degré 2
      │  ② budget absorbé en pénalité : P·(Σxᵢ − B)²
      ▼
   QUBO            E(x) = Σᵢ Qᵢᵢxᵢ + Σᵢ<ₖ Qᵢₖxᵢxₖ
      │  ③ xᵢ = (1 − zᵢ)/2
      ▼
  Ising / H_C      H_C = Σ hᵢZᵢ + Σ JᵢₖZᵢZₖ          (diagonal : H_C|x⟩ = E(x)|x⟩)
      │  ④ circuit à p couches
      ▼
  |ψ(γ,β)⟩ = Π [ e^{−iβH_M} e^{−iγH_C} ] |+⟩^N      H_M = Σ Xᵢ
      │  ⑤ boucle variationnelle : COBYLA optimise (γ,β)
      ▼
  mesure → meilleur tirage faisable
```

Aucun appel à `QAOAAnsatz`, `QuadraticProgram` ni `MinimumEigenOptimizer`.
Qiskit ne sert qu'à assembler le circuit, l'exécuter sur Aer et porter le modèle
de bruit, ce que le sujet autorise explicitement.

---

## Choix de conception

### La règle d'or : une seule fonction objectif

`backend/objective.py` contient **une** fonction `evaluate()`, exacte, sans
aucune approximation. Les **trois** solveurs l'appellent pour produire le chiffre
affiché.

Le QUBO, lui, sert **uniquement** à guider le circuit quantique. Son énergie
n'est jamais affichée comme un score.

> C'est ce qui rend **structurellement impossible** qu'une métrique contredise
> la carte — une exigence explicite du sujet. Des tests vérifient l'égalité pour
> les trois solveurs.

### Remplacer `≤ B` par `= B` sans perdre d'optimum

La couverture est **monotone croissante** : ajouter une borne ne peut jamais la
réduire. Il existe donc toujours un optimum qui sature le budget, et l'inégalité
peut devenir une égalité — qui se pénalise par un simple carré.

**Zéro variable d'écart, donc zéro qubit auxiliaire.** Sur l'instance de
référence, c'est 2 qubits économisés sur 9, soit 22 % du registre. La monotonie
est vérifiée par test.

### La troncature au degré 2 est exacte ici — et c'est mesuré

Un QUBO n'accepte que les degrés 1 et 2, or `1 − Πᵢ(1−xᵢ)` va jusqu'au degré
`|Cⱼ|`. On tronque, ce qui est exact tant qu'au plus **2** bornes couvrent la
même zone.

Or on peut borner cela sans rien énumérer : `s_max = maxⱼ min(|Cⱼ|, B)`.

```
r = 300 m (défaut) →  s_max = 2   →  QUBO EXACT, écart mesuré : 0,0000
r ≤ 400 m          →  s_max = 2   →  QUBO EXACT
r = 450 m et plus  →  s_max = 3   →  régime approché
```

Aucune zone de la carte n'est à portée de trois candidats à 300 m : 4 zones
en voient deux, aucune n'en voit trois.
L'interface affiche un **indicateur de fidélité du QUBO** recalculé à chaque
résolution, qui bascule en orange dès qu'on sort du régime exact.

### Le poids de pénalité `P` est exposé

`P` doit dépasser le gain marginal maximal d'une borne supplémentaire,
`max Wᵢ`. La valeur par défaut est `1,1 × max Wᵢ`, mais **le curseur est
décochable** pour démontrer les deux défaillances en direct :

| `P` | Effet | Ce que montre l'interface |
|---|---|---|
| `< max Wᵢ` | violer le budget devient rentable | QAOA sort 4 ou 5 bornes pour un budget de 3, signalé **infaisable** en rouge |
| `≫ max Wᵢ` | la pénalité écrase le signal de couverture | le contraste entre placements décroît en `1/P`, l'optimiseur perd ses gradients |

Ce ne sont pas deux versions du même défaut : **un `P` trop petit corrompt le
problème, un `P` trop grand corrompt le solveur.** Avec un `P` énorme, l'état
fondamental du QUBO reste correct ; c'est COBYLA qui ne sait plus le trouver.

### Le plafond du simulateur est mesuré, pas décrété

Simuler `N` qubits coûte `O(2^N)` en temps **et** en mémoire, à chaque itération.
Temps de résolution complets mesurés :

| `N` | 9 | 12 | 13 | **14** | 15 | 16 |
|---|---|---|---|---|---|---|
| | 1,8 s | 3,0 s | 5,6 s | **8,4 s** | 18,9 s | **75,2 s** |

Le plafond est fixé à **14 qubits** (`SUPERCHARGE_QAOA_MAX_QUBITS`). Au-delà,
QAOA se désactive en expliquant pourquoi, et **le solveur classique continue de
tourner** — jamais de gel.

Le saut de 15 à 16 est de `×4` et non `×2` : à 16 qubits le vecteur d'état
atteint 1 Mo et sort du cache L2.

### Un chemin rapide, prouvé équivalent au circuit

La boucle variationnelle n'exécute pas le circuit porte par porte : elle utilise
une évolution vectorisée qui exploite le fait que `H_C` est **diagonal** (son
exponentielle est une multiplication élément par élément). **35× plus rapide.**

Ce raccourci ne serait pas défendable s'il pouvait diverger. `tests/test_circuit.py`
prouve sur des angles aléatoires que les deux chemins produisent le **même état**,
à `10⁻¹⁶` près. Le circuit Qiskit reste l'artefact canonique : c'est lui qui est
mesuré, qui porte le bruit, et qui fournit profondeur et comptage de portes.

### Le fond de carte

Tuiles **OpenStreetMap** standard, sans clé d'API. Elles sont volontairement
atténuées en CSS pour que la donnée ressorte.

> CARTO et Stadia proposent de beaux fonds sombres : testés, puis **écartés**,
> car ils exigent désormais une clé d'API, ce que le sujet interdit. Un
> `filter: invert()` sur les tuiles a également été essayé puis abandonné : il
> force une rastérisation logicielle qui gelait le rendu plus de 30 secondes.

Leaflet et Chart.js sont **versionnés dans le dépôt** (`frontend/vendor/`) :
l'application se charge même derrière un réseau qui bloque les CDN.

---

## Les métriques

Le panneau de comparaison rapporte, pour chaque solveur et en delta : couverture
pondérée, bornes utilisées / budget, zones non couvertes, travail effectué et
temps de calcul.

> ⚠️ Les unités de « travail » **ne sont pas comparables entre elles** :
> combinaisons énumérées, évaluations de fonction de coût et propositions de
> mouvement ne mesurent pas la même chose. Seule leur **croissance avec `N`** est
> comparable, et c'est l'objet de la courbe de complexité.

### La courbe de complexité — quatre courbes, pas deux

Échelle logarithmique. L'axe vertical est le **travail** (opérations), **pas** la
mémoire : la force brute parcourt l'espace une combinaison à la fois.

| Courbe | Nature | Pourquoi elle est là |
|---|---|---|
| `2^N` | exponentielle | l'espace de recherche complet, celui que QAOA explore réellement |
| `Σₖ≤B C(N,k)` | polynomiale de degré `B` | **honnêteté** : ce que la force brute énumère vraiment |
| `p·(2N + 3·N(N−1)/2)` | polynomiale | le circuit sur un vrai QPU — **la courbe qui porte l'argument** |
| `iters · 2^N · p·N` | exponentielle | **ma simulation**, la pire des quatre |

Tracer la deuxième désamorce l'objection « à `B` fixé, `C(N,B)` est polynomial,
pas exponentiel ». Elle est juste, et le commutateur **`B = N/2`** montre le
régime des déploiements réels, où `C(N, N/2) ≈ 2^N/√N` redevient exponentiel.

Tracer la quatrième, c'est admettre visuellement que ma simulation est plus
coûteuse que la force brute — je paie le coût exponentiel que le quantique est
censé éviter.

---

## Honnêteté du résultat

**À cette échelle, le solveur classique gagne sur les deux tableaux.** Il est
exact, donc QAOA ne peut jamais le dépasser en couverture, seulement l'égaler.
Et il est environ **1000× plus rapide**.

C'est attendu, et ce n'est pas un échec du projet :

1. la force brute est **exacte** ;
2. je **simule** le circuit sur un CPU, donc je paie `O(2^N)` par itération —
   exactement le coût que le quantique est censé éviter.

L'avantage quantique est **asymptotique**. Il vit dans la courbe de croissance,
pas dans le chronomètre d'une instance à 9 candidats. La ligne de verdict de
l'interface est **générée à partir des chiffres mesurés**, jamais codée en dur.

---

## Bonus

| Bonus | Où |
|---|---|
| **Recuit simulé** (3ᵉ solveur) | sur **le même QUBO** que QAOA : c'est la comparaison la plus juste, « approché classique » contre « approché quantique », dans le même paysage énergétique |
| **Convergence de la boucle variationnelle** | énergie évaluée + minimum courant, avec l'optimum exact en ligne de référence |
| **Concentration des amplitudes** | l'interférence constructive rendue visible : les barres dominent la ligne `1/2^N` du niveau équiprobable |
| **Bruit quantique** | modèle dépolarisant sur les portes et la lecture |
| **Démo d'explosion combinatoire** | curseur `N` jusqu'à 80, avec durée d'énumération lisible |
| **Thème clair / sombre** | deux palettes de séries validées séparément (séparation daltonienne et contraste) |

### Ce que montre réellement le bonus « bruit »

Le placement affiché ne bouge presque pas sous l'effet du bruit, et c'est un
**piège** : on garde le meilleur tirage faisable sur 4096 mesures, or sur un
espace de 512 états le hasard seul finit par toucher l'optimum.

Ce qui se dégrade, c'est la **distribution**. L'interface la rapporte :

| Bruit sur les CX | `P(optimum)` | `P(faisable)` |
|---|---|---|
| aucun (idéal) | 0,71 % | 44,5 % |
| 1 % (matériel 2024) | 0,93 % | 43,4 % |
| **5 %** | **0,44 %** | **24,1 %** |
| *tirage uniforme (référence)* | *0,39 %* | *25,4 %* |

À 5 % d'erreur sur les portes à deux qubits, **la distribution s'effondre sur le
hasard pur** : le circuit ne porte plus aucune information exploitable.

Le circuit QAOA contient `O(p·N²)` portes CX, qui sont les plus fautives. À
`p = 3` et `N = 9`, cela fait 216 CX : à 1 % d'erreur chacune, seules
`(0,99)²¹⁶ ≈ 11 %` des exécutions passent sans aucune erreur. **Et cela empire
quadratiquement avec `N`.** C'est le vrai mur du calcul quantique aujourd'hui :
pas le nombre de qubits, mais leur qualité.

---

## Structure du dépôt

```
Supercharge/
├── docker-compose.yml      docker compose up, rien d'autre
├── Dockerfile              image unique, utilisateur non privilégié
├── requirements.txt        dépendances épinglées
│
├── backend/
│   ├── main.py             FastAPI : API + service du frontend
│   ├── models.py           validation Pydantic (bornes posées une seule fois)
│   ├── instance.py         chargement des données de Lyon, instance paramétrée
│   ├── geometry.py         haversine, matrice de couverture, ray casting
│   ├── objective.py        ⭐ LA fonction objectif, unique source de vérité
│   ├── qubo.py             ⭐ QUBO, Ising, diagnostic de fidélité
│   ├── compare.py          différences, verdict, tableau de métriques
│   ├── complexity.py       les quatre courbes de croissance
│   └── solvers/
│       ├── brute_force.py  exact, vérité terrain
│       ├── qaoa.py         ⭐ circuit + boucle variationnelle
│       └── annealing.py    recuit simulé (bonus)
│
├── data/                   instance de Lyon (générée, committée, auditable)
├── scripts/
│   └── generate_instance.py  régénère data/ de façon déterministe
│
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   ├── js/                 api · maps · charts · panels · app
│   └── vendor/             Leaflet + Chart.js versionnés (aucun CDN requis)
│
└── tests/                  132 tests
```

### Les données de Lyon

`data/` est **généré puis committé**, pour que l'application démarre sans réseau
et que l'instance reste auditable :

```bash
python scripts/generate_instance.py
```

Les zones de demande forment une grille de 180 m pondérée par la proximité à 11
pôles d'activité réels (Bellecour, Hôtel de Ville, Cordeliers, Perrache,
Guillotière…), avec une décroissance gaussienne de portée 350 m. Seules les
cellules atteignant **20 % de la densité de pointe** sont retenues : en dessous,
la demande est trop diffuse pour justifier une infrastructure.

> Ces intensités sont un **choix de modélisation assumé**, calibré à la main sur
> la fréquentation observable de chaque pôle. Ce ne sont pas des données
> officielles de la Métropole, et le projet ne prétend pas le contraire.

**Le Rhône et la Saône, eux, ne sont pas modélisés : ce sont les vraies
emprises**, relevées sur OpenStreetMap (relations `7317123` et `660056`), puis
découpées sur la zone d'étude et simplifiées par Douglas-Peucker à ~9 m près —
1300 points ramenés à 39 pour la Saône, 1072 à 33 pour le Rhône. Les polygones
sont figés en dur dans le script : aucune dépendance réseau, ni au build ni à
l'exécution.

La simplification est vérifiée plutôt que supposée : les 129 cellules de la
grille reçoivent **exactement le même classement** accessible / inaccessible
avec le polygone complet et avec sa version simplifiée.

> Une version antérieure décrivait chaque fleuve par un axe rectiligne épaissi
> à largeur constante. C'était faux de jusqu'à 350 m : un ruban droit ne peut
> pas rendre le coude de la Saône, qui s'écarte vers l'ouest en descendant sur
> Perrache puis quitte la zone au nord de Saint-Paul. Deux candidats étaient
> mal placés dans la foulée, dont le quai Victor Augagneur, situé 580 m trop
> au sud.

---

## Tests

```bash
pip install pytest httpx2
python -m pytest tests/ -q
```

**132 tests**, dont les plus structurants :

| Test | Ce qu'il garantit |
|---|---|
| force brute vs énumération indépendante | la vérité terrain est réellement optimale (sur tout le domaine `B × r`) |
| QUBO ↔ Ising sur **les 2^N états** | le pont classique → quantique est exact, pas « à peu près » |
| état fondamental du QUBO = optimum réel | l'encodage résout bien le bon problème |
| chemin rapide ≡ circuit Qiskit à `10⁻¹⁶` | l'optimisation de vitesse ne change rien au résultat |
| `P` trop petit ⇒ fondamental infaisable | la borne `max Wᵢ` est la vraie frontière |
| `P` trop grand ⇒ contraste en `1/P` | la défaillance annoncée est bien celle qui se produit |
| couverture croissante en `B` | la monotonie, qui légitime `≤ B` → `= B` |
| les trois solveurs via `evaluate()` | les chiffres ne peuvent pas contredire la carte |
| `N` > plafond ⇒ skip propre, classique continue | pas de gel |
| chaque paramètre change le résultat | vérifié pendant l'évaluation |

---

## Licence et attributions

Code du projet : usage pédagogique 42.

- Fonds de carte **et géométrie des fleuves** : © contributeurs
  [OpenStreetMap](https://www.openstreetmap.org/copyright), sous licence ODbL.
  Les emprises du Rhône et de la Saône sont dérivées des données OSM.
- [Leaflet](https://leafletjs.com/) 1.9.4 — BSD-2-Clause
- [Chart.js](https://www.chartjs.org/) 4.4.4 — MIT
- [Qiskit](https://www.ibm.com/quantum/qiskit) — Apache-2.0

Aucun identifiant, jeton ni secret n'est présent dans ce dépôt.
