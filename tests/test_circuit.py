"""
Le circuit QAOA.

Le test décisif de ce fichier est `test_le_chemin_rapide_est_le_circuit_qiskit`.

La boucle variationnelle n'exécute pas le circuit porte par porte : elle
utilise une évolution vectorisée qui exploite le fait que H_C est diagonal.
C'est 35 fois plus rapide, mais ce ne serait pas défendable si les deux
chemins pouvaient diverger. Ce test le prouve sur des angles aléatoires, à
la précision machine.
"""

from __future__ import annotations

import numpy as np
import pytest
from qiskit.quantum_info import Statevector

from backend.instance import build_instance
from backend.qubo import build_qubo, qubo_to_ising
from backend.solvers.qaoa import build_circuit, evolve_statevector, gate_statistics


@pytest.fixture(scope="module")
def petite_instance():
    """Petite instance : on veut pouvoir comparer les 2^N amplitudes."""
    return build_instance(budget=2, radius_m=300, weight_mode="uniform", n_candidates=7)


# --------------------------------------------------------------------------
# Équivalence entre le chemin rapide et le circuit
# --------------------------------------------------------------------------

def test_le_chemin_rapide_est_le_circuit_qiskit(petite_instance):
    """Les deux préparent RIGOUREUSEMENT le même état quantique."""
    qubo = build_qubo(petite_instance)
    ising = qubo_to_ising(qubo)
    energies = qubo.all_energies()
    rng = np.random.default_rng(1234)

    for _ in range(12):
        p = int(rng.integers(1, 5))
        gammas = rng.uniform(-0.4, 0.4, p)
        betas = rng.uniform(-np.pi, np.pi, p)

        par_qiskit = np.asarray(
            Statevector(build_circuit(ising, gammas, betas, measure=False)).probabilities())
        par_chemin_rapide = np.abs(evolve_statevector(energies, qubo.n, gammas, betas)) ** 2

        assert np.abs(par_qiskit - par_chemin_rapide).max() < 1e-10


def test_lordre_des_bits_est_celui_de_qiskit(petite_instance):
    """L'amplitude d'indice s doit correspondre à l'état où le bit i de s
    vaut xᵢ. Une inversion d'ordre passerait inaperçue mais fausserait
    silencieusement TOUTES les énergies."""
    from qiskit import QuantumCircuit

    qubo = build_qubo(petite_instance)
    energies = qubo.all_energies()
    n = qubo.n

    for s in (0, 1, 5, (1 << n) - 1, 0b1010101):
        s = s % (1 << n)
        qc = QuantumCircuit(n)
        for i in range(n):
            if (s >> i) & 1:
                qc.x(i)
        probs = np.asarray(Statevector(qc).probabilities())
        assert int(np.argmax(probs)) == s
        # l'espérance d'un état de base est exactement son énergie
        assert float(probs @ energies) == pytest.approx(energies[s], abs=1e-9)


# --------------------------------------------------------------------------
# Structure du circuit
# --------------------------------------------------------------------------

def test_letat_initial_est_la_superposition_uniforme(petite_instance):
    """Avant toute couche, les 2^N états doivent être équiprobables : c'est
    l'état fondamental du mixer, et le point de départ de l'algorithme."""
    ising = qubo_to_ising(build_qubo(petite_instance))
    n = ising.n
    probs = np.asarray(Statevector(build_circuit(ising, [], [], measure=False)).probabilities())
    assert np.allclose(probs, 1.0 / (1 << n))


def test_le_circuit_ne_contient_que_les_portes_attendues(petite_instance):
    """h, rz, rx, cx et measure : toutes natives d'AerSimulator. C'est ce qui
    permet de se passer de transpilation, qui coûtait 500 ms par résolution."""
    ising = qubo_to_ising(build_qubo(petite_instance))
    qc = build_circuit(ising, [0.1, 0.2], [0.3, 0.4], measure=True)
    assert set(qc.count_ops()) <= {"h", "rz", "rx", "cx", "measure", "barrier"}


def test_le_comptage_de_portes_correspond_au_circuit_reel(petite_instance):
    """`gate_statistics` sert à tracer la courbe de complexité sans construire
    le circuit. Il doit donc dire la vérité."""
    ising = qubo_to_ising(build_qubo(petite_instance))
    for layers in (1, 2, 3, 5):
        annonce = gate_statistics(ising, layers)
        reel = build_circuit(ising, [0.1] * layers, [0.2] * layers, measure=False)
        ops = reel.count_ops()
        total = sum(ops[k] for k in ("h", "rz", "rx", "cx") if k in ops)
        assert annonce["gate_count"] == total
        assert annonce["two_qubit_gates"] == ops.get("cx", 0)


def test_le_cout_en_portes_est_quadratique_en_n():
    """O(p·N²), l'argument central du projet.

    On le vérifie en doublant N : un coût quadratique quadruple, alors que
    l'espace de recherche est élevé à la puissance 2^N.
    """
    couts = {}
    for n in (5, 10, 20):
        inst = build_instance(budget=2, radius_m=300, n_candidates=n)
        ising = qubo_to_ising(build_qubo(inst))
        couts[n] = gate_statistics(ising, 3)["gate_count"]

    ratio_5_10 = couts[10] / couts[5]
    ratio_10_20 = couts[20] / couts[10]
    assert 3.0 < ratio_5_10 < 5.0, "doubler N doit environ quadrupler le coût"
    assert 3.0 < ratio_10_20 < 5.0


def test_le_nombre_de_couches_multiplie_le_circuit(petite_instance):
    ising = qubo_to_ising(build_qubo(petite_instance))
    une = gate_statistics(ising, 1)
    quatre = gate_statistics(ising, 4)
    assert quatre["two_qubit_gates"] == 4 * une["two_qubit_gates"]


# --------------------------------------------------------------------------
# Propriétés physiques
# --------------------------------------------------------------------------

def test_levolution_conserve_la_norme(petite_instance):
    """L'évolution quantique est unitaire : la somme des probabilités vaut 1.
    Une norme qui dérive signalerait une porte mal implémentée."""
    qubo = build_qubo(petite_instance)
    energies = qubo.all_energies()
    rng = np.random.default_rng(99)
    for _ in range(8):
        p = int(rng.integers(1, 6))
        psi = evolve_statevector(energies, qubo.n,
                                 rng.uniform(-1, 1, p), rng.uniform(-np.pi, np.pi, p))
        assert float(np.abs(psi) ** 2 @ np.ones_like(energies)) == pytest.approx(1.0, abs=1e-12)


def test_un_gamma_nul_laisse_la_distribution_uniforme(petite_instance):
    """Sans layer de coût, le mixer seul ne peut rien distinguer : il agit
    identiquement sur tous les qubits. La distribution doit rester plate."""
    qubo = build_qubo(petite_instance)
    energies = qubo.all_energies()
    probs = np.abs(evolve_statevector(energies, qubo.n, [0.0, 0.0], [0.7, 0.3])) ** 2
    assert np.allclose(probs, 1.0 / (1 << qubo.n), atol=1e-12)
