"""
Les solveurs.

Le test central est celui-ci : la force brute est la VÉRITÉ TERRAIN du projet.
On le vérifie contre une énumération indépendante, écrite autrement, et non
contre lui-même. Sans cette garantie, rien de ce qui est construit au-dessus
n'a de valeur (sujet §VII.3).
"""

from __future__ import annotations

from itertools import combinations

import pytest

from backend.instance import build_instance
from backend.objective import evaluate
from backend.solvers import annealing, brute_force, qaoa


@pytest.fixture(scope="module")
def reference():
    """L'instance de référence documentée : Lyon, N = 9, B = 3, r = 300 m."""
    return build_instance(budget=3, radius_m=300, weight_mode="uniform",
                          respect_inaccessible=True, n_candidates=9)


# --------------------------------------------------------------------------
# La force brute est-elle vraiment exacte ?
# --------------------------------------------------------------------------

def enumeration_independante(instance):
    """Optimum recalculé SANS masques de bits ni code partagé.

    Volontairement naïve et écrite autrement que le solveur : si les deux
    implémentations s'accordent, l'accord n'est pas un artefact d'un bug commun.
    """
    best = -1.0
    for k in range(instance.budget + 1):
        for combo in combinations(range(instance.n_candidates), k):
            chosen = set(combo)
            total = 0.0
            for j, cj in enumerate(instance.covering_sets):
                if cj & chosen:                       # intersection d'ensembles
                    total += instance.weights[j]
            best = max(best, total)
    return best


def test_la_force_brute_trouve_bien_loptimum(reference):
    resultat = brute_force.solve(reference)
    assert resultat.covered_weight == pytest.approx(enumeration_independante(reference))


@pytest.mark.parametrize("budget", [0, 1, 2, 3, 4, 5])
@pytest.mark.parametrize("radius", [150.0, 300.0, 500.0])
def test_la_force_brute_reste_exacte_sur_tout_le_domaine(budget, radius):
    inst = build_instance(budget=budget, radius_m=radius, n_candidates=9)
    assert brute_force.solve(inst).covered_weight == pytest.approx(
        enumeration_independante(inst))


def test_le_nombre_de_combinaisons_est_celui_annonce(reference):
    """Σₖ≤3 C(9,k) = 1 + 9 + 36 + 84 = 130."""
    assert brute_force.solve(reference).combinations_evaluated == 130
    assert brute_force.count_combinations(9, 3) == 130


def test_le_resultat_affiche_passe_par_la_fonction_objectif(reference):
    """La boucle chaude optimisée et la fonction objectif doivent coïncider.

    Si elles divergeaient, les chiffres du tableau contrediraient la carte.
    """
    r = brute_force.solve(reference)
    ev = evaluate(r.selection, reference)
    assert r.covered_weight == pytest.approx(ev.covered_weight)
    assert r.covered_zones == ev.covered_zones
    assert r.uncovered_zones == ev.uncovered_zones
    assert len(r.covered_zones) + len(r.uncovered_zones) == reference.n_zones


# --------------------------------------------------------------------------
# Monotonie — c'est le lemme qui autorise « ≤ B » → « = B » dans le QUBO
# --------------------------------------------------------------------------

def test_la_couverture_croit_avec_le_budget():
    """Ajouter une borne ne peut JAMAIS réduire la couverture.

    C'est exactement le lemme sur lequel repose la pénalité d'ÉGALITÉ du
    QUBO : puisqu'un optimum sature toujours le budget, on peut remplacer
    l'inégalité par une égalité sans perdre d'optimum, et donc se passer de
    variables d'écart. Voir explanation.md §5.4.
    """
    precedent = -1.0
    for budget in range(0, 7):
        inst = build_instance(budget=budget, radius_m=300, n_candidates=9)
        courant = brute_force.solve(inst).covered_weight
        assert courant >= precedent - 1e-12
        precedent = courant


def test_ajouter_une_borne_a_une_selection_ne_nuit_jamais(reference):
    base = evaluate([0, 1], reference).covered_weight
    for i in range(reference.n_candidates):
        assert evaluate([0, 1, i], reference).covered_weight >= base - 1e-12


# --------------------------------------------------------------------------
# Les paramètres doivent réellement changer le résultat
# --------------------------------------------------------------------------

def test_le_toggle_des_zones_inaccessibles_change_le_probleme():
    avec = build_instance(budget=3, radius_m=300, respect_inaccessible=True, n_candidates=9)
    sans = build_instance(budget=3, radius_m=300, respect_inaccessible=False, n_candidates=9)
    assert sans.n_zones > avec.n_zones
    assert brute_force.solve(avec).coverage_ratio != pytest.approx(
        brute_force.solve(sans).coverage_ratio)


def test_le_mode_de_poids_change_le_probleme():
    uni = build_instance(budget=3, radius_m=300, weight_mode="uniform", n_candidates=9)
    den = build_instance(budget=3, radius_m=300, weight_mode="density", n_candidates=9)
    assert uni.total_weight != pytest.approx(den.total_weight)


def test_un_mode_de_poids_inconnu_est_refuse():
    with pytest.raises(ValueError):
        build_instance(budget=3, radius_m=300, weight_mode="magique")


