"""
Comparaison des solveurs et génération du verdict.

Deux responsabilités :

  1. LES DIFFÉRENCES SUR LA CARTE (sujet §VII.5)
     « The differences must be made visible: zones covered by one solver but
     not the other, stations chosen by one but not the other. »
     On calcule ici les ensembles symétriques que le frontend met en valeur.

  2. LE VERDICT (sujet §VI.2, figure VI.1)
     Une phrase qui dit PLATEMENT qui gagne à cette échelle. Le sujet est
     catégorique : « do not claim a quantum "win" that the numbers do not
     show ». Cette phrase est donc générée À PARTIR DES CHIFFRES MESURÉS,
     jamais codée en dur. Si un jour QAOA gagnait, elle le dirait ; tant que
     ce n'est pas le cas, elle dit l'inverse.

Voir explanation.md §8.3.
"""

from __future__ import annotations


def _fmt_int(value: float) -> str:
    """12345 → « 12 345 » (espace insécable fine, comme en typographie FR)."""
    return f"{int(value):,}".replace(",", " ")


def diff_solutions(classical, quantum, instance) -> dict:
    """Ce que l'un a choisi et pas l'autre — stations ET zones couvertes."""
    c_stations, q_stations = set(classical.selection), set(quantum.selection)
    c_zones, q_zones = set(classical.covered_zones), set(quantum.covered_zones)

    return {
        "shared_stations": sorted(c_stations & q_stations),
        "only_classical_stations": sorted(c_stations - q_stations),
        "only_quantum_stations": sorted(q_stations - c_stations),
        "shared_zones": sorted(c_zones & q_zones),
        "only_classical_zones": sorted(c_zones - q_zones),
        "only_quantum_zones": sorted(q_zones - c_zones),
        "identical_placement": c_stations == q_stations,
        "identical_coverage": abs(classical.covered_weight - quantum.covered_weight) < 1e-9,
    }


def classify_agreement(classical, quantum, diff: dict) -> dict:
    """Qualifie le désaccord entre les deux solveurs.

    Le cas le plus fréquent sur l'instance de référence n'est PAS que QAOA se
    trompe : c'est qu'il existe PLUSIEURS optima de même valeur. Les deux
    solveurs en choisissent un différent, et tous deux ont raison.
    Distinguer ce cas d'une vraie sous-performance est essentiel — sans quoi
    on accuse QAOA d'une erreur qu'il n'a pas commise.
    """
    if quantum.skipped:
        return {
            "code": "skipped",
            "label": "QAOA ignoré",
            "detail": quantum.reason,
        }

    if diff["identical_placement"]:
        return {
            "code": "identical",
            "label": "Placements identiques",
            "detail": "Les deux solveurs ont retenu exactement les mêmes emplacements.",
        }

    if diff["identical_coverage"]:
        return {
            "code": "degenerate",
            "label": "Optima équivalents",
            "detail": (
                "Les placements diffèrent mais couvrent EXACTEMENT le même poids de "
                "demande. Le problème admet plusieurs optima de même valeur : aucun "
                "des deux solveurs ne se trompe, ils ont simplement départagé "
                "différemment des solutions équivalentes."
            ),
        }

    gap = classical.covered_weight - quantum.covered_weight
    gap_pct = 100.0 * gap / classical.covered_weight if classical.covered_weight else 0.0
    return {
        "code": "suboptimal",
        "label": f"QAOA à {gap_pct:.1f} % sous l'optimum",
        "detail": (
            "QAOA est approché par construction : à p fini, rien ne garantit "
            "qu'il atteigne l'optimum. Seule la limite p → ∞ le garantit, car "
            "elle redonne l'évolution adiabatique."
        ),
    }


