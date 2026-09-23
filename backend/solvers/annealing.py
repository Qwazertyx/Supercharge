"""
[BONUS] Solveur classique approché — recuit simulé.

POURQUOI CE SOLVEUR EST LE PLUS INTÉRESSANT DES TROIS

La force brute compare « exact vs approché ». C'est utile, mais ce n'est pas
la comparaison la plus juste pour QAOA : elle oppose deux choses de nature
différente.

Le recuit simulé, lui, compare « approché CLASSIQUE vs approché QUANTIQUE »,
sur LE MÊME QUBO, dans LE MÊME paysage énergétique. La seule différence est
la façon de le parcourir :

  ┌────────────────────┬──────────────────────┬─────────────────────────────┐
  │                    │  Recuit simulé       │  QAOA                       │
  ├────────────────────┼──────────────────────┼─────────────────────────────┤
  │ Évasion des minima │ fluctuation THERMIQUE│ effet TUNNEL quantique      │
  │ locaux             │ on saute PAR-DESSUS  │ on TRAVERSE la barrière     │
  │ Contrôle           │ température T ↘      │ angles (γ,β) optimisés      │
  │ Ce qui explore     │ UN point à la fois   │ une SUPERPOSITION de tous   │
  │ Nature             │ stochastique         │ unitaire + mesure           │
  └────────────────────┴──────────────────────┴─────────────────────────────┘

C'est l'analogue thermique exact de ce que QAOA fait quantiquement — d'où le
nom de « recuit quantique » donné à la version adiabatique continue.

Voir explanation.md §10.1.

Le recuit simulé est aussi la brique de base de ce que les villes utilisent
RÉELLEMENT aujourd'hui pour ce genre de problème, quand la force brute est
hors de portée. C'est donc le baseline honnête du monde réel.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..objective import evaluate
from ..qubo import build_qubo

DEFAULT_SWEEPS = 400
DEFAULT_RESTARTS = 8
DEFAULT_T_START_RATIO = 0.35   # T initiale, en fraction de l'échelle d'énergie
DEFAULT_T_END_RATIO = 0.002
DEFAULT_SEED = 42


@dataclass
class AnnealingResult:
    selection: list[int] = field(default_factory=list)
    covered_weight: float = 0.0
    coverage_ratio: float = 0.0
    covered_zones: list[int] = field(default_factory=list)
    uncovered_zones: list[int] = field(default_factory=list)
    stations_used: int = 0
    feasible: bool = True

    iterations: int = 0        # nb total de propositions évaluées
    restarts: int = 0
    accepted: int = 0
    uphill_accepted: int = 0   # mouvements DÉGRADANTS acceptés — le cœur du recuit
    penalty: float = 0.0
    final_energy: float = 0.0
    energy_trace: list[float] = field(default_factory=list)
    elapsed_ms: float = 0.0


def solve(
    instance,
    sweeps: int = DEFAULT_SWEEPS,
    restarts: int = DEFAULT_RESTARTS,
    penalty: float | None = None,
    seed: int = DEFAULT_SEED,
    record_trace: bool = False,
) -> AnnealingResult:
    """Recuit simulé sur le MÊME QUBO que celui donné à QAOA.

    C'est volontaire : les deux solveurs approchés voient rigoureusement le
    même paysage énergétique. Toute différence de résultat vient donc de la
    façon de l'explorer, et de rien d'autre.

    Le mouvement élémentaire est un « flip » : on bascule un candidat. La
    pénalité du QUBO se charge de ramener la solution vers |S| = B — on n'a
    pas besoin d'un voisinage qui préserve la cardinalité, et c'est plus
    fidèle à ce que QAOA fait (le mixer bascule aussi un qubit à la fois).
    """
    start = time.perf_counter()
    n = instance.n_candidates

    if n == 0:
        return AnnealingResult()

    qubo = build_qubo(instance, penalty=penalty)
    Q = qubo.Q
    # Matrice symétrisée : delta_energy a besoin de la somme ligne+colonne.
    upper = np.triu(Q, 1)
    sym = upper + upper.T
    diag = np.diag(Q).copy()

    rng = np.random.default_rng(seed)

    # Échelle d'énergie, pour calibrer la température de départ. Une
    # température trop basse gèle immédiatement (recuit = glouton) ; trop
    # haute, on fait une marche aléatoire pure pendant la moitié du budget.
    energy_scale = float(np.abs(diag).max() + np.abs(sym).sum(axis=1).max()) or 1.0
    t_start = DEFAULT_T_START_RATIO * energy_scale
    t_end = DEFAULT_T_END_RATIO * energy_scale
    cooling = (t_end / t_start) ** (1.0 / max(1, sweeps - 1))

    trace: list[float] = []
    best_x, best_energy = None, np.inf
    n_iter = n_accepted = n_uphill = 0

    for _ in range(max(1, restarts)):
        # Départ aléatoire faisable : B candidats tirés au hasard.
        x = np.zeros(n, dtype=np.int8)
        if instance.budget > 0:
            x[rng.choice(n, size=min(instance.budget, n), replace=False)] = 1

        energy = float(diag @ x + x @ upper @ x + qubo.offset)
        temperature = t_start

        for _sweep in range(sweeps):
            # Un « sweep » = n propositions, soit une chance de toucher
            # chaque variable. C'est l'unité standard en recuit.
            for _ in range(n):
                i = int(rng.integers(n))

                # ΔE d'un flip de la variable i, en O(1) :
                #   xᵢ: 0→1  ⇒  ΔE = +Qᵢᵢ + Σ_{k≠i} Q̃ᵢₖ·xₖ
                #   xᵢ: 1→0  ⇒  ΔE = −(idem)
                local = diag[i] + float(sym[i] @ x)
                delta = -local if x[i] else local

                n_iter += 1
                # ── LE CŒUR DU RECUIT ────────────────────────────────────
                # delta < 0 : c'est mieux, on accepte toujours.
                # delta > 0 : c'est PIRE, et on accepte quand même avec
                #             probabilité exp(−ΔE/T). C'est ce qui permet de
                #             remonter une colline pour découvrir un creux
                #             plus profond derrière — un glouton pur resterait
                #             bloqué dans le premier minimum local venu.
                #             Quand T → 0, exp(−ΔE/T) → 0 : on redevient
                #             glouton et la solution se fige.
                if delta <= 0.0 or rng.random() < np.exp(-delta / max(temperature, 1e-12)):
                    x[i] ^= 1
                    energy += delta
                    n_accepted += 1
                    if delta > 0.0:
                        n_uphill += 1

                    if energy < best_energy:
                        best_energy, best_x = energy, x.copy()

            if record_trace:
                trace.append(energy)
            temperature *= cooling

    selection = [i for i in range(n) if best_x is not None and best_x[i]]

    # Si la pénalité a laissé passer une solution trop grosse, on la ramène
    # dans le budget en gardant les B meilleures contributions marginales.
    # C'est honnête : on le fait avec la VRAIE fonction objectif, et on
    # compte ce travail comme du travail classique.
    if len(selection) > instance.budget:
        selection = _trim_to_budget(selection, instance)

    ev = evaluate(selection, instance)
    return AnnealingResult(
        selection=ev.selection,
        covered_weight=ev.covered_weight,
        coverage_ratio=ev.coverage_ratio,
        covered_zones=ev.covered_zones,
        uncovered_zones=ev.uncovered_zones,
        stations_used=ev.stations_used,
        feasible=ev.feasible,
        iterations=n_iter,
        restarts=max(1, restarts),
        accepted=n_accepted,
        uphill_accepted=n_uphill,
        penalty=qubo.penalty,
        final_energy=float(best_energy),
        energy_trace=trace,
        elapsed_ms=(time.perf_counter() - start) * 1000.0,
    )


def _trim_to_budget(selection: list[int], instance) -> list[int]:
    """Réduit une sélection à B éléments, gloutonnement, objectif réel."""
    kept: list[int] = []
    remaining = list(selection)
    while len(kept) < instance.budget and remaining:
        best_i, best_gain = None, -1.0
        for i in remaining:
            gain = evaluate(kept + [i], instance).covered_weight
            if gain > best_gain:
                best_gain, best_i = gain, i
        kept.append(best_i)
        remaining.remove(best_i)
    return sorted(kept)
