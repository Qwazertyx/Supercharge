"""
Solveur classique — force brute exhaustive.

C'est la GROUND TRUTH du projet. Il énumère littéralement toutes les
combinaisons faisables, donc ce qu'il renvoie EST l'optimum global. Pas
« probablement », pas « approximativement ». Est.

C'est contre lui qu'on juge QAOA. Si la force brute est fausse, rien de ce
qui est construit au-dessus n'a de valeur (sujet §VII.3).

Voir explanation.md §3.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from itertools import combinations
from math import comb

from ..objective import evaluate


@dataclass
class BruteForceResult:
    selection: list[int]
    covered_weight: float
    coverage_ratio: float
    covered_zones: list[int]
    uncovered_zones: list[int]
    stations_used: int
    combinations_evaluated: int
    optimal_ties: int          # nb de placements distincts atteignant l'optimum
    elapsed_ms: float


def count_combinations(n: int, budget: int) -> int:
    """Nombre de sous-ensembles de taille ≤ budget parmi n candidats.

        Σ_{k=0}^{B} C(n, k)

    C'est le chiffre que le sujet exige d'afficher. Sur l'instance de
    référence (n = 9, B = 3) : 1 + 9 + 36 + 84 = 130.
    """
    budget = max(0, min(budget, n))
    return sum(comb(n, k) for k in range(budget + 1))


def solve(instance) -> BruteForceResult:
    """Énumère, évalue, garde le meilleur.

    L'évaluation utilise des masques de bits : tester si une zone est couverte
    est un ET binaire, une seule instruction machine. C'est ce qui permet à ce
    solveur d'être honnêtement rapide et de rendre la comparaison de temps
    significative — on ne veut pas gagner la course en handicapant l'adversaire.
    """
    start = time.perf_counter()

    n = instance.n_candidates
    budget = instance.budget
    zone_masks = instance.zone_masks
    weights = instance.weights

    best_mask = 0
    best_weight = -1.0
    ties = 0
    evaluated = 0

    for k in range(budget + 1):
        for combo in combinations(range(n), k):
            mask = 0
            for i in combo:
                mask |= 1 << i

            total = 0.0
            for j, zm in enumerate(zone_masks):
                if mask & zm:
                    total += weights[j]

            evaluated += 1

            if total > best_weight + 1e-12:
                best_weight = total
                best_mask = mask
                ties = 1
            elif abs(total - best_weight) <= 1e-12:
                ties += 1

    elapsed_ms = (time.perf_counter() - start) * 1000.0

    # On repasse par la fonction objectif officielle pour produire les chiffres
    # affichés. Le calcul ci-dessus est une boucle chaude optimisée ; celui-ci
    # est la source de vérité. Les deux doivent coïncider — c'est testé.
    selection = [i for i in range(n) if best_mask >> i & 1]
    ev = evaluate(selection, instance)

    return BruteForceResult(
        selection=ev.selection,
        covered_weight=ev.covered_weight,
        coverage_ratio=ev.coverage_ratio,
        covered_zones=ev.covered_zones,
        uncovered_zones=ev.uncovered_zones,
        stations_used=ev.stations_used,
        combinations_evaluated=evaluated,
        optimal_ties=ties,
        elapsed_ms=elapsed_ms,
    )