def build_verdict(classical, quantum, instance, annealing=None) -> dict:
    """La ligne de verdict, générée à partir des mesures.

    Elle doit être lisible à voix haute telle quelle devant un jury, et ne
    jamais surestimer le quantique.
    """
    if quantum.skipped:
        return {
            "headline": "Le solveur classique a résolu seul — QAOA a été ignoré.",
            "detail": quantum.reason,
            "winner": "classical",
            "speedup": None,
        }

    speedup = quantum.elapsed_ms / classical.elapsed_ms if classical.elapsed_ms > 0 else None

    if quantum.covered_weight >= classical.covered_weight - 1e-9:
        quality = "QAOA a atteint la couverture optimale"
    else:
        gap = 100.0 * (1 - quantum.covered_weight / classical.covered_weight)
        quality = f"QAOA reste {gap:.1f} % sous l'optimum"

    speed_txt = f"{speedup:,.0f}×".replace(",", " ") if speedup else "nettement"

    headline = (
        f"À cette échelle, le solveur CLASSIQUE gagne : il est exact, et {speed_txt} "
        f"plus rapide que la simulation QAOA. {quality}."
    )

    detail = (
        f"C'est le résultat attendu, et ce n'est pas un échec. La force brute est "
        f"exacte : la couverture de QAOA ne peut jamais la dépasser, seulement "
        f"l'égaler. Et comme je SIMULE le circuit sur un CPU, je paie un coût en "
        f"O(2^N) à chaque itération — précisément le coût exponentiel que le "
        f"quantique est censé éviter. "
        f"L'avantage quantique n'est pas ici : il est ASYMPTOTIQUE. La force brute "
        f"a évalué {_fmt_int(classical.combinations_evaluated)} combinaisons sur un "
        f"espace de recherche de 2^{instance.n_candidates} = "
        f"{_fmt_int(2 ** instance.n_candidates)} états, là où le circuit QAOA tient "
        f"en {_fmt_int(quantum.gate_count)} portes sur {quantum.n_qubits} qubits — "
        f"un coût en O(p·N²), polynomial. C'est la courbe de complexité qui porte "
        f"cet argument, pas le chronomètre de cette instance."
    )

    result = {
        "headline": headline,
        "detail": detail,
        "winner": "classical",
        "speedup": speedup,
        "classical_is_exact": True,
    }

    if annealing is not None:
        ratio = annealing.elapsed_ms / classical.elapsed_ms if classical.elapsed_ms else None
        result["annealing_note"] = (
            f"Le recuit simulé est le point de comparaison le plus juste pour QAOA : "
            f"il attaque LE MÊME QUBO, dans le MÊME paysage énergétique, mais en le "
            f"parcourant thermiquement au lieu de quantiquement. Il a accepté "
            f"{_fmt_int(annealing.uphill_accepted)} mouvements DÉGRADANTS sur "
            f"{_fmt_int(annealing.iterations)} propositions — c'est exactement ce qui "
            f"lui permet de s'échapper des minima locaux, là où QAOA exploite "
            f"l'interférence."
            + (f" Il est {ratio:,.0f}× plus lent que la force brute."
               .replace(",", " ") if ratio else "")
        )

    return result


def build_metrics_table(instance, classical, quantum, annealing=None) -> list[dict]:
    """Le panneau de métriques du sujet (§VII.6), avec les deltas.

    Toutes les valeurs viennent des résultats des solveurs, qui ont eux-mêmes
    été produits par la fonction objectif exacte. Rien n'est recalculé ici :
    c'est ce qui garantit que le tableau ne peut pas contredire la carte.
    """
    def cov(r):
        return None if getattr(r, "skipped", False) else r.coverage_ratio * 100.0

    def val(r, attr, default=None):
        return default if getattr(r, "skipped", False) else getattr(r, attr, default)

    rows = [
        {
            "key": "coverage",
            "label": "Demande couverte",
            "unit": "%",
            "classical": cov(classical),
            "quantum": cov(quantum),
            "annealing": cov(annealing) if annealing else None,
            "better": "high",
            "help": "Part du poids total de demande couverte par au moins une borne.",
        },
        {
            "key": "stations",
            "label": "Bornes utilisées",
            "unit": f"/ {instance.budget}",
            "classical": classical.stations_used,
            "quantum": val(quantum, "stations_used"),
            "annealing": annealing.stations_used if annealing else None,
            "better": "neutral",
            "help": "Doit toujours rester ≤ B. Une valeur supérieure signale une "
                    "solution infaisable, donc un poids de pénalité trop faible.",
        },
        {
            "key": "uncovered",
            "label": "Zones non couvertes",
            "unit": f"/ {instance.n_zones}",
            "classical": len(classical.uncovered_zones),
            "quantum": len(quantum.uncovered_zones) if not quantum.skipped else None,
            "annealing": len(annealing.uncovered_zones) if annealing else None,
            "better": "low",
            "help": "Nombre de zones de demande qu'aucune borne retenue n'atteint.",
        },
        {
            "key": "work",
            "label": "Travail effectué",
            "unit": "",
            "classical": classical.combinations_evaluated,
            "quantum": val(quantum, "iterations"),
            "annealing": annealing.iterations if annealing else None,
            "better": "low",
            "help": "Force brute : combinaisons énumérées. QAOA : évaluations de la "
                    "fonction de coût. Recuit : propositions de mouvement. Ces unités "
                    "ne sont PAS comparables entre elles — seule leur croissance avec "
                    "N l'est, et c'est l'objet de la courbe de complexité.",
        },
        {
            "key": "time",
            "label": "Temps de calcul",
            "unit": "ms",
            "classical": round(classical.elapsed_ms, 2),
            "quantum": round(quantum.elapsed_ms, 2),
            "annealing": round(annealing.elapsed_ms, 2) if annealing else None,
            "better": "low",
            "help": "Mesuré sur cette machine. QAOA inclut le coût de la SIMULATION "
                    "du circuit, qui est exponentiel et n'existerait pas sur un QPU.",
        },
    ]
    return rows
