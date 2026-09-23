"""
La courbe de croissance de la complexité.

Le sujet : « The complexity growth curve is the single most important visual
of the project. »

⚠️ L'axe Y est le TRAVAIL COMPUTATIONNEL (nombre d'opérations, proportionnel
au temps d'exécution). Ce n'est PAS de la mémoire — la force brute parcourt
l'espace de recherche une combinaison à la fois, son empreinte mémoire reste
minuscule. Le sujet insiste sur ce point ; ne pas le confondre en soutenance.

ON TRACE QUATRE COURBES, PAS DEUX. C'est ce qui fait la différence entre un
projet correct et un projet solide :

  ① 2^N — l'espace de recherche complet.
     C'est l'argument principal, et c'est aussi l'espace que QAOA explore
     réellement : le QUBO ne contraint pas le budget structurellement, il le
     PÉNALISE, donc le circuit met les N qubits en superposition et parcourt
     bien les 2^N états.

  ② Σₖ≤B C(N,k) — ce que la force brute énumère VRAIMENT avec le B courant.
     C'est l'honnêteté du projet. À B fixé cette courbe est polynomiale de
     degré B, pas exponentielle, et un jury attentif le remarquera. Mieux
     vaut la tracer soi-même que se la faire opposer. Le bouton
     « B = N/2 » montre le régime réaliste, où elle redevient exponentielle.

  ③ p·(2N + 3·N(N−1)/2) — le coût en portes du circuit QAOA sur un VRAI QPU.
     POLYNOMIAL, en O(p·N²). C'est la courbe qui porte tout l'argument.

  ④ iterations · 2^N · portes — le coût de MA simulation sur CPU.
     Exponentielle, et la PIRE des quatre. La tracer, c'est admettre
     visuellement pourquoi QAOA est plus lent sur ma machine, sans rien
     cacher. C'est la leçon du projet.

Voir explanation.md §9.
"""

from __future__ import annotations

from math import comb


def brute_force_work(n: int, budget: int) -> float:
    """Nombre de combinaisons réellement énumérées : Σ_{k=0}^{B} C(n,k)."""
    b = max(0, min(budget, n))
    return float(sum(comb(n, k) for k in range(b + 1)))


def search_space(n: int) -> float:
    """2^N — l'espace de recherche complet, celui que QAOA explore."""
    return float(2 ** n)


def qaoa_circuit_gates(n: int, layers: int) -> float:
    """Portes du circuit QAOA sur un vrai QPU.

        N Hadamard
      + p · [ N rotations RZ de champ
            + 3 · N(N−1)/2 portes pour les couplages (CX·RZ·CX)
            + N rotations RX du mixer ]

    Soit O(p·N²). Le graphe de couplage est COMPLET parce que la pénalité
    de budget P(Σxᵢ−B)² crée un terme xᵢxₖ pour CHAQUE paire — même entre
    deux candidats géographiquement sans rapport. C'est le prix à payer
    pour encoder la contrainte, et c'est une remarque appréciée en soutenance.
    """
    couplings = n * (n - 1) / 2
    return float(n + layers * (2 * n + 3 * couplings))


def qaoa_simulation_work(n: int, layers: int, maxiter: int) -> float:
    """Coût de la simulation du circuit sur un CPU classique.

    À chaque évaluation de la fonction de coût, il faut faire évoluer 2^N
    amplitudes complexes à travers toutes les couches. Et l'optimiseur
    appelle cette fonction `maxiter` fois.

        maxiter · 2^N · (travail par couche)

    C'est EXPONENTIEL. On paie exactement le coût que le quantique est censé
    éviter — parce que simuler un système quantique sur une machine classique
    est intrinsèquement exponentiel. C'est précisément pourquoi on veut
    construire de vraies machines quantiques.
    """
    per_eval = (2 ** n) * layers * n
    return float(maxiter * per_eval)


