# `Supercharge` — Le document de compréhension

> **Ce fichier est pour toi.** Il n'est pas un livrable du projet.
> Il contient tout ce dont tu as besoin pour : comprendre la théorie, écrire le code,
> relire le code sans être perdu, et répondre à n'importe quelle question du jury.
>
> Lis-le une fois en entier. Puis reviens-y section par section pendant qu'on code.

---

## Table des matières

| §                                        | Titre                      | Tu en as besoin pour…                       |
| ----------------------------------------- | -------------------------- | -------------------------------------------- |
| [1](#1-le-problème)                       | Le problème               | comprendre ce qu'on optimise                 |
| [2](#2-la-géométrie)                     | La géométrie             | écrire`geometry.py`                       |
| [3](#3-le-solveur-classique)               | Le solveur classique       | écrire`brute_force.py`                    |
| [4](#4-pourquoi-cest-difficile)            | Pourquoi c'est difficile   | défendre la courbe de complexité           |
| [5](#5-le-qubo)                            | Le QUBO                    | **la section critique** — `qubo.py` |
| [6](#6-du-qubo-à-lhamiltonien)            | Du QUBO à l'Hamiltonien   | le pont classique → quantique               |
| [7](#7-qaoa)                               | QAOA                       | écrire`qaoa.py`                           |
| [8](#8-lhonnêteté-scientifique)          | L'honnêteté scientifique | **le piège du sujet**                 |
| [9](#9-la-courbe-de-complexité)           | La courbe de complexité   | le visuel n°1 du projet                     |
| [10](#10-les-bonus)                        | Les bonus                  | recuit simulé, bruit, scaling               |
| [11](#11-questionsréponses-de-soutenance) | Q/R de soutenance          | ne jamais être pris au dépourvu            |
| [12](#12-glossaire)                        | Glossaire                  | les mots exacts à employer                  |

---

# 1. Le problème

## 1.1 L'histoire

Une ville veut installer des **bornes de recharge électrique**. Elle a :

- une liste d'**emplacements possibles** (on ne peut pas construire n'importe où : il faut du foncier, du raccordement électrique, un accord de la mairie),
- un **budget** : elle ne peut en financer que quelques-unes,
- une **carte de la demande** : certains quartiers ont beaucoup plus de véhicules électriques que d'autres.

Question : **lesquelles construire ?**

## 1.2 La formulation mathématique

C'est un problème classique de recherche opérationnelle qui s'appelle le **Maximum Coverage Problem** (problème de couverture maximale) **sous contrainte de cardinalité**.

### Les données

| Symbole      | Nom                        | Description                                              |
| ------------ | -------------------------- | -------------------------------------------------------- |
| `N`        | nombre de candidats        | emplacements où on*pourrait* construire               |
| `i`        | indice de candidat         | `i ∈ {0, 1, …, N−1}`                                |
| `M`        | nombre de zones de demande | points où il y a des gens qui veulent recharger         |
| `j`        | indice de zone             | `j ∈ {0, 1, …, M−1}`                                |
| `wⱼ ≥ 0` | poids de la zone`j`      | « combien cette zone compte » (densité, population…) |
| `r`        | rayon de couverture        | une borne couvre tout dans un rayon`r`                 |
| `B`        | budget                     | nombre maximum de bornes constructibles                  |

### Les variables de décision

Pour chaque candidat `i`, une variable **binaire** :

```
xᵢ = 1  →  on construit une borne à l'emplacement i
xᵢ = 0  →  on ne construit pas
```

Un **vecteur** `x = (x₀, x₁, …, x_{N−1}) ∈ {0,1}^N` décrit donc **une solution complète**.

> 💡 **Pourquoi c'est important :** il y a exactement `2^N` vecteurs possibles.
> C'est déjà la graine de toute l'explosion combinatoire du projet.
> Avec N=9, c'est 512. Avec N=50, c'est 1 125 899 906 842 624.

### L'ensemble couvrant `Cⱼ`

Pour chaque zone `j`, on définit :

```
Cⱼ = { i  :  distance(candidat_i, zone_j) ≤ r }
```

C'est **l'ensemble des candidats capables de couvrir la zone `j`**.

> 📌 `Cⱼ` ne dépend **que** de la géométrie et de `r`. Il ne dépend **pas** de `x`.
> Donc on le calcule **une seule fois** au début, et les deux solveurs le réutilisent.
> C'est ce qui permet à la brute force d'être rapide malgré l'énumération.

### L'objectif

Une zone `j` est **couverte** si **au moins un** candidat construit la couvre :

```
zone j couverte  ⟺  ∃ i ∈ Cⱼ tel que xᵢ = 1
                 ⟺  Σᵢ∈Cⱼ xᵢ ≥ 1
```

On maximise le **poids total couvert** :

```
        ┌──────────────────────────────────┐
max     │  f(x) = Σⱼ wⱼ · 𝟙[ Σᵢ∈Cⱼ xᵢ ≥ 1 ] │
        └──────────────────────────────────┘
s.c.       Σᵢ xᵢ ≤ B
           xᵢ ∈ {0,1}
```

Où `𝟙[·]` est la **fonction indicatrice** : elle vaut 1 si la condition est vraie, 0 sinon.

### ⚠️ Le point crucial à comprendre tout de suite

Regarde bien cette formule : **une zone couverte par 3 bornes compte exactement autant qu'une zone couverte par 1 borne.** Elle rapporte `wⱼ`, pas `3wⱼ`.

C'est ce qui rend le problème **non-linéaire** — et c'est **toute la difficulté** de la section 5.
Si on comptait `3wⱼ`, le problème serait trivial à résoudre.

## 1.3 Un exemple à la main

Prends `N = 3` candidats, `M = 4` zones, toutes de poids `wⱼ = 1`, budget `B = 2`.

```
Zone      Candidats qui la couvrent (Cⱼ)
────────────────────────────────────────
zone 0    {0}
zone 1    {0, 1}
zone 2    {1, 2}
zone 3    {2}
```

Énumérons toutes les solutions faisables (`Σxᵢ ≤ 2`) :

| `x`   | Bornes construites | Zones couvertes | `f(x)`               |
| ------- | ------------------ | --------------- | ---------------------- |
| `000` | —                 | —              | 0                      |
| `100` | {0}                | 0, 1            | 2                      |
| `010` | {1}                | 1, 2            | 2                      |
| `001` | {2}                | 2, 3            | 2                      |
| `110` | {0,1}              | 0, 1, 2         | **3**            |
| `101` | {0,2}              | 0, 1, 2, 3      | **4** ← optimum |
| `011` | {1,2}              | 1, 2, 3         | **3**            |

**L'optimum est `x = 101`** : construire aux emplacements 0 et 2, couverture 4/4.

> 🔍 **Observe `110` vs `101`.** Les deux utilisent 2 bornes. Mais dans `110`, les candidats
> 0 et 1 couvrent **tous les deux** la zone 1 — c'est de la **redondance**, du gaspillage.
> Dans `101`, les couvertures sont **disjointes**. Retiens ça : **la redondance est l'ennemi.**
> On va la retrouver mathématiquement en section 5.

---

# 2. La géométrie

Fichier : `backend/geometry.py`

## 2.1 Le problème : la Terre est ronde

Les coordonnées GPS sont en **degrés** (latitude, longitude). Les distances sont en **mètres**.
On ne peut **pas** faire `√((lat₁−lat₂)² + (lon₁−lon₂)²)` :

- 1 degré de **latitude** ≈ 111 320 m, toujours.
- 1 degré de **longitude** ≈ 111 320 × cos(latitude) m. **À Lyon (45.76°N), ça fait ≈ 77 700 m.**

Soit une erreur de ~43 % si tu ignores la projection. Sur un rayon de 300 m, tes cercles seraient des ovales et ta couverture serait fausse.

## 2.2 La formule de Haversine

C'est la distance **orthodromique** (le long de la sphère) :

```
Δφ = φ₂ − φ₁                       (différence de latitude, en radians)
Δλ = λ₂ − λ₁                       (différence de longitude, en radians)

a = sin²(Δφ/2) + cos(φ₁)·cos(φ₂)·sin²(Δλ/2)

d = 2R · arcsin(√a)                R = 6 371 000 m (rayon terrestre moyen)
```

```python
# backend/geometry.py
from math import radians, sin, cos, asin, sqrt

EARTH_RADIUS_M = 6_371_000.0

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique en mètres entre deux points GPS."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))
```

> **Question de jury probable :** *« Pourquoi Haversine et pas Vincenty ? »*
> Réponse : Vincenty modélise la Terre comme un **ellipsoïde** et est plus précis (~0,5 mm contre ~0,3 %),
> mais il est **itératif** et peut ne pas converger sur les antipodes. Sur une zone urbaine de
> quelques kilomètres, l'erreur de Haversine est de l'ordre du **mètre** — négligeable devant
> un rayon de 300 m. Le surcoût n'est pas justifié.

## 2.3 La matrice de couverture

C'est **l'objet central** du projet. On la calcule une fois, les trois solveurs s'en servent.

```python
def build_coverage_sets(candidates, zones, radius_m):
    """
    Retourne:
      covering_sets : list[set[int]]  — covering_sets[j] = Cⱼ = candidats couvrant la zone j
      covered_by    : list[set[int]]  — covered_by[i]    = zones couvertes par le candidat i
    """
    covering_sets = []
    covered_by = [set() for _ in candidates]
    for j, zone in enumerate(zones):
        cj = set()
        for i, cand in enumerate(candidates):
            if haversine(cand.lat, cand.lon, zone.lat, zone.lon) <= radius_m:
                cj.add(i)
                covered_by[i].add(j)
        covering_sets.append(cj)
    return covering_sets, covered_by
```

Complexité : `O(N × M)`. Avec N=9 et M≈150, c'est ~1350 calculs — instantané.

### Optimisation : les bitmasks

Pour la brute force, représenter `Cⱼ` comme un **entier bitmask** rend l'évaluation ultra-rapide :

```python
# Cⱼ = {0, 2} devient l'entier 0b101 = 5
mask_j = sum(1 << i for i in cj)

# Une sélection S = {0, 2} devient aussi 0b101
# "La zone j est-elle couverte ?"  →  (selection_mask & mask_j) != 0
#                                     ↑ une seule instruction CPU
```

C'est ce qui permet d'évaluer des centaines de milliers de combinaisons par seconde
et de rendre le chrono de la brute force honnête.

## 2.4 Les zones inaccessibles

Le sujet demande que **« Inaccessible zones (buildings, parks, water) should be visible enough that the placement makes geographic sense »**, et un **toggle** dans l'UI.

À Lyon c'est un cadeau :

- **Le Rhône** et **la Saône** traversent la ville → deux grandes bandes d'eau.
- **Le parc de la Tête d'Or**, la **place Bellecour** (minérale, mais pas de logements) → pas de demande résidentielle.

**Sémantique retenue** (à documenter, c'est un choix de design) :

> Une zone de demande dont le centre tombe dans un polygone inaccessible est **retirée du problème** :
> elle ne génère pas de demande (personne n'habite dans le Rhône).

Le toggle **« inaccessibles »** :

- **activé** (défaut) → ces zones sont retirées, `M` diminue → les deux solveurs voient le vrai problème.
- **désactivé** → toutes les zones comptent → les solveurs peuvent choisir de placer des bornes pour couvrir de l'eau. C'est volontairement absurde, et **c'est pédagogique** : ça montre au jury que le paramètre change bien le résultat.

Test point-dans-polygone : **algorithme du ray casting** (lancer de rayon).

```python
def point_in_polygon(lat, lon, polygon):
    """Ray casting : on lance un rayon horizontal et on compte les intersections.
    Nombre impair d'intersections → le point est à l'intérieur."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if (lon_i > lon) != (lon_j > lon):
            # le segment traverse la ligne horizontale du point
            lat_cross = lat_i + (lon - lon_i) / (lon_j - lon_i) * (lat_j - lat_i)
            if lat < lat_cross:
                inside = not inside
        j = i
    return inside
```

---

# 3. Le solveur classique

Fichier : `backend/solvers/brute_force.py`

## 3.1 Le principe

**Énumérer. Évaluer. Garder le meilleur.** C'est tout.

```
pour chaque sous-ensemble S ⊆ {0,…,N−1} avec |S| ≤ B :
    score = évaluer(S)
    si score > meilleur_score :
        meilleur_score, meilleure_solution = score, S
```

## 3.2 Pourquoi c'est notre *ground truth*

> Le sujet : *« Your brute force is your ground truth. If it does not return the optimum
> on the reference instance, nothing built on top of it can be trusted. »*

La brute force teste **littéralement toutes les possibilités**. Il n'y a donc **aucun doute** :
ce qu'elle renvoie **est** l'optimum global. Pas « probablement », pas « approximativement ». **Est.**

C'est ça, sa valeur : c'est la **référence absolue** contre laquelle on juge QAOA.
Si QAOA trouve 84,2 % et la brute force 84,2 %, on **sait** que QAOA a trouvé l'optimum.

## 3.3 L'implémentation

```python
from itertools import combinations

def solve_brute_force(instance):
    n = instance.n_candidates
    best_mask, best_weight, evaluated = 0, -1.0, 0

    # zone_masks[j] = bitmask des candidats couvrant la zone j
    zone_masks = instance.zone_masks
    weights = instance.weights

    for k in range(0, instance.budget + 1):           # 0, 1, …, B bornes
        for combo in combinations(range(n), k):        # tous les sous-ensembles de taille k
            sel = 0
            for i in combo:
                sel |= (1 << i)

            total = 0.0
            for j, mj in enumerate(zone_masks):
                if sel & mj:                            # au moins un candidat de S couvre j
                    total += weights[j]

            evaluated += 1
            if total > best_weight:
                best_weight, best_mask = total, sel

    return BruteForceResult(
        selection=mask_to_list(best_mask),
        covered_weight=best_weight,
        combinations_evaluated=evaluated,   # ← exigé par le sujet
    )
```

## 3.4 Combien de combinaisons ?

C'est un chiffre que le sujet exige d'afficher. Le nombre de sous-ensembles de taille `≤ B` parmi `N` :

```
             B
combos(N,B) = Σ  C(N,k)      avec  C(N,k) = N! / (k!·(N−k)!)
            k=0
```

Pour notre instance de référence (**N = 9, B = 3**) :

```
C(9,0) = 1
C(9,1) = 9
C(9,2) = 36
C(9,3) = 84
─────────────
Total  = 130 combinaisons
```

> ⚠️ **Piège à connaître absolument.** `130`, ce n'est pas « explosif ». Si le jury te dit
> *« ton solveur ne teste que 130 cas, où est l'explosion combinatoire ? »*, tu dois avoir
> la réponse — elle est en **section 4.3** et en **section 9.2**. Ne saute pas ces sections.

---

# 4. Pourquoi c'est difficile

## 4.1 NP-difficile

Le Maximum Coverage est **NP-difficile**. Concrètement, ça veut dire :

> Personne n'a trouvé d'algorithme qui le résout **exactement** en temps **polynomial**,
> et on soupçonne très fortement qu'il n'en existe pas (c'est la conjecture `P ≠ NP`).

Ce n'est pas « on n'a pas encore cherché ». C'est un des problèmes les mieux étudiés de
l'informatique théorique depuis 50 ans.

### Le résultat d'inapproximabilité (bonus pour impressionner)

Il existe un **algorithme glouton** simple (prendre à chaque étape la borne qui rapporte le
plus de nouvelle couverture) qui garantit toujours au moins `1 − 1/e ≈ 63,2 %` de l'optimum.

Et **Feige (1998)** a prouvé que, sauf si `P = NP`, **aucun** algorithme polynomial ne peut
garantir mieux que `1 − 1/e`. Le glouton est donc **optimal parmi les algorithmes polynomiaux**.

> 💡 C'est une excellente chose à dire en soutenance : ça montre que tu sais **où se situe**
> ton problème dans le paysage de la complexité, et pourquoi chercher des approches
> alternatives (dont le quantique) est une démarche sérieuse et pas un gadget.

## 4.2 L'explosion combinatoire

L'espace de recherche complet (sans contrainte de budget) est de taille `2^N`.

| N   | `2^N`        | Temps à 10⁹ évaluations/seconde                          |
| --- | -------------- | ----------------------------------------------------------- |
| 10  | 1 024          | instantané                                                 |
| 20  | 1 048 576      | 1 ms                                                        |
| 30  | 1,07 × 10⁹   | 1 seconde                                                   |
| 40  | 1,10 × 10¹² | 18 minutes                                                  |
| 50  | 1,13 × 10¹⁵ | **13 jours**                                          |
| 60  | 1,15 × 10¹⁸ | **36 ans**                                            |
| 80  | 1,21 × 10²⁴ | **38 millions d'années**                             |
| 100 | 1,27 × 10³⁰ | **40 000 milliards d'années** (≫ âge de l'univers) |

Chaque candidat ajouté **double** le travail. Pas +10 %. **×2.**

Acheter un ordinateur 1000× plus rapide te fait gagner… **10 candidats** (`2¹⁰ ≈ 1000`).

## 4.3 ⚠️ La nuance que tu DOIS maîtriser

Voici le point où un jury exigeant va te pousser, et la réponse qui fait la différence.

**L'objection :** « Avec `B` fixé à 3, tu ne testes que `C(N,3) ≈ N³/6` combinaisons. C'est
**polynomial**, pas exponentiel. Ta courbe `2^N` est malhonnête. »

**L'objection est techniquement correcte.** Et voici les trois réponses, toutes vraies :

### Réponse 1 — Dans la vraie vie, `B` grandit avec `N`

Un budget fixe à 3 bornes pour une ville de 100 emplacements candidats n'a aucun sens.
Une ville qui étudie 100 emplacements en construira 30 ou 50. Si `B = N/2` :

```
C(N, N/2) ≈ 2^N / √(πN/2)
```

C'est **exponentiel**, à un facteur `√N` près. L'explosion est bien réelle.

Le pire cas est `B = N/2`, exactement le régime des déploiements réels.

### Réponse 2 — `N^B` est déjà catastrophique

Même avec `B` fixé, `C(N,B) ~ N^B/B!` est polynomial **de degré B**. Pour B = 20 :

```
C(100, 20) ≈ 5,36 × 10²⁰
```

« Polynomial » ne veut pas dire « faisable ». Un polynôme de degré 20 est ingérable.

### Réponse 3 — **QAOA cherche dans l'espace complet `2^N`**

C'est la réponse la plus profonde, et c'est **la comparaison honnête**.

Le QUBO **n'impose pas** la contrainte de budget structurellement : il la **pénalise**.
Le circuit QAOA met les `N` qubits en superposition et explore donc **les `2^N` états**, en
laissant l'optimisation faire émerger ceux qui respectent le budget.

Donc :

- **Brute force** exploite un raccourci **structurel** (« je sais que |S| ≤ B, je n'énumère que ceux-là »).
- **QAOA** travaille sur l'espace **complet**, `2^N`.

Comparer QAOA à `2^N` est donc la comparaison **apples-to-apples**.

> ✅ **Ce qu'on fait dans le projet :** on trace **les deux courbes** — `2^N` (espace complet)
> **et** `Σₖ≤B C(N,k)` (ce que la brute force énumère réellement, avec le `B` courant),
> **et** le coût du circuit QAOA. Et on explique la différence dans l'UI.
>
> **Tracer les deux, c'est ce qui transforme une objection en démonstration de maîtrise.**

---

# 5. Le QUBO

> 🔴 **SECTION LA PLUS IMPORTANTE DU PROJET.**
>
> Le sujet écrit noir sur blanc :
> *« Reformulating the problem as a QUBO is the heart of the quantum side. You must
> understand why the budget constraint becomes a penalty term, and what happens to the
> solution quality when the penalty weight is too small or too large. "I copied the QUBO
> from a tutorial" is not an acceptable answer at the defense. »*
>
> Lis cette section deux fois.

Fichier : `backend/qubo.py`

## 5.1 Qu'est-ce qu'un QUBO ?

**QUBO** = **Q**uadratic **U**nconstrained **B**inary **O**ptimization.

Décortiquons le sigle, mot par mot — c'est exactement ce qu'on te demandera :

| Mot                     | Signification                                                                     | Conséquence                                  |
| ----------------------- | --------------------------------------------------------------------------------- | --------------------------------------------- |
| **Binary**        | les variables sont dans`{0,1}`                                                  | ✅ nos`xᵢ` le sont déjà                  |
| **Quadratic**     | degré**maximum 2** : `xᵢ` et `xᵢxₖ`, **jamais** `xᵢxₖxₗ` | ⚠️ problème (§5.2)                        |
| **Unconstrained** | **aucune** contrainte. Que la fonction à minimiser.                        | ⚠️ problème (§5.3)                        |
| **Optimization**  | on**minimise** (convention)                                                 | on minimise`−f` au lieu de maximiser `f` |

La forme canonique :

```
              ┌────────────────────────────────────────┐
min_{x∈{0,1}ᴺ}│ E(x) = Σᵢ Qᵢᵢ xᵢ  +  Σᵢ<ₖ Qᵢₖ xᵢxₖ  + c │
              └────────────────────────────────────────┘
                       ↑ termes        ↑ termes      ↑ constante
                       linéaires       quadratiques  (sans effet sur l'argmin)
```

Tout tient dans une **matrice `Q` triangulaire supérieure de taille N×N**. C'est tout.

## 5.2 Pourquoi cette forme précise ?

Parce qu'un QUBO se traduit **directement** en **Hamiltonien de Ising**, qui est
**exactement** ce qu'un processeur quantique sait encoder :

- `xᵢ` (terme linéaire) → un champ magnétique local sur le qubit `i` → une porte `RZ`
- `xᵢxₖ` (terme quadratique) → un couplage entre les qubits `i` et `k` → `CX · RZ · CX`

Un terme de degré 3, `xᵢxₖxₗ`, demanderait un couplage à **trois corps**.
Ça n'existe pas nativement sur le hardware. Il faudrait le décomposer avec des qubits
auxiliaires, ce qui coûte des qubits — la ressource la plus rare.

**C'est ça, la vraie raison de la contrainte « quadratique ».** Ce n'est pas une convention
mathématique arbitraire : c'est une contrainte **physique** du matériel.

## 5.3 Obstacle n°1 : linéariser la couverture

### Le problème

Notre objectif contient `𝟙[Σᵢ∈Cⱼ xᵢ ≥ 1]`. Ce n'est **pas** un polynôme. Il faut l'écrire
avec des `+`, des `×` et des constantes uniquement.

### L'identité exacte

La zone `j` est **non** couverte si **tous** les candidats de `Cⱼ` valent 0 :

```
𝟙[zone j NON couverte] = Πᵢ∈Cⱼ (1 − xᵢ)
```

(chaque facteur vaut 1 si `xᵢ=0`, et 0 si `xᵢ=1` ; le produit vaut 1 ssi tous sont à 0)

Donc :

```
              ┌──────────────────────────────────────┐
𝟙[j couverte]=│  1 − Πᵢ∈Cⱼ (1 − xᵢ)                  │   ← EXACT
              └──────────────────────────────────────┘
```

### Le développement

Développons pour `|Cⱼ| = 3`, avec les candidats `a`, `b`, `c` :

```
1 − (1−xₐ)(1−x_b)(1−x_c)
  = 1 − [ 1 − xₐ − x_b − x_c + xₐx_b + xₐx_c + x_bx_c − xₐx_bx_c ]
  = xₐ + x_b + x_c − xₐx_b − xₐx_c − x_bx_c + xₐx_bx_c
    └──── degré 1 ────┘ └────── degré 2 ──────┘ └─ degré 3 ─┘
                                                      ↑
                                            ⚠️ INTERDIT en QUBO
```

En général (**principe d'inclusion-exclusion**) :

```
1 − Πᵢ∈Cⱼ(1−xᵢ) = Σᵢ xᵢ − Σᵢ<ₖ xᵢxₖ + Σᵢ<ₖ<ₗ xᵢxₖxₗ − … ± (termes jusqu'au degré |Cⱼ|)
```

### Les trois options, et pourquoi on choisit A1

|              | Méthode                            | Qubits    | Exact ? | Verdict                                                              |
| ------------ | ----------------------------------- | --------- | ------- | -------------------------------------------------------------------- |
| **A1** | **Troncature au degré 2**    | `N`     | non     | ✅**retenu**                                                   |
| A2           | Variable auxiliaire`yⱼ` par zone | `N + M` | oui     | ❌`M ≈ 150` → 159 qubits → `2¹⁵⁹` amplitudes. Insimulable. |
| A3           | Précalculer le OU                  | —        | —      | ❌ ce n'est plus un polynôme, donc plus un QUBO                     |

> **Sur A2, pour le jury :** l'encodage exact existe et il est standard. On ajoute `yⱼ ∈ {0,1}`
> avec un terme de pénalité forçant `yⱼ ≤ Σᵢ∈Cⱼ xᵢ`. Mais il coûte **un qubit par zone**.
> Avec 150 zones, le vecteur d'état ferait `2¹⁵⁹ × 16` octets — plus d'atomes qu'il n'y en a
> dans l'univers observable. **Ce n'est pas un choix de facilité, c'est une impossibilité physique
> sur simulateur.** Le dire comme ça montre que tu as étudié l'alternative.

### ✅ Le choix retenu : troncature au degré 2

```
              ┌────────────────────────────────────────┐
cover_j(x) ≈  │  Σᵢ∈Cⱼ xᵢ  −  Σᵢ<ₖ∈Cⱼ xᵢxₖ              │
              └────────────────────────────────────────┘
```

### Analysons l'erreur exactement (le jury adorera)

Soit `s = |{i ∈ Cⱼ : xᵢ = 1}|` le nombre de bornes construites qui couvrent la zone `j` :

```
Σᵢ∈Cⱼ xᵢ = s          et         Σᵢ<ₖ∈Cⱼ xᵢxₖ = C(s,2) = s(s−1)/2
```

Donc l'approximation vaut :

```
approx(s) = s − s(s−1)/2
```

Comparons à la vraie valeur `𝟙[s ≥ 1]` :

| `s` (bornes couvrant la zone) | Vraie valeur | `approx(s)`     | Erreur                |
| ------------------------------- | ------------ | ----------------- | --------------------- |
| 0                               | 0            | `0 − 0 = 0`    | ✅**exact**     |
| 1                               | 1            | `1 − 0 = 1`    | ✅**exact**     |
| 2                               | 1            | `2 − 1 = 1`    | ✅**exact**     |
| 3                               | 1            | `3 − 3 = 0`    | ⚠️ sous-estime de 1 |
| 4                               | 1            | `4 − 6 = −2`  | ⚠️ sous-estime de 3 |
| 5                               | 1            | `5 − 10 = −5` | ⚠️ sous-estime de 6 |

**Conclusion, à retenir par cœur :**

> L'approximation est **exacte** tant qu'au plus **2 bornes** couvrent la même zone.
> Au-delà, elle **sous-estime** — elle **pénalise la redondance**.

### ⭐⭐ Le résultat mesuré sur NOTRE instance — ta meilleure carte en soutenance

Voici le point qui change tout. On peut **borner `s` exactement, sans rien énumérer**.

Une sélection contient au plus `B` bornes. Et une zone `j` n'est atteignable que par les
`|Cⱼ|` candidats de son ensemble couvrant. Donc le `s` maximal atteignable vaut :

```
              ┌──────────────────────────────┐
s_max  =      │  maxⱼ  min( |Cⱼ| , B )       │      ← calculable en O(M)
              └──────────────────────────────┘
```

**Si `s_max ≤ 2`, la troncature n'est pas une approximation : elle est EXACTE.**

Et sur l'instance de référence de Lyon, **c'est le cas** — mesuré, pas supposé :

```
r = 300 m, B = 3  →  s_max = 2
   → troncature EXACTE sur 130/130 états faisables
   → écart max |E_qubo − (−couverture réelle)| = 0.0000
```

La raison est purement **géométrique** : à 300 m, **aucune zone de la Presqu'île n'est à
portée de trois candidats à la fois**. Il faut passer à ~400 m pour que `s = 3` apparaisse.

| Rayon                     | `s_max`   | Régime           |
| ------------------------- | ----------- | ----------------- |
| **300 m (défaut)** | **2** | ✅**exact** |
| 400 m                     | 3           | approché         |
| 500 m et +                | 3           | approché         |

> 🎤 **Ce qu'on en fait dans l'application :** un indicateur **« fidélité du QUBO »** dans
> le panneau de métriques, recalculé à chaque résolution. Il affiche en vert
> *« QUBO exact : multiplicité max = 2 »* sur l'instance de référence, et bascule en orange
> avec le nombre de zones concernées dès que l'utilisateur monte le rayon.
>
> **Tu ne te défends plus contre l'objection : tu la montres, chiffrée, à l'écran.**

### Pourquoi c'est acceptable même dans le régime approché

1. **Le biais va dans le bon sens.** Rappelle-toi l'exemple de la section 1.3 : la redondance
   est du gaspillage. Une formulation qui décourage de placer 3 bornes sur le même pâté de
   maisons pousse vers des solutions **plus étalées**, donc **meilleures** au sens du vrai objectif.
2. **Le régime problématique est rare, et on sait exactement quand il survient.** C'est le
   calcul de `s_max` ci-dessus. Ce n'est pas un pari : c'est une borne.
3. **On ne s'en sert jamais pour noter.** ⭐ **Point essentiel.**

### ⭐ La règle d'or du projet

> **Le QUBO sert UNIQUEMENT à guider le circuit quantique.
> Le score affiché est TOUJOURS calculé par la vraie fonction objectif `f(x)`.**

Concrètement, dans `objective.py` :

```python
def coverage(selection: set[int], instance) -> tuple[float, set[int]]:
    """LA fonction objectif. Exacte. Unique source de vérité.
    Utilisée par brute force, QAOA et recuit pour évaluer leur résultat FINAL."""
    covered = {j for j, cj in enumerate(instance.covering_sets) if cj & selection}
    return sum(instance.weights[j] for j in covered), covered
```

Cette fonction n'a **aucune** approximation. Les trois solveurs l'appellent pour produire
le chiffre affiché. **Donc les métriques ne peuvent jamais contredire la carte** — exigence
explicite du sujet (*« Numbers that contradict the map will be caught »*).

Et comme la brute force est exacte, on peut **mesurer** l'impact de l'approximation :
si QAOA atteint la même couverture que la brute force, l'approximation n'a rien cassé.
On transforme une faiblesse théorique en **résultat expérimental vérifié**.

## 5.4 Obstacle n°2 : la contrainte de budget

Le « **U** » de QUBO veut dire **Unconstrained**. Or on a `Σᵢ xᵢ ≤ B`.

### Le principe de la pénalité

L'idée : **faire disparaître la contrainte en la rendant coûteuse.**

Au lieu d'interdire les solutions qui violent le budget, on **ajoute un terme d'énergie**
qui explose quand on la viole. L'optimiseur les évitera **tout seul**, parce qu'elles
ont une mauvaise énergie — pas parce qu'on les a bannies.

```
minimiser  f(x)  sous  g(x) = 0     ⟶     minimiser  f(x) + P·g(x)²
                                                          └── pénalité ──┘
```

On élève au **carré** pour deux raisons :

1. La pénalité doit être **positive** dans les deux sens de violation (trop **ou** trop peu).
2. Le carré est **quadratique** → compatible QUBO. (`|g(x)|` ne l'est pas.)

### ⭐ L'astuce : transformer `≤` en `=`

**C'est LA réponse qui impressionne.** Le réflexe standard face à une inégalité, c'est
d'ajouter des **variables d'écart** (slack) :

```
Σᵢ xᵢ ≤ B   ⟺   Σᵢ xᵢ + s = B,  avec s ∈ {0,…,B}
```

`s` s'encode en binaire sur `⌈log₂(B+1)⌉` qubits supplémentaires. Ça coûte cher, ça
complique le circuit, ça ajoute des degrés de liberté à optimiser.

**On peut s'en passer complètement. Voici pourquoi :**

> **Lemme.** La fonction objectif `f` est **monotone croissante** : ajouter une borne ne
> peut **jamais** diminuer la couverture.
>
> **Preuve.** Si `S ⊆ S'`, alors toute zone `j` couverte par `S` (donc `∃i ∈ S ∩ Cⱼ`) est
> aussi couverte par `S'` (car `i ∈ S'`). Donc `f(S) ≤ f(S')`. ∎
>
> **Corollaire.** Il existe **toujours** une solution optimale qui utilise **exactement** `B`
> bornes. (Si une solution optimale en utilise `k < B`, on ajoute `B−k` bornes arbitraires :
> le score ne baisse pas, donc elle reste optimale.)
>
> **Donc remplacer `≤ B` par `= B` ne perd aucun optimum.** ∎

Résultat : **zéro qubit auxiliaire**, et une pénalité d'une simplicité totale :

```
              ┌──────────────────┐
pénalité(x) = │  P · (Σᵢ xᵢ − B)² │
              └──────────────────┘
```

Elle vaut `0` si on utilise exactement `B` bornes, et `P·k²` si on s'en écarte de `k`.

> 💬 **À dire au jury :** *« J'ai évité les variables d'écart en exploitant la monotonie de
> l'objectif : comme ajouter une borne ne peut jamais nuire, il existe toujours un optimum
> qui sature le budget, donc l'inégalité peut être remplacée par une égalité sans perte.
> Ça m'économise ⌈log₂(B+1)⌉ qubits, soit 2 qubits sur l'instance de référence — 22 % du
> registre. »* **Cette phrase vaut cher.**

## 5.5 Le QUBO complet

On assemble :

```
        ┌─────────────────────────────────────────────────────────────────┐
E(x) =  │ − Σⱼ wⱼ·[ Σᵢ∈Cⱼ xᵢ − Σᵢ<ₖ∈Cⱼ xᵢxₖ ]   +   P·( Σᵢ xᵢ − B )²      │
        └─────────────────────────────────────────────────────────────────┘
          └────── −couverture (on minimise) ──────┘   └─ pénalité budget ─┘
```

### Extraction des coefficients

**Truc essentiel :** pour `xᵢ ∈ {0,1}`, on a **`xᵢ² = xᵢ`**. (`0²=0`, `1²=1`.)
C'est ce qui permet de replier les carrés dans les termes linéaires.

Développons la pénalité :

```
P·(Σᵢ xᵢ − B)²
 = P·[ (Σᵢ xᵢ)² − 2B·Σᵢ xᵢ + B² ]
 = P·[ Σᵢ xᵢ² + 2·Σᵢ<ₖ xᵢxₖ − 2B·Σᵢ xᵢ + B² ]
 = P·[ Σᵢ xᵢ   + 2·Σᵢ<ₖ xᵢxₖ − 2B·Σᵢ xᵢ + B² ]        ← ici on utilise xᵢ² = xᵢ
 = P(1−2B)·Σᵢ xᵢ  +  2P·Σᵢ<ₖ xᵢxₖ  +  P·B²
   └─ linéaire ─┘     └─ quadratique ─┘   └ constante ┘
```

Définissons deux quantités géométriques :

```
Wᵢ  = Σ_{j : i ∈ Cⱼ} wⱼ           « poids total que le candidat i peut couvrir seul »
Wᵢₖ = Σ_{j : i ∈ Cⱼ ET k ∈ Cⱼ} wⱼ  « poids que les candidats i et k couvrent en DOUBLON »
```

D'où les coefficients finaux :

```
┌────────────────────────────────────────────────────────────┐
│  Qᵢᵢ = − Wᵢ  +  P·(1 − 2B)                                 │
│  Qᵢₖ = + Wᵢₖ +  2P                (pour i < k)             │
│  c   =   P·B²                     (constante, ignorable)   │
└────────────────────────────────────────────────────────────┘
```

### Lecture physique de chaque terme — sache l'expliquer

| Terme        | Signe                 | Sens                                                                                                                                                                                                                                |
| ------------ | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `−Wᵢ`    | **négatif**    | **récompense** : construire en `i` baisse l'énergie proportionnellement à ce qu'il couvre. Plus `i` est utile, plus c'est attractif.                                                                                   |
| `P(1−2B)` | négatif si`B ≥ 1` | **incitation à construire** : la pénalité pousse à atteindre `B` bornes, pas à rester à 0.                                                                                                                            |
| `+Wᵢₖ`   | **positif**     | **anti-redondance** : si `i` et `k` couvrent les mêmes zones, les prendre **ensemble** coûte cher. C'est la troncature au degré 2 de §5.3 — elle apparaît ici **exactement** comme le terme de doublon. |
| `+2P`      | positif               | **frein au budget** : chaque paire supplémentaire renchérit, ce qui borne le nombre de bornes à `B`.                                                                                                                     |

> 🔍 **Fait remarquable à souligner en soutenance :** le terme d'approximation `−Σxᵢxₖ` et le
> terme de pénalité `+2P·Σxᵢxₖ` atterrissent sur **le même coefficient** `Qᵢₖ`. Les deux
> mécanismes — « ne gaspille pas » et « respecte le budget » — s'expriment par la **même
> structure algébrique**. Ce n'est pas un hasard : tous deux disent « n'empile pas les bornes ».

### Le code

```python
# backend/qubo.py
import numpy as np

def build_qubo(instance, penalty: float | None = None):
    n, B = instance.n_candidates, instance.budget
    w = instance.weights
    covering = instance.covering_sets           # covering[j] = Cⱼ (set d'indices)

    # W_i : poids couvrable par le candidat i
    W = np.zeros(n)
    for j, cj in enumerate(covering):
        for i in cj:
            W[i] += w[j]

    if penalty is None:
        penalty = auto_penalty(W)               # voir §5.6

    Q = np.zeros((n, n))

    # --- diagonale : récompense de couverture + incitation budgétaire ---
    for i in range(n):
        Q[i, i] = -W[i] + penalty * (1 - 2 * B)

    # --- hors-diagonale : doublon de couverture + frein budgétaire ---
    for j, cj in enumerate(covering):
        members = sorted(cj)
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                Q[members[a], members[b]] += w[j]     # W_ik
    for i in range(n):
        for k in range(i + 1, n):
            Q[i, k] += 2 * penalty

    offset = penalty * B * B
    return Q, offset, penalty


def qubo_energy(Q, offset, x) -> float:
    """Énergie d'un vecteur binaire. Sert aux tests et au debug."""
    x = np.asarray(x, dtype=float)
    linear = np.diag(Q) @ x                 # Σᵢ Qᵢᵢ xᵢ
    quadratic = x @ np.triu(Q, 1) @ x       # Σᵢ<ₖ Qᵢₖ xᵢxₖ  (stricte : k > i)
    return float(linear + quadratic + offset)
```

> Note sur la dernière ligne : `Q` est **triangulaire supérieure**. `x @ triu(Q,1) @ x`
> somme les `Qᵢₖ xᵢxₖ` pour `i<k`, et `diag(Q) @ x` somme les `Qᵢᵢ xᵢ`. Pas de double comptage.

## 5.6 ⭐ Le poids de pénalité `P` — la question que le sujet annonce

> *« what happens to the solution quality when the penalty weight is too small or too large »*

C'est écrit dans le sujet. **On te posera cette question.** Voici la réponse complète.

### Le raisonnement pour trouver le bon `P`

On veut : **aucune solution infaisable ne doit avoir une énergie meilleure qu'une solution faisable.**

Passons de `B` bornes à `B+1` bornes :

- **Gain** de couverture : au **maximum** `max_i Wᵢ` (le meilleur candidat, au mieux, apporte tout son poids).
- **Coût** de pénalité : `P·(B+1−B)² − P·(B−B)² = P·1 − 0 = P`.

Donc violer le budget est désavantageux **si et seulement si** :

```
              ┌──────────────────┐
              │  P  >  maxᵢ Wᵢ   │
              └──────────────────┘
```

Vérifions dans l'autre sens, `B → B−1` :

- **Gain** de pénalité : `0 − P = −P` (on paie `P`, c'est un coût).
- **Gain** de couverture : négatif (on perd au plus `max_i Wᵢ`).

Même condition. ✅ La borne est **symétrique**, elle verrouille les deux côtés.

**Valeur par défaut retenue :**

```python
def auto_penalty(W) -> float:
    """P juste au-dessus du gain marginal maximal d'une borne supplémentaire."""
    return 1.1 * float(np.max(W)) if len(W) else 1.0
```

Le facteur `1.1` donne une marge de 10 % sans écraser le signal. C'est le compromis.

### Ce qui se passe quand `P` est mal choisi

#### 🔻 `P` trop petit (ex. `P = 0.1 × max Wᵢ`)

La pénalité ne couvre pas le gain. L'optimiseur découvre qu'ajouter une 4ᵉ, 5ᵉ, 6ᵉ borne
améliore l'énergie. Il construit **au-delà du budget**.

```
Résultat : QAOA renvoie 6 bornes pour un budget de 3.
           → SOLUTION INFAISABLE. Elle ne veut rien dire.
```

**Dans notre application :** on détecte ce cas et on l'affiche explicitement — la solution
est marquée **« infaisable (budget violé) »** dans le panneau de métriques. On ne la cache pas :
on s'en sert comme démonstration.

#### 🔺 `P` trop grand (ex. `P = 10⁶ × max Wᵢ`)

Le piège est plus subtil, et c'est celui que les gens comprennent mal. La solution
reste **faisable** — mais elle devient **mauvaise**. Pourquoi ?

⚠️ **Précision importante** : puisqu'on a remplacé `≤ B` par `= B`, la pénalité ne vaut
zéro que pour les états qui **saturent** le budget (`|S| = B` exactement). Un placement
à `|S| < B` est pénalisé, lui aussi. Ce sont donc les `C(N,B)` états à `|S| = B` — **84**
sur notre instance — qui se disputent réellement l'optimum, et c'est entre eux que le
contraste doit rester lisible.

Regarde l'ordre de grandeur des énergies :

```
Énergie ≈ [ terme de couverture, amplitude ~ 30 ]  +  [ terme de pénalité, échelle ~ P·N² ]
```

Entre deux états à `|S| = B`, la pénalité est identique (nulle) : ils ne diffèrent que par
la couverture, quelques dizaines. Mais l'**échelle totale** du paysage, elle, croît en `P`.

**Mesuré sur notre instance** — contraste = (écart d'énergie entre états à `|S|=B`) / (échelle totale) :

| `P / max Wᵢ`  | Contraste         |
| ---------------- | ----------------- |
| 1,1*(défaut)* | `4,0 × 10⁻²` |
| 10               | `4,2 × 10⁻³` |
| 10³             | `4,2 × 10⁻⁵` |
| 10⁶             | `4,2 × 10⁻⁸` |

**Loi : contraste ∝ 1/P.** Le signal de couverture s'évanouit proportionnellement.

Conséquences en chaîne :

1. **Le paysage énergétique devient plat.** Vu à l'échelle de `P`, toutes les solutions
   faisables ont quasiment la même énergie. Le relief qui distingue la bonne solution de
   la mauvaise est écrasé.
2. **L'optimiseur classique perd ses gradients.** COBYLA compare `F(γ,β)` en différents
   points. Si l'écart entre une bonne et une mauvaise solution est `10⁻⁴` en relatif,
   il est noyé dans le **bruit d'échantillonnage** (on estime `F` avec un nombre fini de shots).
   L'optimiseur suit du bruit, pas du signal.
3. **Les angles QAOA deviennent inopérants.** Les rotations `RZ(2γ·coefficient)` avec des
   coefficients énormes font tourner les phases de plusieurs tours complets (`mod 2π`),
   et une variation infime de `γ` change tout. **La surface `F(γ,β)` devient hautement
   oscillante** — impossible à optimiser.

```
Résultat : QAOA renvoie une solution FAISABLE mais MÉDIOCRE.
           3 bornes (budget respecté ✅) mais une couverture bien en dessous de l'optimum.
```

> 🔑 **La nuance qui prouve que tu as vraiment compris :** avec un `P` énorme, **l'état
> fondamental du QUBO reste le bon**. Si tu énumérais les `2^N` énergies, tu retrouverais
> l'optimum exact. Ce qui casse, ce n'est pas la **formulation** — c'est l'**optimisation** :
> COBYLA ne distingue plus le signal du bruit d'échantillonnage.
>
> **Un `P` trop petit corrompt le problème. Un `P` trop grand corrompt le solveur.**
> Ce ne sont pas deux versions du même défaut : ce sont deux défaillances de nature
> différente, et il faut savoir les distinguer.

### Le résumé visuel à retenir

```
   Qualité
   ▲
84%│              ╭────────────╮
   │             ╱              ╲
   │            ╱                ╲___
   │           ╱                     ╲____
52%│          ╱                           ╲─────────
   │  ╱──────╯                                     
   │ ╱  INFAISABLE  │    ZONE SAINE    │   PAYSAGE PLAT
 0%│╱  budget violé │  P ≈ 1.1·max Wᵢ  │  gradients noyés
   └────────────────┼──────────────────┼──────────────────► P
                 max Wᵢ            ~10× max Wᵢ
```

### 🎤 Ce qu'on met dans l'UI pour le démontrer en direct

Le slider `P` est exposé dans le panneau de configuration, avec une case **« auto »** cochée
par défaut. En soutenance, tu décoches, tu glisses vers la gauche → **le jury voit QAOA
sortir 6 bornes pour un budget de 3**. Tu glisses à fond à droite → **il voit la couverture
s'effondrer alors que le budget reste respecté.**

> **Tu ne récites pas la réponse. Tu la montres.** C'est la différence entre « j'ai compris »
> et « je sais faire ».

---

# 6. Du QUBO à l'Hamiltonien

Fichier : `backend/qubo.py` (suite)

## 6.1 Pourquoi cette étape ?

Un QUBO manipule des variables `xᵢ ∈ {0,1}`.
Un ordinateur quantique manipule des **qubits**, dont les observables naturelles sont les
matrices de **Pauli-Z**, de valeurs propres `zᵢ ∈ {−1, +1}` :

```
Z|0⟩ = +1·|0⟩          Z|1⟩ = −1·|1⟩
```

Il faut donc traduire `{0,1}` → `{−1,+1}`.

## 6.2 Le changement de variable

```
              ┌─────────────────┐
              │  xᵢ = (1 − zᵢ)/2 │
              └─────────────────┘

zᵢ = +1  (état |0⟩)  →  xᵢ = 0   « je ne construis pas »
zᵢ = −1  (état |1⟩)  →  xᵢ = 1   « je construis »
```

## 6.3 La transformation

Pour les termes quadratiques :

```
xᵢxₖ = (1−zᵢ)(1−zₖ)/4 = (1 − zᵢ − zₖ + zᵢzₖ)/4
```

En substituant dans `E(x) = Σᵢ Qᵢᵢxᵢ + Σᵢ<ₖ Qᵢₖxᵢxₖ + c` et en regroupant :

```
┌──────────────────────────────────────────────────────────┐
│  hᵢ     = − Qᵢᵢ/2  −  (1/4)·Σ_{k≠i} Qᵢₖ        (champ)   │
│  Jᵢₖ    = Qᵢₖ/4                             (couplage)   │
│  offset = Σᵢ Qᵢᵢ/2  +  Σᵢ<ₖ Qᵢₖ/4  +  c                  │
└──────────────────────────────────────────────────────────┘
```

⚠️ Dans `Σ_{k≠i} Qᵢₖ`, il faut sommer **toute la ligne et toute la colonne** de `i`
(la matrice est triangulaire supérieure, donc `Qᵢₖ` avec `k<i` est stocké en `Q[k][i]`).

L'**Hamiltonien de coût** est alors :

```
  ┌───────────────────────────────────────────────────┐
  │  H_C = Σᵢ hᵢ·Zᵢ  +  Σᵢ<ₖ Jᵢₖ·ZᵢZₖ  +  offset·I   │
  └───────────────────────────────────────────────────┘
```

## 6.4 Propriété fondamentale : `H_C` est diagonal

`Z` est diagonale. Un produit de `Z` est diagonal. Une somme de matrices diagonales
est diagonale. Donc :

> **`H_C` est diagonal dans la base de calcul.**
>
> Chaque état de base `|x⟩` (par exemple `|101⟩`) est un **état propre** de `H_C`, et sa
> valeur propre est **exactement** l'énergie QUBO `E(x)`.

C'est ce qui rend tout le projet possible :

```
H_C|x⟩ = E(x)·|x⟩
```

**Trouver l'état fondamental de `H_C`** (celui d'énergie minimale) **est exactement
équivalent à résoudre le QUBO.** On a traduit un problème d'optimisation combinatoire en
un problème de **physique** : trouver l'état de plus basse énergie d'un système de spins.

```python
def qubo_to_ising(Q, offset):
    n = Q.shape[0]
    Qs = Q + Q.T - np.diag(np.diag(Q))    # matrice symétrisée, diagonale préservée
    h = np.zeros(n)
    J = {}
    for i in range(n):
        row_sum = sum(Qs[i, k] for k in range(n) if k != i)
        h[i] = -Q[i, i] / 2 - row_sum / 4
    for i in range(n):
        for k in range(i + 1, n):
            if Q[i, k] != 0:
                J[(i, k)] = Q[i, k] / 4
    ising_offset = offset + np.sum(np.diag(Q)) / 2 + sum(J.values())
    return h, J, ising_offset
```

> ✅ **Test à écrire absolument :** pour tous les `2^N` vecteurs `x`, vérifier que
> `qubo_energy(Q, offset, x) == ising_energy(h, J, off, 1-2x)` à `1e-9` près.
> Si ce test passe, ta transformation est **prouvée correcte**, et tu peux le dire au jury.

---

# 7. QAOA

Fichier : `backend/solvers/qaoa.py`

## 7.1 D'où ça vient : le théorème adiabatique

Pour comprendre QAOA, il faut comprendre d'où il sort. Ce n'est pas une recette magique.

**Le théorème adiabatique** (Born & Fock, 1928) dit :

> Si un système quantique est dans l'**état fondamental** d'un Hamiltonien `H(0)`, et qu'on
> transforme **suffisamment lentement** `H(0)` en `H(1)`, alors le système reste dans
> l'état fondamental et finit dans celui de `H(1)`.

L'idée du **calcul quantique adiabatique** :

1. On part d'un Hamiltonien `H_M` dont l'état fondamental est **facile** à préparer.
2. On l'évolue lentement vers `H_C`, notre Hamiltonien de coût.
3. On mesure : on obtient l'état fondamental de `H_C`, c'est-à-dire **la solution du QUBO**.

### Le mixer `H_M`

```
H_M = Σᵢ Xᵢ            (X = porte de Pauli-X, le "NOT" quantique)
```

Son état fondamental est la **superposition uniforme** de tous les états :

```
|+⟩^⊗N = (1/√(2^N)) · Σ_{x ∈ {0,1}^N} |x⟩
```

Elle se prépare avec **N portes de Hadamard**. Une seule couche de portes.
C'est l'état « **je suis dans toutes les solutions possibles à la fois** ».

### Le problème avec l'adiabatique

Il faut aller **lentement**. Et « suffisamment lentement » dépend du **gap spectral**
(l'écart d'énergie entre le fondamental et le premier excité), qui pour un problème
NP-difficile peut devenir **exponentiellement petit**. Il faudrait donc un temps
**exponentiel**. Et ça demande une évolution continue, que les machines à portes ne font pas.

## 7.2 L'idée de QAOA : discrétiser

**QAOA** (Farhi, Goldstone & Gutmann, 2014) = **Q**uantum **A**pproximate **O**ptimization **A**lgorithm.

L'idée : **approximer** l'évolution adiabatique continue par un nombre **fini** `p` d'étapes
discrètes, en alternant les deux Hamiltoniens :

```
                 ┌────────────────────────────────────────────────────┐
  |ψ(γ,β)⟩  =    │  Π_{l=1}^{p} [ e^{−iβ_l H_M} · e^{−iγ_l H_C} ]  |+⟩^N │
                 └────────────────────────────────────────────────────┘
```

Et au lieu de calculer les bonnes durées `γ_l, β_l` théoriquement (impossible), on les
**optimise numériquement** avec un optimiseur **classique**. D'où le nom d'algorithme
**variationnel** (ou **hybride**).

## 7.3 Le circuit, porte par porte

```
       ┌───┐                                                            
q₀ ────┤ H ├──┬───── e^{−iγ₁H_C} ─────┬──── e^{−iβ₁H_M} ────┬─ … ─┬─ M ─
       ├───┤  │                        │                      │      │
q₁ ────┤ H ├──┤     (diagonal,         │     (rotations X     │      │ M ─
       ├───┤  │      RZ + CX·RZ·CX)    │      indépendantes)  │      │
q₂ ────┤ H ├──┴────────────────────────┴──────────────────────┴─ … ─┴─ M ─
       └───┘  └──────────────── couche 1 (γ₁,β₁) ─────────────┘
                                                               2p paramètres
```

### Étape 1 — Initialisation

```python
qc = QuantumCircuit(n)
qc.h(range(n))          # superposition uniforme, l'état fondamental de H_M
```

### Étape 2 — Le layer de coût `e^{−iγ H_C}`

`H_C` étant **diagonal**, son exponentielle se décompose **exactement** (pas d'approximation
de Trotter nécessaire — tous les termes commutent !) :

**Termes de champ** `e^{−iγ hᵢ Zᵢ}` :

```python
for i in range(n):
    qc.rz(2 * gamma * h[i], i)      # RZ(θ) = e^{−iθZ/2}, d'où le facteur 2
```

**Termes de couplage** `e^{−iγ Jᵢₖ ZᵢZₖ}` — l'astuce standard :

```python
for (i, k), Jik in J.items():
    qc.cx(i, k)
    qc.rz(2 * gamma * Jik, k)       # CX · RZ · CX  ≡  e^{−iθ Z_i Z_k / 2}
    qc.cx(i, k)
```

> 🔍 **Pourquoi `CX · RZ · CX` réalise `ZZ` ?** Le `CX(i,k)` transforme la base de `k` en la
> **parité** de `i` et `k`. La rotation `RZ` sur `k` applique donc une phase qui dépend de
> `zᵢ · zₖ`. Le second `CX` restaure la base. C'est la décomposition canonique.

### Étape 3 — Le layer mixer `e^{−iβ H_M}`

`H_M = ΣXᵢ`, les termes commutent, c'est juste `N` rotations indépendantes :

```python
qc.rx(2 * beta, range(n))
```

### Étape 4 — Mesure

```python
qc.measure_all()
```

### Le circuit complet

```python
def build_qaoa_circuit(h, J, gammas, betas):
    n = len(h)
    p = len(gammas)
    qc = QuantumCircuit(n)
    qc.h(range(n))
    for layer in range(p):
        g, b = gammas[layer], betas[layer]
        # --- cost layer ---
        for i in range(n):
            if h[i] != 0:
                qc.rz(2 * g * h[i], i)
        for (i, k), Jik in J.items():
            qc.cx(i, k)
            qc.rz(2 * g * Jik, k)
            qc.cx(i, k)
        # --- mixer layer ---
        for i in range(n):
            qc.rx(2 * b, i)
    qc.measure_all()
    return qc
```

### Coût en portes — important pour la courbe de complexité (§9)

| Élément                              | Nombre de portes          |
| -------------------------------------- | ------------------------- |
| Hadamard initiales                     | `N`                     |
| Par couche :`RZ` de champ            | `N`                     |
| Par couche :`CX·RZ·CX` de couplage | `3 ·                     |
| Par couche :`RX` du mixer            | `N`                     |
| **Total**                        | **`O(p · N²)`** |

**`O(p·N²)` est POLYNOMIAL en N.** C'est **tout l'argument du projet**. Retiens ce chiffre.

## 7.4 La boucle variationnelle : qui fait quoi

C'est la question n°2 du chapitre « Understanding » du sujet :
*« The difference between the classical optimization loop and the quantum circuit inside
QAOA, and how the two cooperate. »*

```
                  ╔═══════════════════════════════════════════╗
                  ║        BOUCLE HYBRIDE QAOA                ║
                  ╚═══════════════════════════════════════════╝

      💻 CÔTÉ CLASSIQUE (CPU)              ⚛️  CÔTÉ QUANTIQUE (QPU / simulateur)
      ─────────────────────────            ──────────────────────────────────────

      (γ, β) initiaux
            │
            ├──────── envoie (γ,β) ───────► construit le circuit avec ces angles
            │                                            │
            │                                    exécute le circuit
            │                                            │
            │                                    mesure N_shots fois
            │                                            │
            │◄────── renvoie ⟨H_C⟩ ──────────  estime l'énergie moyenne
            │
      COBYLA analyse : « est-ce
      mieux qu'avant ? dans quelle
      direction pousser (γ,β) ? »
            │
            ├──── nouveaux (γ,β) ─────────►  … et on recommence
            │
      convergence atteinte
            │
            ▼
      on échantillonne une dernière fois
      et on garde le MEILLEUR bitstring
```

### La répartition des rôles, en une phrase chacun

|                                    | Rôle                                                                                                                                                                                             |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ⚛️**Le circuit quantique** | il**prépare un état** `                                                                                                                                                                   |
| 💻**L'optimiseur classique** | il**cherche les bons `(γ,β)`**. Il ne voit du monde quantique qu'**un seul nombre** : `⟨H_C⟩`. C'est une optimisation continue de `2p` paramètres réels, en boîte noire. |

> 💬 **La phrase qui montre que tu as compris :**
> *« Le quantique n'optimise rien. Il prépare une distribution. C'est le classique qui
> optimise — mais il optimise les angles du circuit, pas la solution du problème.
> La solution émerge de la mesure. »*

### L'interférence : pourquoi ça peut marcher

Voici le mécanisme physique sous-jacent, en une image.

Après les Hadamard, les `2^N` solutions ont **toutes la même amplitude**. Le layer de coût
`e^{−iγH_C}` donne à chaque état `|x⟩` une **phase** `e^{−iγE(x)}` — **proportionnelle à
son énergie**. Les bonnes solutions et les mauvaises reçoivent des phases différentes.

Puis le mixer `e^{−iβH_M}` fait **interférer** ces états entre eux (`X` mélange `|0⟩` et `|1⟩`,
donc chaque état se mélange avec ses **voisins à un bit de distance**).

Les phases s'ajoutent (**interférence constructive**) pour les bonnes solutions, et se
compensent (**interférence destructive**) pour les mauvaises — **si `γ` et `β` sont bien choisis**.
D'où la nécessité de la boucle d'optimisation.

> C'est exactement le mécanisme de Grover que tu as vu en `ftl_quantum` (oracle de phase +
> diffuseur), mais ici l'« oracle » encode une **énergie continue** au lieu d'un
> marquage binaire, et les angles sont **appris** au lieu d'être fixés analytiquement.
> **Faire ce lien en soutenance est très fort.**

### Le code de la boucle

```python
from scipy.optimize import minimize
from qiskit_aer import AerSimulator
from qiskit.quantum_info import Statevector

def solve_qaoa(instance, p=3, maxiter=150, shots=4096, seed=42):
    Q, offset, penalty = build_qubo(instance)
    h, J, ising_offset = qubo_to_ising(Q, offset)
    n = instance.n_candidates

    energies = precompute_all_energies(Q, offset, n)   # vecteur de taille 2^N
    trace = []                                          # pour le bonus convergence

    def cost(params):
        gammas, betas = params[:p], params[p:]
        qc = build_qaoa_circuit(h, J, gammas, betas)
        # Pas de mesure pour l'espérance : on lit le vecteur d'état, c'est exact et rapide
        probs = Statevector(qc.remove_final_measurements(inplace=False)).probabilities()
        value = float(np.dot(probs, energies))
        trace.append(value)
        return value

    # Initialisation "adiabatique" : γ croît, β décroît — bien meilleure qu'aléatoire
    x0 = np.concatenate([
        np.linspace(0.1, 1.0, p) / max(1.0, np.abs(list(J.values())).max()),
        np.linspace(1.0, 0.1, p),
    ])

    res = minimize(cost, x0, method="COBYLA", options={"maxiter": maxiter})

    # --- échantillonnage final ---
    qc = build_qaoa_circuit(h, J, res.x[:p], res.x[p:])
    counts = AerSimulator(seed_simulator=seed).run(qc, shots=shots).result().get_counts()

    # On évalue les bitstrings les plus fréquents avec la VRAIE fonction objectif
    best = None
    for bitstring in sorted(counts, key=counts.get, reverse=True)[:64]:
        sel = bitstring_to_selection(bitstring, n)
        if len(sel) > instance.budget:          # on écarte les infaisables
            continue
        weight, _ = coverage(sel, instance)     # ← objective.py, la source de vérité
        if best is None or weight > best.weight:
            best = Candidate(sel, weight)

    return QaoaResult(
        selection=best.selection,
        covered_weight=best.weight,
        iterations=res.nfev,                    # ← exigé par le sujet
        shots=shots,
        layers=p,
        penalty=penalty,
        energy_trace=trace,                     # ← bonus convergence
    )
```

### ⚠️ Deux points d'honnêteté à documenter

1. **On lit le vecteur d'état pour l'espérance, pas des shots.** Sur simulateur c'est
   **exact** (pas de bruit statistique) et plus rapide. Sur hardware réel, ce serait
   impossible : il faudrait estimer `⟨H_C⟩` par échantillonnage. **Il faut le dire.**
   (Le bonus « bruit » réintroduit l'échantillonnage réaliste.)
2. **On post-sélectionne le meilleur bitstring mesuré.** Ce n'est **pas** de la triche :
   c'est le protocole QAOA **canonique**. La sortie de QAOA *est* une distribution ; on
   l'échantillonne et on garde le meilleur tirage. Le nombre de shots fait partie du coût
   reporté. On écarte les bitstrings infaisables (plus de `B` bornes) — sauf en mode
   « démonstration de pénalité », où on les laisse passer pour **montrer** l'effet d'un `P` trop petit.

## 7.5 ⚠️ Le piège de l'échelle des angles — le bug le plus instructif du projet

**Celui-ci, tu l'as vécu. Raconte-le : rien ne prouve mieux qu'on a compris un algorithme
que d'expliquer comment on l'a réparé.**

### Le symptôme

QAOA renvoyait systématiquement des solutions sous-optimales. Pire : **augmenter `p`
n'améliorait rien, et le dégradait parfois.** Or un ansatz plus expressif ne peut pas être
*intrinsèquement* pire — à `p+1` couches, on peut toujours imiter `p` couches en mettant les
angles de la dernière à zéro. **Ce symptôme prouvait donc que le problème était dans
l'optimiseur, pas dans le circuit.**

### Le diagnostic

En balayant exhaustivement le paysage à `p = 1` (2 paramètres seulement, donc traçable) :

```
vrai optimum du paysage   :  ⟨H⟩ = −13,77   à  γ = 0,0201
ce que COBYLA trouvait    :  ⟨H⟩ =  −6,76   à  γ = 1,154     ← 57× plus loin
```

### La cause racine

Le layer de coût applique `RZ(2γ·coefficient)`. Les coefficients de l'Ising valent ici
~15,5. Donc :

```
période de F en γ  ≈  2π / 15,5  ≈  0,40          et  γ_optimal ≈ 0,02
```

Or **COBYLA démarre avec un rayon de simplexe `rhobeg = 1.0` par défaut**. Son *premier pas*
faisait donc 50× la largeur de toute la plage utile de `γ`. Il traversait plusieurs
oscillations complètes de la surface et atterrissait dans un bassin local arbitraire.

> **Ce n'était pas un défaut de QAOA. C'était une inadéquation d'échelle entre le
> paramétrage et l'optimiseur.**

### Le correctif

Optimiser sur `γ̃ = γ · scale`, dont la période naturelle devient `2π` — la même échelle
que `β`. Les deux familles de paramètres vivent alors sur `O(1)`, et `rhobeg` redevient
pertinent pour les deux.

```python
scale = max(max|hᵢ|, max|Jᵢₖ|)
γ = γ̃ / scale                       # γ̃ ∈ [0, 2π],  β ∈ [0, π]
minimize(..., method="COBYLA", options={"rhobeg": 0.5})
```

### Le résultat, mesuré

|                               | Avant      | Après                                          |
| ----------------------------- | ---------- | ----------------------------------------------- |
| `⟨H⟩` à `p=1`          | −6,76     | **−13,80** (optimum exhaustif : −13,77) |
| `p` améliore la qualité ? | ❌ non     | ✅ oui, monotonement                            |
| `P(optimum)` à `p=3`     | ~1 %       | **5,3 %**                                 |
| Optimum atteint sur 20 seeds  | aléatoire | **20/20**                                 |

> 💬 **En soutenance :** *« Mon premier QAOA ne trouvait jamais l'optimum, et augmenter le
> nombre de couches ne changeait rien — ce qui est impossible si l'ansatz est en cause, donc
> j'ai su que c'était l'optimiseur. En traçant le paysage à p=1, j'ai vu que COBYLA
> atterrissait 57× à côté du vrai optimum. La cause : γ vit sur une échelle 1/coefficient,
> soit ~0,02, alors que le rayon initial du simplexe de COBYLA vaut 1 par défaut. J'ai
> normalisé γ pour que sa période soit 2π comme β, et je passe de 1 % à 5 % de probabilité
> sur l'optimum, avec 20/20 de réussite. »*

## 7.6 Le choix de l'optimiseur — mesuré, pas supposé

Comparaison sur l'instance de référence, `p = 3`, 4 redémarrages :

| Optimiseur       | Évaluations  | `P(optimum)`  | Verdict                                         |
| ---------------- | ------------- | --------------- | ----------------------------------------------- |
| **COBYLA** | **600** | **5,6 %** | ✅ retenu                                       |
| Powell           | 2 731         | 4,6 %           | meilleure`⟨H⟩`, mais 4,5× plus d'appels    |
| Nelder-Mead      | 2 098         | 1,6 %           |                                                 |
| SLSQP            | 1 077         | 0,5 %           | ❌ gradient par différences finies : inadapté |

**COBYLA atteint la meilleure qualité avec 4,5× moins d'évaluations.** C'est décisif : sur
un vrai QPU, chaque évaluation est un envoi de circuit qui coûte des **secondes**. Le
nombre d'appels est la ressource critique, pas le temps CPU de l'optimiseur.

> ⚠️ **À savoir si on te chronomètre :** depuis SciPy 1.15, COBYLA n'est plus l'implémentation
> Fortran historique mais un portage **Python pur** (`pyprima`). Son surcoût est d'environ
> 3,4 ms par itération — **plus cher que l'évaluation du circuit lui-même** sur une petite
> instance. C'est un artefact d'implémentation, pas une propriété de l'algorithme, et il
> faut le dire si on présente des mesures de temps.

## 7.7 Le nombre de couches `p`

| `p`      | Effet                                                                                                      |
| ---------- | ---------------------------------------------------------------------------------------------------------- |
| `p = 1`  | très peu expressif, une seule « étape » d'adiabatique. Qualité médiocre.                             |
| `p = 3`  | **notre défaut.** Bon compromis qualité / temps de simulation.                                     |
| `p = 6+` | meilleure qualité théorique, mais`12` paramètres à optimiser → COBYLA galère, et le temps explose. |

**Garantie théorique :** quand `p → ∞`, QAOA retrouve l'évolution adiabatique et donc
**converge vers l'optimum exact**. Pour `p` fini, c'est approché — d'où le « **A**pproximate »
dans le nom.

## 7.8 Le plafond du simulateur — exigence explicite du sujet

> *« Simulating QAOA stores 2^N complex amplitudes and recomputes them at every optimization
> step, so it costs O(2^N) in both time and memory. […] When the user pushes N past it, the
> quantum solve should degrade or be skipped **gracefully**, not freeze the application. »*

### Le calcul de mémoire

Un `complex128` fait **16 octets**. Le vecteur d'état fait `2^N` amplitudes :

| N  | Mémoire du statevector | Simulable ?                     |
| -- | ----------------------- | ------------------------------- |
| 10 | 16 Ko                   | trivial                         |
| 16 | 1 Mo                    | ✅ instantané                  |
| 20 | 16 Mo                   | ✅ ok                           |
| 24 | 256 Mo                  | ⚠️ lent (×150 itérations !) |
| 28 | 4 Go                    | ❌ saturé                      |
| 32 | 64 Go                   | ❌ impossible                   |
| 50 | 16**pétaoctets** | ❌ absurde                      |

Et il faut le **recalculer à chaque itération** de COBYLA (~150 fois).

### L'implémentation du garde-fou

```python
QAOA_MAX_QUBITS = 16       # configurable via variable d'environnement

if instance.n_candidates > QAOA_MAX_QUBITS:
    return QaoaResult(
        skipped=True,
        reason=(
            f"N = {instance.n_candidates} dépasse le plafond du simulateur "
            f"({QAOA_MAX_QUBITS} qubits). Simuler {instance.n_candidates} qubits "
            f"demanderait {2**instance.n_candidates * 16 / 1e9:.1f} Go de RAM, "
            f"recalculés à chaque itération. "
            f"Ce plafond est celui du SIMULATEUR, pas de l'algorithme : "
            f"sur un vrai QPU le circuit utiliserait {instance.n_candidates} qubits "
            f"et O(p·N²) = {3 * instance.n_candidates**2} portes."
        ),
    )
# → le solveur classique, lui, continue de tourner normalement
```

> ⭐ **Le message est pédagogique, pas seulement défensif.** Il transforme une limite
> technique en **argument du projet** : ce n'est pas l'algorithme qui plafonne, c'est
> l'émulation classique. Un vrai QPU n'aurait pas ce problème. **C'est exactement le
> point que le sujet veut te faire comprendre.**

---

# 8. L'honnêteté scientifique

> 🔴 **Le sujet consacre deux encadrés entiers à ce point.** C'est un test de maturité
> scientifique. Une soutenance où tu prétends que le quantique « gagne » est une soutenance
> ratée, même si tout le code marche.

## 8.1 Ce que le sujet écrit

> *« Be honest about what the side-by-side comparison actually shows on your machine.
> Brute force is exact, so the coverage of QAOA can at best equal it and never beat it.
> And because you simulate the quantum circuit on a CPU, QAOA is also slower than brute
> force on these small instances. This is expected. It is not a failure of your project.
> […] **do not claim a quantum "win" that the numbers do not show.** »*

## 8.2 Les trois vérités à énoncer sans détour

### Vérité n°1 — QAOA ne peut **jamais** battre la brute force en couverture

La brute force est **exacte** : elle renvoie l'optimum global, par construction.
Il n'existe donc, par définition, **rien de mieux**. QAOA peut au mieux **égaler**.

```
couverture(QAOA)  ≤  couverture(brute force)      TOUJOURS.
```

Si ton application affichait QAOA > brute force, **ça voudrait dire que ta brute force
est buguée**. C'est d'ailleurs un excellent test.

### Vérité n°2 — QAOA est **plus lent** ici, et c'est structurel

Ce n'est pas une question d'optimisation de code. Le compte :

```
Temps QAOA ≈ (nb itérations COBYLA) × (coût de simulation d'un circuit)
           ≈ 150 × O(2^N × nb_portes)
           ≈ 150 × O(2^N × p·N²)

Temps brute force ≈ O(C(N,B) × M)
```

Sur `N = 9, B = 3` : brute force ≈ **130 × 150 = 19 500** opérations → quelques millisecondes.
QAOA ≈ **150 × 512 × 250 ≈ 19 millions** d'opérations → une à deux secondes.

**QAOA est ~100 à 1000× plus lent. C'est normal.**

### Vérité n°3 — On **simule**, donc on paie deux fois

C'est le point le plus important, et le plus mal compris.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Sur un VRAI processeur quantique :                                      │
│      N qubits, O(p·N²) portes, temps d'exécution POLYNOMIAL en N         │
│                                                                           │
│  Sur un SIMULATEUR classique (ce qu'on fait ici) :                       │
│      on doit stocker et faire évoluer 2^N amplitudes complexes           │
│      → coût EXPONENTIEL en N                                             │
└──────────────────────────────────────────────────────────────────────────┘
```

**On paie le coût exponentiel qu'on prétend éviter.**

C'est contre-intuitif mais c'est logique : **simuler un système quantique sur une machine
classique est exponentiellement coûteux**. C'est précisément *pourquoi* on veut construire
des ordinateurs quantiques — un système quantique est le seul objet capable de se simuler
lui-même efficacement.

> 💬 **La phrase de Feynman à citer :**
> *« Nature isn't classical, dammit, and if you want to make a simulation of nature,
> you'd better make it quantum mechanical. »* — Richard Feynman, 1981.
>
> Notre projet **est** l'illustration de cette phrase.

## 8.3 La ligne de verdict

Le sujet montre une capture avec une **ligne de verdict** explicite. On la génère
**dynamiquement à partir des vrais chiffres** — jamais en dur :

```python
def build_verdict(classical, quantum):
    if quantum.skipped:
        return (f"QAOA ignoré : {quantum.reason} "
                f"Le solveur classique a trouvé l'optimum en {classical.time_ms:.0f} ms.")

    speedup = quantum.time_ms / classical.time_ms
    if quantum.covered_weight >= classical.covered_weight - 1e-9:
        quality = "QAOA a atteint la couverture optimale"
    else:
        gap = 100 * (1 - quantum.covered_weight / classical.covered_weight)
        quality = f"QAOA est à {gap:.1f} % sous l'optimum"

    return (
        f"À cette échelle, le solveur CLASSIQUE gagne : il est exact et "
        f"{speedup:.0f}× plus rapide. {quality}. "
        f"L'avantage quantique n'est PAS ici — il est ASYMPTOTIQUE : "
        f"la force brute explore {classical.combinations:,} combinaisons contre "
        f"{quantum.gate_count} portes pour le circuit QAOA. "
        f"Regardez la courbe de complexité ci-dessous."
    )
```

## 8.4 Alors pourquoi faire du quantique ?

Parce que l'argument n'est **pas** sur une instance. Il est sur la **croissance**.

```
  Coût
  ▲
  │                                        ╱  brute force : 2^N
  │                                      ╱
  │                                    ╱
  │                                  ╱
  │                                ╱
  │                             ╱
  │                        ╱
  │                  ╱
  │           ╱ ─────────────────────────  QAOA sur QPU : O(p·N²)
  │      ╱ ───────
  │ ─────
  └──────────┬─────────────────────┬──────────────────────────────► N
             │                     │
        ici (N=9),            quelque part ici,
      le classique gagne      les courbes se croisent
```

Le croisement existe **mathématiquement**, parce qu'une exponentielle finit **toujours**
par dépasser un polynôme, quelles que soient les constantes.

**Où ?** Personne ne le sait avec certitude — ça dépend de la qualité du hardware, du bruit,
du nombre de couches nécessaires. Les estimations sérieuses parlent de **centaines à
milliers de qubits logiques de bonne qualité**. On n'y est pas.

**Mais c'est précisément l'objet de ce projet** : montrer *où* se trouve l'argument,
pas prétendre qu'il est déjà gagné.

---

# 9. La courbe de complexité

> Le sujet : *« The complexity growth curve is the single most important visual of the project. »*

Fichier : `frontend/js/charts.js` + route `GET /api/complexity`

## 9.1 Ce qu'on trace

**Axe X :** `N`, le nombre de candidats (de 2 à ~60).
**Axe Y :** le **travail computationnel** (nombre d'opérations), en **échelle logarithmique**.

> ⚠️ Le sujet précise : *« This axis is computational **work** (operations, proportional to
> runtime). **It is not memory.** The brute force walks the search space one combination at
> a time, so its memory stays small. »*
> **Ne te trompe pas en soutenance.** C'est du **travail**, pas de la mémoire.

### Les quatre courbes

| Courbe                                         | Formule                                     | Nature                     | Couleur suggérée  |
| ---------------------------------------------- | ------------------------------------------- | -------------------------- | ------------------- |
| **Espace de recherche complet**          | `2^N`                                     | exponentielle              | rouge, trait plein  |
| **Brute force réelle** (budget courant) | `Σₖ≤B C(N,k)`                          | polynomiale de degré`B` | orange, pointillés |
| **Circuit QAOA sur QPU**                 | `p·(2N + 3·N(N−1)/2)` ≈ `O(p·N²)` | polynomiale de degré 2    | vert, trait plein   |
| **Simulation QAOA sur CPU**              | `iters · 2^N · portes`                  | exponentielle              | violet, pointillés |

### Pourquoi quatre et pas deux

C'est ce qui fait la différence entre un projet correct et un projet excellent.

- Les courbes **1 vs 3** portent l'argument principal : **exponentiel vs polynomial**.
- La courbe **2** est **l'honnêteté** : elle montre ce que ta brute force fait *vraiment*
  avec le `B` courant. Elle désarme d'avance l'objection de la section 4.3.
- La courbe **4** est **la leçon du projet** : elle montre que ta *simulation* est, elle aussi,
  exponentielle — et **pire que la brute force**. Elle explique visuellement pourquoi
  QAOA est plus lent sur ta machine, **sans rien cacher**.

> 💬 **La phrase à dire en montrant le graphe :**
> *« Regardez : la courbe violette — ma simulation — est au-dessus de la rouge. Sur ma
> machine, le quantique est le PIRE des deux. C'est attendu. La courbe qui compte est la
> verte : c'est ce que ferait un vrai QPU. Et elle est polynomiale. »*

## 9.2 L'échelle logarithmique

**Sur une échelle log, une exponentielle devient une droite.** C'est ce qui rend le graphe lisible :

```
log(2^N) = N · log(2)        → une DROITE de pente log(2)
log(N²)  = 2 · log(N)        → une COURBE qui s'aplatit
```

Sans échelle log, la courbe `2^N` sortirait de l'écran dès `N = 30` et on ne verrait
strictement plus rien. **Sache expliquer ce choix** — c'est une question classique.

## 9.3 Ce que ça veut dire pour un déploiement réel

C'est la dernière question du chapitre « Understanding » :
*« What the complexity growth curve means for a real-world deployment. »*

Ta réponse, structurée :

> **Notre instance de référence — 9 candidats, Lyon Presqu'île — est un jouet.**
> Une vraie étude de déploiement pour la Métropole de Lyon examinerait **des centaines**
> d'emplacements candidats, avec des contraintes bien plus riches (puissance disponible
> sur le réseau, propriété du foncier, accessibilité PMR, coûts de raccordement variables).
>
> **À cette échelle, la force brute est morte.** Avec 200 candidats, `2²⁰⁰ ≈ 10⁶⁰` —
> plus que le nombre d'atomes dans la Voie lactée. Ce n'est pas une question de patience
> ou de budget cloud : c'est **physiquement impossible**.
>
> **Ce que font les villes aujourd'hui**, concrètement : des **heuristiques** (glouton,
> recuit simulé, algorithmes génétiques) et des **solveurs MILP** (Gurobi, CPLEX) qui
> utilisent branch-and-bound pour élaguer l'espace de recherche. Ils sont excellents,
> mais ils n'offrent **aucune garantie** d'optimalité en temps polynomial dans le cas général.
>
> **Le pari du quantique**, c'est d'offrir une **classe d'approximation différente** :
> pas forcément meilleure que le meilleur solveur classique aujourd'hui, mais fondée sur
> une **mécanique différente** (interférence, tunneling quantique) qui pourrait, sur
> certaines structures de problème, explorer le paysage énergétique autrement.
>
> **Aujourd'hui, ce n'est pas encore vrai.** Le hardware est trop bruité et trop petit.
> Mais la question « **est-ce que ce sera vrai ?** » est une des questions ouvertes les
> plus sérieuses de l'informatique, et elle se joue exactement sur ce type de problème.

---

# 10. Les bonus

## 10.1 Recuit simulé (3ᵉ solveur)

Fichier : `backend/solvers/annealing.py`

### L'idée

Le **recuit simulé** (*simulated annealing*, Kirkpatrick 1983) s'inspire de la métallurgie :
on chauffe un métal puis on le refroidit **lentement** pour que ses atomes trouvent un
arrangement de basse énergie (un cristal régulier) plutôt que de se figer dans un désordre.

```
T ← T_initiale
x ← solution aléatoire faisable
tant que T > T_finale :
    x' ← voisin de x          (on déplace une borne)
    ΔE ← E(x') − E(x)
    si ΔE < 0 :               accepter          (c'est mieux → on prend)
    sinon :                   accepter avec probabilité exp(−ΔE / T)
                                               (c'est pire → on prend QUAND MÊME, parfois)
    T ← α·T                   (refroidissement géométrique, α ≈ 0.95)
```

### Le point clé : pourquoi accepter des solutions pires ?

Pour **s'échapper des minima locaux**. Un algorithme purement glouton se bloque dès qu'il
atteint un creux local. Le recuit, **quand il est chaud**, accepte de remonter — donc il
peut franchir une « colline » et découvrir un creux plus profond derrière.

Quand `T → 0`, `exp(−ΔE/T) → 0` : il devient purement glouton et se stabilise.

### Pourquoi c'est pertinent ici — le parallèle avec QAOA

C'est **exactement** l'analogue **thermique** de ce que QAOA fait **quantiquement** :

|                         | Recuit simulé                                                            | QAOA / recuit quantique                                          |
| ----------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Mécanisme d'évasion   | **fluctuations thermiques** — on *saute par-dessus* la barrière | **effet tunnel quantique** — on *traverse* la barrière |
| Paramètre de contrôle | température`T`, décroissante                                          | angles`(γ, β)`, optimisés                                   |
| Ce qui explore          | une trajectoire, un point à la fois                                      | une superposition, tous les états à la fois                    |
| Nature                  | stochastique classique                                                    | unitaire quantique + mesure                                      |

> 💬 **En soutenance :** *« Le recuit simulé est le point de comparaison le plus juste pour
> QAOA, bien plus que la force brute. Les deux sont des heuristiques approchées sur le
> MÊME QUBO. La force brute compare "exact vs approché" ; le recuit compare "approché
> classique vs approché quantique" — c'est la comparaison qui a vraiment du sens.
> Et c'est le même paysage énergétique : la seule différence est la façon de le parcourir. »*

**Et il est gratuit à implémenter** : il optimise **le même QUBO** que QAOA, avec le même
`build_qubo()`. ~40 lignes de code.

## 10.2 Simulation de bruit quantique

Fichier : `backend/solvers/qaoa.py` (mode `noisy=True`)

### Pourquoi c'est le bonus le plus instructif

Parce qu'il répond à la question « **pourquoi on n'utilise pas déjà des QPU ?** ».

### Les sources de bruit modélisées

| Type                                    | Cause physique                                               | Ordre de grandeur (hardware 2024)     |
| --------------------------------------- | ------------------------------------------------------------ | ------------------------------------- |
| **Erreur de porte 1-qubit**       | calibration imparfaite de l'impulsion micro-onde             | `~10⁻⁴`                           |
| **Erreur de porte 2-qubits** (CX) | couplage imparfait entre qubits                              | `~10⁻²` ⚠️ **100× pire** |
| **Décohérence** (T1, T2)        | le qubit perd son état par interaction avec l'environnement | `T1 ≈ 100 μs`                     |
| **Erreur de mesure**              | le détecteur se trompe en lisant                            | `~10⁻²`                           |

```python
from qiskit_aer.noise import NoiseModel, depolarizing_error

def build_noise_model(p1=1e-3, p2=1e-2):
    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(depolarizing_error(p1, 1), ["rz", "rx", "h"])
    nm.add_all_qubit_quantum_error(depolarizing_error(p2, 2), ["cx"])
    return nm
```

### Ce qu'on démontre avec

L'analyse à faire, et à montrer dans un petit graphe :

> Le circuit QAOA contient `O(p·N²)` portes **CX**, qui sont celles qui se trompent le plus.
> Avec `p = 3` et `N = 9`, on a `~108` portes CX. À `10⁻²` d'erreur chacune, la probabilité
> qu'**aucune** ne se trompe est `(1 − 0.01)¹⁰⁸ ≈ 34 %`.
>
> **Deux tiers des exécutions sont corrompues.** Et ça **empire quadratiquement avec N** :
> à `N = 30`, il y a ~1300 CX, et `(0.99)¹³⁰⁰ ≈ 2 × 10⁻⁶`. Autrement dit, **le circuit ne
> produit plus jamais un résultat non corrompu.**

> 💬 **La conclusion à énoncer :** *« Et voilà le vrai mur du calcul quantique aujourd'hui.
> Ce n'est pas le nombre de qubits — IBM en a plus de 1000. C'est leur QUALITÉ. Le circuit
> QAOA grandit en `O(p·N²)`, donc la fidélité s'effondre EXPONENTIELLEMENT avec `N²`.
> Tant qu'on n'a pas de correction d'erreur fonctionnelle, l'avantage asymptotique que
> montre ma courbe verte reste théorique. C'est exactement ce que mon graphe de bruit
> quantifie. »*

C'est la conclusion la plus mature que tu puisses livrer sur ce projet.

## 10.3 Animation de convergence QAOA

On enregistre `trace = [⟨H_C⟩ à chaque itération]` (déjà fait dans le code de §7.4)
et on l'anime côté frontend.

**Deux visualisations complémentaires :**

1. **Courbe d'énergie** `⟨H_C⟩` vs itération — on voit COBYLA descendre, avec ses
   plateaux et ses sauts (COBYLA construit un simplexe, il a des phases d'exploration).
   On trace l'énergie de l'optimum (connue par la brute force) en ligne horizontale :
   **on voit l'écart se refermer.**
2. **Histogramme des amplitudes** aux itérations `0`, `p/2`, `final` — on voit la
   distribution partir **plate** (superposition uniforme après les Hadamard) et se
   **concentrer** sur les bons états. **C'est l'interférence constructive rendue visible.**

> C'est le bonus qui fait le plus d'effet en présentation : le public *voit* la mécanique
> quantique faire son travail, au lieu de l'entendre décrite.

## 10.4 Mode « scaling demo »

Un slider `N` de 2 à 60 qui, en temps réel :

- recalcule et **anime** les quatre courbes de complexité,
- affiche un compteur « nombre de combinaisons » qui **s'emballe**,
- affiche un « temps estimé pour la brute force » qui passe de `ms` → `s` → `heures`
  → `années` → `âges de l'univers`,
- passe la carte en mode dégradé au-delà du plafond, avec le message explicatif.

> **C'est LE bonus pour ta présentation.** L'explosion combinatoire est un concept abstrait
> tant qu'on ne l'a pas **vue bouger**. Un compteur qui passe de `130` à `10¹⁸` pendant
> que tu déplaces un slider, ça marque durablement.

---

# 11. Questions/Réponses de soutenance

Le sujet liste **5 questions obligatoires** (§VII.8). Les voici, avec des réponses
complètes, plus les pièges probables.

## Les 5 questions du sujet

### Q1 — « Qu'est-ce qu'un QUBO, et pourquoi reformuler le problème ainsi ? »

> Un QUBO, c'est **Quadratic Unconstrained Binary Optimization** : minimiser une fonction
> de variables binaires, de **degré au plus 2**, et **sans aucune contrainte**.
>
> On reformule ainsi parce que c'est **la seule forme qu'un processeur quantique sait
> encoder nativement**. Un terme linéaire `xᵢ` devient un champ local sur le qubit `i`,
> une porte `RZ`. Un terme quadratique `xᵢxₖ` devient un couplage entre deux qubits,
> `CX·RZ·CX`. Un terme de degré 3 demanderait un couplage à trois corps, qui n'existe
> pas sur le matériel.
>
> Dans mon cas, ça m'a demandé **deux transformations**. D'abord **linéariser la couverture** :
> `𝟙[au moins une borne]` vaut exactement `1 − Π(1−xᵢ)`, que je tronque au degré 2 — ce qui
> est exact tant qu'au plus 2 bornes couvrent la même zone, et qui au-delà pénalise la
> redondance, un biais qui va dans le bon sens. Ensuite **absorber la contrainte de budget**
> dans une **pénalité** `P·(Σxᵢ − B)²`.

### Q2 — « Boucle classique vs circuit quantique dans QAOA : comment coopèrent-ils ? »

> Ce sont **deux rôles complètement distincts**.
>
> Le **circuit quantique** ne cherche rien. Il **prépare un état** `|ψ(γ,β)⟩`, une
> superposition pondérée des `2^N` solutions. Le layer de coût `e^{−iγH_C}` donne à chaque
> état une phase proportionnelle à son énergie ; le mixer `e^{−iβH_M}` les fait interférer.
> Si `(γ,β)` sont bons, l'interférence est **constructive** pour les bonnes solutions et
> **destructive** pour les mauvaises. Le circuit encode donc une **distribution de probabilité**.
>
> L'**optimiseur classique** — COBYLA chez moi — cherche justement ces bons `(γ,β)`. Il ne
> voit du quantique qu'**un seul nombre**, l'énergie moyenne `⟨H_C⟩`. C'est une optimisation
> continue en boîte noire de `2p` paramètres réels.
>
> **La coopération** : le classique propose des angles, le quantique renvoie une énergie,
> le classique ajuste. À la fin, on mesure le circuit optimisé et on garde le meilleur
> bitstring échantillonné.
>
> **En une phrase : le quantique ne résout pas le problème, il prépare une distribution ;
> c'est le classique qui optimise, mais il optimise les angles, pas la solution.**

### Q3 — « Pourquoi les deux solveurs peuvent-ils différer sur la même instance ? »

**Quatre raisons, à donner dans cet ordre :**

> **1. QAOA est approché par construction.** Le « A » de son nom. À `p` fini, il n'y a
> aucune garantie d'atteindre l'optimum. Seule la limite `p → ∞` la donne.
>
> **2. Il y a souvent plusieurs optima — c'est le cas le plus fréquent chez moi.** Plusieurs
> placements différents peuvent couvrir **exactement le même poids**. Quand ça arrive,
> QAOA et la brute force renvoient des **ensembles différents** avec la **même couverture**.
> Ce n'est pas un désaccord sur la qualité, c'est un choix arbitraire parmi des optima
> équivalents — la brute force garde le premier trouvé, QAOA garde le plus probable.
> **Mon interface distingue visuellement ces deux cas.**
>
> **3. La troncature au degré 2 déforme légèrement le paysage.** Quand 3 bornes ou plus
> couvrent la même zone, le QUBO sous-estime la couverture. QAOA optimise donc une
> fonction très proche mais pas identique au vrai objectif. Comme j'évalue toujours le
> résultat final avec la **vraie** fonction objectif, ça ne fausse pas mes chiffres —
> mais ça peut guider QAOA vers un autre optimum.
>
> **4. QAOA est probabiliste.** Deux exécutions avec des seeds différentes peuvent donner
> des résultats différents. J'ai fixé une seed pour que ma démonstration soit reproductible.

### Q4 — « Pourquoi le quantique est-il pertinent alors que la brute force est plus rapide ET meilleure ici ? »

> **Il ne l'est pas, ici. Et je ne prétends pas le contraire.**
>
> Sur mon instance, la brute force gagne **sur les deux tableaux** : elle est exacte —
> donc QAOA ne peut jamais faire mieux, seulement égaler — et elle est ~150× plus rapide.
>
> Deux raisons, toutes deux structurelles :
>
> **D'abord, je simule.** Simuler `N` qubits coûte `O(2^N)` en temps ET en mémoire, à
> **chaque** itération de la boucle. Je paie donc exactement le coût exponentiel que le
> quantique est censé éviter. Sur un vrai QPU, le circuit utilise `N` qubits et
> `O(p·N²)` portes — **polynomial**.
>
> **Ensuite, l'argument est asymptotique.** Il n'est pas sur une instance, il est sur la
> **croissance**. C'est ce que montre ma courbe de complexité : l'espace classique en `2^N`
> contre un circuit en `O(p·N²)`. Une exponentielle finit toujours par dépasser un polynôme.
>
> **À `N = 9`, cette croisée n'a pas encore eu lieu — et c'est exactement ce que mon
> projet démontre : où se situe l'argument, et non qu'il est déjà gagné.**

### Q5 — « Que signifie la courbe de complexité pour un déploiement réel ? »

*(Voir §9.3 pour la réponse complète et développée.)*

En condensé :

> Une vraie étude pour la Métropole de Lyon regarderait des **centaines** de candidats.
> À 200 candidats, `2²⁰⁰ ≈ 10⁶⁰` — plus que le nombre d'atomes de la Voie lactée.
> La force brute est **physiquement** impossible, pas juste lente.
> Les villes utilisent donc aujourd'hui des heuristiques et des solveurs MILP, sans
> garantie d'optimalité. Le pari quantique est d'offrir une **classe d'approximation
> différente**, fondée sur l'interférence. Ce n'est pas encore vrai — le hardware est trop
> bruité — mais c'est précisément sur ce type de problème que la question se joue.

---

## Les pièges probables

### P1 — « Ton `B` est fixé à 3, donc `C(N,3)` est polynomial. Où est l'explosion ? »

*(La réponse complète est en §4.3 — relis-la, c'est le piège le plus sérieux.)*

> **Objection juste, et j'ai prévu trois réponses.**
> ① Dans la réalité `B` croît avec `N` — une ville avec 100 candidats en construit 30, pas 3.
> À `B = N/2`, `C(N,N/2) ≈ 2^N/√N`, c'est bien exponentiel.
> ② Même à `B` fixé, `C(N,B) ~ N^B/B!` est polynomial **de degré B**. `C(100,20) ≈ 5×10²⁰`.
> « Polynomial » ne veut pas dire « faisable ».
> ③ Surtout : **QAOA explore l'espace complet `2^N`**, puisque le QUBO ne contraint pas
> structurellement le budget, il le pénalise. Comparer QAOA à `2^N` est donc la comparaison
> honnête.
> **Et c'est pour ça que je trace les deux courbes dans mon interface.**

### P2 — « Ta troncature au degré 2 est fausse. Ton QUBO ne représente pas le problème. »

*(Ne récite pas. Montre l'indicateur « fidélité du QUBO » à l'écran, puis dis ceci.)*

> **Sur l'instance de référence, elle n'est pas approchée : elle est exacte. Et je le mesure.**
>
> La troncature est exacte tant qu'au plus 2 bornes couvrent la même zone. Or je peux
> borner ça sans rien énumérer : `s_max = maxⱼ min(|Cⱼ|, B)`, calculable en `O(M)`.
> Sur Lyon à 300 m, `s_max = 2` — **aucune zone de la Presqu'île n'est à portée de trois
> candidats à la fois**. J'ai vérifié sur les 130 états faisables : l'écart entre l'énergie
> du QUBO et la vraie couverture est **exactement nul**.
>
> **C'est ce que montre l'indicateur vert, ici.** Si je monte le rayon à 400 m —
> *(le faire)* — il passe en orange et me dit combien de zones entrent dans le régime approché.
>
> Et même dans ce régime, ça reste sain : ① le biais **pénalise la redondance**, ce qui va
> dans le sens du vrai objectif ; ② **je n'utilise jamais l'énergie du QUBO pour noter** —
> le score affiché passe toujours par ma fonction objectif exacte, donc mes métriques ne
> peuvent pas contredire ma carte.
>
> L'alternative exacte existe — une variable auxiliaire `yⱼ` par zone — mais elle coûte
> `N + M` qubits, soit une centaine chez moi. `2¹⁰⁰` amplitudes, c'est plus d'atomes que
> la Voie lactée n'en contient. **Ce n'est pas un choix de confort, c'est une impossibilité.**

### P3 — « Montre-moi ce qui se passe si je change le poids de pénalité. »

> *(Tu ne réponds pas. Tu décoches « auto » et tu manipules le slider en direct.)*
> **Trop petit** → regardez, QAOA renvoie 6 bornes pour un budget de 3. Infaisable, et mon
> interface le signale.
> **Trop grand** → le budget est respecté, mais la couverture tombe de 84 % à 52 %. Parce que
> le terme de pénalité écrase numériquement le signal de couverture : toutes les solutions
> faisables ont une pénalité nulle, donc leurs énergies ne diffèrent que de ~100 sur une
> échelle de 10⁶. Le paysage devient plat, COBYLA n'a plus de gradient exploitable.
> **Le bon `P` est juste au-dessus de `max Wᵢ`**, le gain marginal maximal d'une borne
> supplémentaire — c'est ce que calcule mon mode auto.

### P4 — « Pourquoi COBYLA et pas un optimiseur à gradient ? »

> Parce que je n'ai **pas** accès au gradient analytiquement. Chaque évaluation de `F(γ,β)`
> demande d'exécuter un circuit — c'est une **boîte noire**. Un gradient par différences
> finies coûterait `2p` évaluations de circuit par pas, ce qui est prohibitif.
>
> **COBYLA** est *derivative-free* : il construit une approximation linéaire locale dans
> un simplexe. Il est robuste au bruit d'échantillonnage, ce qui compte sur hardware réel.
>
> **Et je l'ai mesuré** : face à Powell, Nelder-Mead et SLSQP sur mon instance, COBYLA
> atteint la meilleure probabilité sur l'optimum (5,6 %) avec **4,5× moins d'évaluations**.
> C'est la bonne métrique : sur un vrai QPU, chaque évaluation est un envoi de circuit qui
> coûte des secondes, donc le nombre d'appels prime sur le temps CPU de l'optimiseur.
>
> ⚠️ Attention au piège d'échelle, par contre : `rhobeg`, le rayon initial du simplexe de
> COBYLA, vaut 1 par défaut, alors que γ vit sur une échelle ~0,02. Sans normalisation de γ,
> COBYLA saute par-dessus toute la structure du paysage. C'est le bug que j'ai dû corriger
> — voir §7.5.
>
> Les alternatives sérieuses : **SPSA** (deux évaluations par pas seulement, très utilisé
> sur hardware bruité) ou la **règle de décalage de paramètres** (*parameter-shift rule*),
> qui donne le gradient **exact** en `2` évaluations par paramètre — mais qui reste coûteuse.

### P5 — « Pourquoi `p = 3` ? »

> C'est un compromis mesuré. À `p = 1`, le circuit n'est pas assez expressif et la qualité
> est médiocre. À `p ≥ 6`, il y a 12 paramètres à optimiser — COBYLA converge mal en
> dimension élevée — et le temps de simulation explose. À `p = 3` j'atteins l'optimum sur
> mon instance de référence dans la grande majorité des essais.
> **Théoriquement, `p → ∞` redonne l'évolution adiabatique et donc l'optimum exact.**
> C'est le « Approximate » du nom qui vient de `p` fini.

### P6 — « Tu prends le meilleur bitstring mesuré. C'est pas de la triche ? »

> Non, c'est le **protocole QAOA canonique**. La sortie de QAOA **est** une distribution de
> probabilité, pas un bitstring unique. On l'échantillonne et on garde le meilleur tirage.
> C'est la définition de l'algorithme dans le papier de Farhi.
>
> Ce qui **serait** de la triche, ce serait de m'appuyer sur la brute force pour choisir.
> Je ne le fais pas : je n'utilise que les bitstrings **effectivement mesurés**, je les
> évalue avec la vraie fonction objectif, et j'écarte les infaisables. Et le **nombre de
> shots fait partie du coût que je reporte**.

### P7 — « Pourquoi Qiskit et pas ton propre simulateur ? »

> Le sujet l'autorise explicitement : *« Using a quantum framework to assemble and simulate
> the circuit is of course expected and allowed. »* Ce que je devais écrire moi-même —
> le solveur brute force, la construction du QUBO, la transformation en Ising, le circuit
> QAOA porte par porte, la boucle variationnelle — **je l'ai écrit moi-même**. Qiskit ne fait
> qu'appliquer les matrices unitaires au vecteur d'état et gérer le modèle de bruit.
> **Je n'appelle aucune fonction qui résout le problème à ma place**, ni `QAOAAnsatz`,
> ni `MinimumEigenOptimizer`, ni `QuadraticProgram`.

### P8 — « Que se passe-t-il si je mets le rayon à 5000 m ? »

> Tous les candidats couvrent toutes les zones. Chaque `Cⱼ` contient tous les candidats,
> donc **n'importe quelle** solution non vide couvre 100 % — **tous les placements
> deviennent équivalents**. La brute force renvoie le premier trouvé, QAOA renvoie
> n'importe lequel. C'est un cas **dégénéré**, et c'est le comportement correct : le
> problème n'a plus de structure à exploiter.
>
> À l'inverse, à 10 m, plus rien ne se recouvre : chaque borne couvre son propre voisinage
> et rien d'autre. Le problème devient **séparable** — il suffit de prendre les `B`
> meilleurs candidats indépendamment. Là aussi, plus de structure.
>
> **Le problème n'est intéressant qu'entre les deux**, quand les couvertures se recoupent
> partiellement. C'est pourquoi 300 m est le bon ordre de grandeur sur la Presqu'île.

---

# 12. Glossaire

Les mots exacts à employer devant le jury.

| Terme                                              | Définition courte                                                                                         |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Maximum Coverage**                         | choisir ≤ B ensembles pour maximiser le poids des éléments couverts. NP-difficile.                      |
| **NP-difficile**                             | au moins aussi dur que n'importe quel problème de NP. Pas d'algorithme exact polynomial connu.            |
| **QUBO**                                     | Quadratic Unconstrained Binary Optimization.`min xᵀQx` sur `x ∈ {0,1}^N`.                            |
| **Pénalité**                               | terme d'énergie qui rend coûteuse la violation d'une contrainte, permettant de l'éliminer formellement. |
| **Ising**                                    | modèle de spins`zᵢ ∈ {−1,+1}` avec champs `hᵢ` et couplages `Jᵢₖ`. Équivalent au QUBO.       |
| **Hamiltonien**                              | opérateur dont les valeurs propres sont les énergies du système. Ici,`H_C` diagonal.                  |
| **État fondamental**                        | l'état propre d'énergie minimale. Pour nous : la solution optimale du QUBO.                              |
| **Gap spectral**                             | écart d'énergie entre fondamental et premier excité. Petit gap ⇒ adiabatique lent.                     |
| **QAOA**                                     | Quantum Approximate Optimization Algorithm. Farhi, Goldstone, Gutmann (2014).                              |
| **Ansatz**                                   | la forme paramétrée du circuit. Ici :`p` alternances cost/mixer.                                       |
| **Mixer**                                    | `H_M = ΣXᵢ`. Son rôle est de faire interférer les états entre eux.                                  |
| **Couche / layer `p`**                     | une répétition du couple (cost, mixer). Plus de`p` = plus expressif, plus cher.                        |
| **Variationnel / hybride**                   | un circuit paramétré dont les paramètres sont optimisés par un algorithme classique.                   |
| **COBYLA**                                   | Constrained Optimization BY Linear Approximation. Optimiseur sans dérivée.                               |
| **Shots**                                    | nombre de répétitions de la mesure pour estimer une distribution.                                        |
| **Statevector**                              | le vecteur des`2^N` amplitudes complexes. Ce qu'un simulateur exact manipule.                            |
| **Théorème adiabatique**                   | un système reste dans son fondamental si l'Hamiltonien évolue assez lentement.                           |
| **Interférence constructive / destructive** | amplitudes qui s'additionnent / s'annulent. Le moteur de tout l'avantage quantique.                        |
| **Décohérence**                            | perte de l'information quantique par interaction avec l'environnement.`T1`, `T2`.                      |
| **Bruit dépolarisant**                      | modèle d'erreur : avec probabilité`p`, l'état est remplacé par l'état maximalement mixte.           |
| **Recuit simulé**                           | heuristique classique acceptant des dégradations avec probabilité`exp(−ΔE/T)`.                       |
| **Effet tunnel**                             | traversée quantique d'une barrière de potentiel, sans passer par-dessus.                                 |
| **Haversine**                                | formule de distance orthodromique sur une sphère.                                                         |
| **Ray casting**                              | test point-dans-polygone par comptage d'intersections d'un rayon.                                          |

---

# 📌 La fiche mémo — à relire 10 minutes avant la soutenance

```
LE PROBLÈME
  max Σⱼ wⱼ·𝟙[Σᵢ∈Cⱼ xᵢ ≥ 1]   s.c.  Σᵢ xᵢ ≤ B        NP-difficile

LE QUBO      (2 transformations)
  ① couverture → 1 − Π(1−xᵢ), tronqué au degré 2
     exact jusqu'à s=2 ; au-delà sous-estime → PÉNALISE LA REDONDANCE (biais favorable)
  ② budget ≤ B → = B  (car f est MONOTONE : un optimum sature toujours le budget)
                → pénalité P·(Σxᵢ − B)²         ZÉRO qubit auxiliaire

  Qᵢᵢ = −Wᵢ + P(1−2B)        Qᵢₖ = +Wᵢₖ + 2P
  P > max Wᵢ    trop petit → INFAISABLE    trop grand → PAYSAGE PLAT

L'ISING
  xᵢ = (1−zᵢ)/2  →  H_C = Σhᵢ Zᵢ + ΣJᵢₖ ZᵢZₖ       H_C est DIAGONAL
  H_C|x⟩ = E(x)|x⟩   →  état fondamental = solution du QUBO

QAOA
  |ψ⟩ = Π_l e^{−iβ_l H_M} e^{−iγ_l H_C} |+⟩^N      H_M = ΣXᵢ
  quantique = prépare une distribution     classique = optimise les angles (γ,β)
  coût en portes : O(p·N²)  ← POLYNOMIAL, c'est TOUT l'argument
  p=3, COBYLA, 4096 shots, seed fixée

L'HONNÊTETÉ — le point le plus important
  brute force EXACTE  →  QAOA ne peut jamais faire mieux
  je SIMULE  →  O(2^N) par itération  →  QAOA est ~150× plus lent
  → c'est ATTENDU, ce n'est PAS un échec
  l'avantage est ASYMPTOTIQUE, il est dans la COURBE

LA COURBE (échelle log, axe Y = TRAVAIL, pas mémoire)
  2^N (espace complet) ─── Σₖ≤B C(N,k) (brute force réelle)
  O(p·N²) (QPU réel)   ─── iters·2^N·portes (ma simulation, la PIRE)

LE PLAFOND
  N > 16 → skip gracieux + message.  C'est le plafond du SIMULATEUR, pas de l'ALGORITHME.

L'INSTANCE DE RÉFÉRENCE
  Lyon Presqu'île · N=9 · B=3 · r=300 m · poids uniformes · 130 combinaisons
```

---

*Dernière chose : le sujet répète trois fois qu'une application qu'on ne sait pas expliquer
ne vaut rien. Ce document est là pour que ça ne t'arrive pas. Relis-le.*