def test_les_identifiants_de_zones_restent_denses_apres_filtrage():
    """Après retrait des zones inaccessibles, les id doivent rester 0..M-1.

    Sinon les masques de bits et les index de listes se désynchroniseraient
    silencieusement, et la carte afficherait les mauvaises zones.
    """
    inst = build_instance(budget=3, radius_m=300, respect_inaccessible=True)
    assert [z.id for z in inst.zones] == list(range(inst.n_zones))


# --------------------------------------------------------------------------
# QAOA
# --------------------------------------------------------------------------

def test_qaoa_atteint_loptimum_sur_linstance_de_reference(reference):
    """Le sujet l'exige : « it should land on the optimum or very close to it
    most of the time ». On vérifie sur plusieurs graines, pas sur une seule."""
    optimum = brute_force.solve(reference).covered_weight
    resultats = [qaoa.solve(reference, seed=s, record_trace=False) for s in range(4)]
    atteints = sum(r.covered_weight >= optimum - 1e-9 for r in resultats)
    assert atteints == len(resultats), (
        f"{atteints}/{len(resultats)} exécutions ont atteint l'optimum")


def test_qaoa_ne_peut_jamais_depasser_la_force_brute(reference):
    """La force brute est exacte : rien ne peut faire mieux. Si ce test
    échouait, ce serait la force brute qui serait fausse."""
    optimum = brute_force.solve(reference).covered_weight
    assert qaoa.solve(reference, seed=7, record_trace=False).covered_weight <= optimum + 1e-9


def test_qaoa_respecte_le_budget_avec_la_penalite_automatique(reference):
    r = qaoa.solve(reference, seed=3, record_trace=False)
    assert r.stations_used <= reference.budget
    assert r.feasible


def test_qaoa_rend_compte_de_son_travail(reference):
    r = qaoa.solve(reference, seed=1, record_trace=False)
    assert r.iterations > 0          # exigé par le sujet
    assert r.gate_count > 0
    assert r.two_qubit_gates > 0
    assert r.n_qubits == reference.n_candidates


# --------------------------------------------------------------------------
# Dégradation gracieuse au-delà du plafond du simulateur
# --------------------------------------------------------------------------

def test_au_dela_du_plafond_qaoa_se_desactive_proprement():
    """Le sujet : « should degrade or be skipped gracefully, not freeze »."""
    inst = build_instance(budget=3, radius_m=300, n_candidates=18)
    r = qaoa.solve(inst, max_qubits=14, record_trace=False)
    assert r.skipped
    assert r.reason and "plafond" in r.reason.lower()
    assert str(inst.n_candidates) in r.reason
    # le message doit expliquer que la limite est celle du SIMULATEUR
    assert "SIMULATEUR" in r.reason


def test_le_solveur_classique_continue_au_dela_du_plafond():
    inst = build_instance(budget=3, radius_m=300, n_candidates=18)
    assert qaoa.solve(inst, max_qubits=14, record_trace=False).skipped
    classique = brute_force.solve(inst)
    assert classique.covered_weight > 0
    assert classique.stations_used <= inst.budget


def test_sous_le_plafond_qaoa_ne_se_desactive_pas(reference):
    assert not qaoa.solve(reference, max_qubits=14, record_trace=False).skipped


# --------------------------------------------------------------------------
# Recuit simulé (bonus)
# --------------------------------------------------------------------------

def test_le_recuit_atteint_loptimum_sur_linstance_de_reference(reference):
    optimum = brute_force.solve(reference).covered_weight
    for seed in range(3):
        r = annealing.solve(reference, seed=seed, record_trace=False)
        assert r.covered_weight >= optimum - 1e-9


def test_le_recuit_respecte_le_budget(reference):
    r = annealing.solve(reference, seed=0, record_trace=False)
    assert r.stations_used <= reference.budget
    assert r.feasible


def test_le_recuit_accepte_des_mouvements_degradants(reference):
    """C'est le cœur du recuit : sans mouvements dégradants acceptés, il ne
    serait qu'un algorithme glouton et resterait bloqué au premier minimum
    local. Si ce compteur est nul, la température est mal calibrée."""
    r = annealing.solve(reference, seed=0, record_trace=False)
    assert r.uphill_accepted > 0
    assert r.accepted <= r.iterations


# --------------------------------------------------------------------------
# Cohérence entre les trois solveurs
# --------------------------------------------------------------------------

def test_les_trois_solveurs_mesurent_avec_la_meme_fonction(reference):
    """Chacun doit pouvoir être recalculé par `evaluate` sur sa sélection.

    C'est la garantie structurelle que les métriques ne peuvent pas
    contredire la carte, exigence explicite du sujet (§VII.6).
    """
    resultats = [
        brute_force.solve(reference),
        qaoa.solve(reference, seed=2, record_trace=False),
        annealing.solve(reference, seed=2, record_trace=False),
    ]
    for r in resultats:
        ev = evaluate(r.selection, reference)
        assert r.covered_weight == pytest.approx(ev.covered_weight)
        assert r.coverage_ratio == pytest.approx(ev.coverage_ratio)
        assert sorted(r.covered_zones) == sorted(ev.covered_zones)
        assert len(r.covered_zones) + len(r.uncovered_zones) == reference.n_zones