def build_curves(
    n_max: int = 60,
    budget: int = 3,
    layers: int = 3,
    maxiter: int = 150,
    budget_scales_with_n: bool = False,
) -> dict:
    """Échantillonne les quatre courbes de N = 2 à n_max.

    `budget_scales_with_n` — le commutateur le plus intéressant de l'interface.
    À B fixé, la force brute est polynomiale de degré B. Mais une ville qui
    étudie 100 emplacements n'en construit pas 3 : elle en construit 30 ou 50.
    Avec B = N/2, C(N, N/2) ≈ 2^N/√(πN/2) — l'explosion redevient bien réelle.
    """
    ns = list(range(2, n_max + 1))
    rows = []
    for n in ns:
        b = max(1, n // 2) if budget_scales_with_n else budget
        rows.append({
            "n": n,
            "budget": min(b, n),
            "search_space": search_space(n),
            "brute_force": brute_force_work(n, b),
            "qaoa_circuit": qaoa_circuit_gates(n, layers),
            "qaoa_simulation": qaoa_simulation_work(n, layers, maxiter),
        })

    return {
        "points": rows,
        "series": [
            {
                "key": "search_space",
                "label": "Espace de recherche complet — 2^N",
                "nature": "exponentielle",
                "note": "L'espace que QAOA explore réellement : le QUBO pénalise "
                        "le budget au lieu de le contraindre.",
            },
            {
                "key": "brute_force",
                "label": "Force brute réelle — Σₖ≤B C(N,k)",
                "nature": "polynomiale de degré B" if not budget_scales_with_n
                          else "exponentielle (B = N/2)",
                "note": "Ce que mon solveur énumère vraiment. À B fixé, c'est "
                        "polynomial — je le montre au lieu de le cacher.",
            },
            {
                "key": "qaoa_circuit",
                "label": "Circuit QAOA sur un vrai QPU — O(p·N²)",
                "nature": "polynomiale",
                "note": "LA courbe qui porte l'argument du projet.",
            },
            {
                "key": "qaoa_simulation",
                "label": "Ma simulation QAOA sur CPU — iters · 2^N · p·N",
                "nature": "exponentielle",
                "note": "La pire des quatre. C'est pourquoi QAOA est plus lent "
                        "sur ma machine : je paie le coût que le quantique évite.",
            },
        ],
        "params": {
            "n_max": n_max,
            "budget": budget,
            "layers": layers,
            "maxiter": maxiter,
            "budget_scales_with_n": budget_scales_with_n,
        },
    }


def humanize_duration(operations: float, ops_per_second: float = 1e9) -> str:
    """Traduit un nombre d'opérations en durée lisible.

    Sert au mode « scaling demo » : voir un compteur passer de « 12 ms » à
    « 38 millions d'années » pendant qu'on déplace un curseur rend
    l'explosion combinatoire viscérale, là où un nombre reste abstrait.

    1 GHz d'évaluations est une hypothèse GÉNÉREUSE pour la force brute —
    chaque combinaison demande en réalité plusieurs dizaines d'opérations.
    Être généreux avec l'adversaire rend l'argument plus fort, pas plus faible.
    """
    seconds = operations / ops_per_second
    if seconds < 1e-3:
        return f"{seconds * 1e6:.0f} µs"
    if seconds < 1.0:
        return f"{seconds * 1e3:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    if seconds < 86_400:
        return f"{seconds / 3600:.1f} h"
    if seconds < 31_557_600:
        return f"{seconds / 86_400:.1f} jours"

    years = seconds / 31_557_600
    if years < 1e3:
        return f"{years:.0f} ans"
    if years < 1e6:
        return f"{years / 1e3:.1f} milliers d'années"
    if years < 1e9:
        return f"{years / 1e6:.1f} millions d'années"
    if years < 13.8e9:
        return f"{years / 1e9:.1f} milliards d'années"
    return f"{years / 13.8e9:.3g} × l'âge de l'univers"
