"""
LA fonction objectif. Exacte. Unique source de vérité du projet.

═══════════════════════════════════════════════════════════════════════════
  RÈGLE D'OR — à ne jamais enfreindre
  ─────────────────────────────────────────────────────────────────────────
  Le QUBO (qubo.py) sert UNIQUEMENT à guider le circuit quantique.
  Il est approché : il tronque la couverture au degré 2 et absorbe la
  contrainte de budget dans une pénalité.

  Tout chiffre AFFICHÉ — couverture, pourcentage, zones non couvertes —
  passe obligatoirement par ce module. Les trois solveurs (force brute,
  QAOA, recuit simulé) appellent `evaluate()` sur leur résultat final.

  C'est ce qui rend structurellement impossible qu'une métrique contredise
  la carte, exigence explicite du sujet (§VII.6).
═══════════════════════════════════════════════════════════════════════════

Voir explanation.md §5.3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Evaluation:
    """Le résultat exact d'un placement, tel qu'il sera affiché."""

    selection: list[int]        # les candidats retenus, triés
    covered_weight: float       # Σⱼ wⱼ sur les zones couvertes
    covered_zones: list[int]    # les identifiants des zones couvertes
    uncovered_zones: list[int]  # les identifiants des zones NON couvertes
    coverage_ratio: float       # covered_weight / total_weight, dans [0, 1]
    stations_used: int          # |selection|
    feasible: bool              # stations_used <= budget ?


def evaluate(selection, instance) -> Evaluation:
    """Évalue un placement avec la VRAIE fonction objectif.

        f(x) = Σⱼ wⱼ · 𝟙[ Σᵢ∈Cⱼ xᵢ ≥ 1 ]

    Aucune approximation. Une zone couverte par trois bornes rapporte
    exactement wⱼ, pas 3·wⱼ — c'est cette non-linéarité qui fait toute la
    difficulté du problème, et c'est ici qu'elle est traitée honnêtement.

    `selection` peut être n'importe quel itérable d'indices de candidats.
    """
    sel = sorted(set(selection))
    mask = 0
    for i in sel:
        mask |= 1 << i

    covered, uncovered = [], []
    covered_weight = 0.0
    for j, zone_mask in enumerate(instance.zone_masks):
        if mask & zone_mask:
            covered.append(j)
            covered_weight += instance.weights[j]
        else:
            uncovered.append(j)

    total = instance.total_weight
    return Evaluation(
        selection=sel,
        covered_weight=covered_weight,
        covered_zones=covered,
        uncovered_zones=uncovered,
        coverage_ratio=(covered_weight / total) if total > 0 else 0.0,
        stations_used=len(sel),
        feasible=len(sel) <= instance.budget,
    )


def evaluate_mask(mask: int, instance) -> tuple[float, int]:
    """Version rapide pour les boucles chaudes : ne renvoie que le poids.

    Utilisée par la force brute, qui appelle cette fonction une fois par
    combinaison. On évite donc d'allouer des listes des centaines de milliers
    de fois. Le résultat est identique à `evaluate(...).covered_weight`.
    """
    total = 0.0
    count = 0
    for j, zone_mask in enumerate(instance.zone_masks):
        if mask & zone_mask:
            total += instance.weights[j]
            count += 1
    return total, count
