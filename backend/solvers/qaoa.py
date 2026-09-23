"""
Solveur quantique — QAOA en simulation locale.

QAOA = Quantum Approximate Optimization Algorithm (Farhi, Goldstone & Gutmann,
2014). C'est un algorithme HYBRIDE : un circuit quantique paramétré, dont les
paramètres sont optimisés par un algorithme classique.

  ┌─ CÔTÉ QUANTIQUE ──────────────────────────────────────────────────────┐
  │  Ne cherche RIEN. Prépare un état |ψ(γ,β)⟩, superposition pondérée des │
  │  2ⁿ solutions, dans lequel les bonnes solutions ont — si (γ,β) sont    │
  │  bons — une amplitude plus grande. C'est une DISTRIBUTION.             │
  └───────────────────────────────────────────────────────────────────────┘
  ┌─ CÔTÉ CLASSIQUE ──────────────────────────────────────────────────────┐
  │  Cherche les bons (γ,β). Ne voit du quantique qu'UN SEUL nombre :      │
  │  l'énergie moyenne ⟨H_C⟩. Optimisation continue en boîte noire.        │
  └───────────────────────────────────────────────────────────────────────┘

  |ψ(γ,β)⟩ = Π_{l=1..p} [ e^{−iβ_l H_M} · e^{−iγ_l H_C} ] |+⟩^N
  avec H_M = Σᵢ Xᵢ (mixer) et H_C l'Hamiltonien de coût issu du QUBO.

Voir explanation.md §7.

TOUT est écrit à la main : le circuit porte par porte, la boucle variationnelle,
l'échantillonnage. Qiskit ne sert qu'à appliquer les unitaires au vecteur d'état
et à porter le modèle de bruit. Aucun appel à QAOAAnsatz, QuadraticProgram ou
MinimumEigenOptimizer — le sujet l'interdit, et ce serait manquer l'essentiel.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from scipy.optimize import minimize

from ..objective import evaluate
from ..qubo import Ising, build_qubo, qubo_to_ising

# Plafond du simulateur. C'est celui du SIMULATEUR, pas de l'algorithme :
# stocker 2^N amplitudes complexes coûte 16·2^N octets, recalculés à CHAQUE
# itération de la boucle. Sur un vrai QPU, le circuit utiliserait N qubits et
# O(p·N²) portes — polynomial. Voir explanation.md §7.8.
#
# La valeur 14 est MESURÉE, pas choisie au hasard. Temps de résolution
# complet sur la machine de développement, p = 3, 3 redémarrages :
#
#     N     9     12     13     14  |    15      16
#     t  1,8s   3,0s   5,6s   8,4s  |  18,9s   75,2s
#                              ▲       ▲
#                          plafond    au-delà, l'application paraîtrait gelée
#
# Le saut de 15 à 16 est de ×4 et non de ×2 : à 16 qubits le vecteur d'état
# atteint 1 Mo et sort du cache L2, si bien que la constante multiplicative
# se dégrade en plus de la croissance exponentielle.
DEFAULT_MAX_QUBITS = int(os.environ.get("SUPERCHARGE_QAOA_MAX_QUBITS", "14"))

DEFAULT_LAYERS = 3
DEFAULT_MAXITER = 120
DEFAULT_SHOTS = 4096
DEFAULT_RESTARTS = 3
DEFAULT_SEED = 42


@dataclass
class QaoaResult:
    # --- résultat retenu (toujours évalué par la VRAIE fonction objectif) ---
    selection: list[int] = field(default_factory=list)
    covered_weight: float = 0.0
    coverage_ratio: float = 0.0
    covered_zones: list[int] = field(default_factory=list)
    uncovered_zones: list[int] = field(default_factory=list)
    stations_used: int = 0
    feasible: bool = True

    # --- ce que le circuit a RÉELLEMENT produit, sans filtrage ---
    # Exposé pour que l'effet d'un P mal choisi soit visible plutôt que masqué.
    raw_selection: list[int] = field(default_factory=list)
    raw_stations: int = 0
    raw_probability: float = 0.0
    budget_violated_in_raw: bool = False

    # --- travail effectué (exigé par le sujet) ---
    iterations: int = 0          # nb d'évaluations de la fonction de coût
    restarts: int = 0
    layers: int = 0
    shots: int = 0
    n_qubits: int = 0
    gate_count: int = 0
    two_qubit_gates: int = 0
    circuit_depth: int = 0

    # --- diagnostic quantique ---
    penalty: float = 0.0
    final_energy: float = 0.0
    optimal_energy: float | None = None   # min exact, connu par énumération
    approximation_ratio: float | None = None
    energy_trace: list[float] = field(default_factory=list)
    amplitude_snapshots: list[dict] = field(default_factory=list)

    # --- QUALITÉ DE LA DISTRIBUTION MESURÉE ---
    # Ces trois chiffres, et non le meilleur tirage, sont ce qui se dégrade
    # sous l'effet du bruit. Garder le meilleur échantillon sur plusieurs
    # milliers de mesures masquerait complètement cet effet : sur un espace
    # de 512 états, le hasard seul finirait par toucher l'optimum. Les
    # reporter est une question d'honnêteté, pas de confort.
    p_optimum: float = 0.0      # part des mesures tombant sur un optimum
    p_feasible: float = 0.0     # part des mesures respectant le budget
    mean_sampled_energy: float = 0.0

    # --- bruit (bonus) ---
    noisy: bool = False
    noise_params: dict | None = None

    # --- dégradation gracieuse ---
    skipped: bool = False
    reason: str | None = None

    elapsed_ms: float = 0.0


# --------------------------------------------------------------------------
# Construction du circuit
# --------------------------------------------------------------------------

def build_circuit(ising: Ising, gammas, betas, measure: bool = True) -> QuantumCircuit:
    """Assemble le circuit QAOA, porte par porte.

    Structure, pour chacune des p couches :

      ┌ layer de COÛT   e^{−iγ H_C} ─────────────────────────────────────┐
      │  H_C est DIAGONAL, donc tous ses termes commutent : l'exponen-   │
      │  tielle se décompose EXACTEMENT, sans approximation de Trotter.  │
      │    e^{−iγ hᵢ Zᵢ}      → RZ(2γhᵢ)  sur le qubit i                 │
      │    e^{−iγ Jᵢₖ ZᵢZₖ}   → CX(i,k) · RZ(2γJᵢₖ) sur k · CX(i,k)      │
      │  Le CX transforme la base de k en la PARITÉ de i et k ; la       │
      │  rotation applique alors une phase fonction de zᵢ·zₖ ; le second │
      │  CX restaure la base.                                            │
      └──────────────────────────────────────────────────────────────────┘
      ┌ layer MIXER     e^{−iβ H_M} ─────────────────────────────────────┐
      │  H_M = Σ Xᵢ : les termes commutent aussi, ce sont N rotations    │
      │  indépendantes RX(2β). C'est ce layer qui fait INTERFÉRER les    │
      │  états entre eux — sans lui, rien ne se passerait.               │
      └──────────────────────────────────────────────────────────────────┘

    Le facteur 2 vient de la convention Qiskit : RZ(θ) = e^{−iθZ/2}.
    """
    n = ising.n
    qc = QuantumCircuit(n)

    # |+⟩^N : l'état fondamental du mixer, préparé en une couche de Hadamard.
    # C'est l'état « je suis dans toutes les solutions à la fois ».
    qc.h(range(n))

    for gamma, beta in zip(gammas, betas):
        for i in range(n):
            if ising.h[i] != 0.0:
                qc.rz(2.0 * gamma * ising.h[i], i)
        for (i, k), Jik in ising.J.items():
            qc.cx(i, k)
            qc.rz(2.0 * gamma * Jik, k)
            qc.cx(i, k)
        for i in range(n):
            qc.rx(2.0 * beta, i)

    if measure:
        qc.measure_all()
    return qc


def evolve_statevector(energies: np.ndarray, n: int, gammas, betas) -> np.ndarray:
    """Évolution exacte de |ψ(γ,β)⟩, en exploitant la structure du problème.

    MÊME état que `build_circuit` — c'est prouvé par test (tests/test_qaoa.py),
    à 1e-10 près. Mais calculé en O(p·N·2^N) au lieu de dérouler les
    O(p·N²) portes une par une dans la couche Python de Qiskit.

    Pourquoi c'est légitime, et pourquoi c'est même plus juste :

      • LE LAYER DE COÛT EST DIAGONAL. H_C|x⟩ = E(x)|x⟩, donc
              e^{−iγH_C} |ψ⟩  =  (e^{−iγE(x)})ₓ ⊙ |ψ⟩
        Une multiplication élément par élément. Dérouler cet opérateur en
        216 portes CX pour ensuite recomposer la même diagonale, c'est payer
        4000× le prix du dispatch Python pour un résultat identique.

      • LE MIXER EST UN PRODUIT TENSORIEL. H_M = ΣXᵢ, les termes commutent,
        donc e^{−iβH_M} = ⊗ᵢ RX(2β). On applique N matrices 2×2.

    Le circuit Qiskit reste l'artefact canonique du projet : c'est lui qui est
    construit, exécuté sur Aer, mesuré, qui porte le modèle de bruit et qui
    fournit la profondeur et le comptage de portes. Cette fonction n'est qu'un
    chemin rapide pour la boucle d'optimisation, vérifié contre lui.

    Convention d'indexation : l'amplitude d'indice s correspond à l'état de
    base où le bit i de s vaut xᵢ — c'est-à-dire l'ordre little-endian de
    Qiskit, et exactement celui de `Qubo.all_energies()`.
    """
    size = 1 << n
    psi = np.full(size, 1.0 / np.sqrt(size), dtype=np.complex128)  # |+⟩^N

    for gamma, beta in zip(gammas, betas):
        # ── layer de coût : diagonal, une seule multiplication ────────────
        psi *= np.exp(-1j * gamma * energies)

        # ── layer mixer : RX(2β) sur chaque qubit ─────────────────────────
        # RX(θ) = [[cos(θ/2), −i·sin(θ/2)], [−i·sin(θ/2), cos(θ/2)]], θ = 2β
        #       = [[c, −i·s], [−i·s, c]]  avec c = cos β, s = sin β
        c = np.cos(beta)
        minus_i_s = -1j * np.sin(beta)

        for qubit in range(n):
            # On voit psi comme (bits_hauts, bit_du_qubit, bits_bas) :
            #   s = haut·2^(q+1) + b_q·2^q + bas
            # Le reshape est une simple VUE (aucune copie), et les deux
            # tranches sont contiguës — la mise à jour est un produit
            # matriciel 2×2 vectorisé sur tout le reste du registre.
            view = psi.reshape(size >> (qubit + 1), 2, 1 << qubit)
            lo = view[:, 0, :].copy()          # amplitudes avec b_q = 0
            hi = view[:, 1, :]                 # amplitudes avec b_q = 1
            view[:, 0, :] = c * lo + minus_i_s * hi
            view[:, 1, :] = minus_i_s * lo + c * hi

    return psi


def gate_statistics(ising: Ising, layers: int) -> dict:
    """Coût en portes du circuit, sans le construire.

    C'est le chiffre qui alimente la courbe de complexité : il croît en
    O(p·N²), donc POLYNOMIALEMENT en N. C'est tout l'argument du projet.
    """
    n = ising.n
    n_h = int(np.count_nonzero(ising.h))
    n_j = len(ising.J)
    per_layer = n_h + 3 * n_j + n        # RZ champs + (CX,RZ,CX) couplages + RX
    return {
        "gate_count": n + layers * per_layer,
        "two_qubit_gates": layers * 2 * n_j,
        "per_layer": per_layer,
    }


# --------------------------------------------------------------------------
# Le solveur
# --------------------------------------------------------------------------

def solve(
    instance,
    layers: int = DEFAULT_LAYERS,
    maxiter: int = DEFAULT_MAXITER,
    shots: int = DEFAULT_SHOTS,
    seed: int = DEFAULT_SEED,
    penalty: float | None = None,
    restarts: int = DEFAULT_RESTARTS,
    max_qubits: int = DEFAULT_MAX_QUBITS,
    record_trace: bool = False,
    noise_model=None,
    noise_params: dict | None = None,
) -> QaoaResult:
    """Résout l'instance par QAOA.

    `penalty=None` → P automatique. Une valeur explicite sert à démontrer en
    direct l'effet d'un poids de pénalité mal choisi.
    """
    start = time.perf_counter()
    n = instance.n_candidates

    # ── Garde-fou : plafond du simulateur ────────────────────────────────
    if n > max_qubits:
        return _skipped(instance, n, max_qubits, layers, start)

    if n == 0:
        return QaoaResult(skipped=True, reason="Aucun candidat à placer.", n_qubits=0)

    # ── QUBO → Ising ─────────────────────────────────────────────────────
    qubo = build_qubo(instance, penalty=penalty)
    ising = qubo_to_ising(qubo)

    # Énergies exactes des 2ⁿ états. Deux usages :
    #  1. calculer ⟨H_C⟩ = Σ p(x)·E(x) sans échantillonner (exact sur simulateur)
    #  2. connaître l'énergie optimale, donc le ratio d'approximation
    energies = qubo.all_energies()
    optimal_energy = float(energies.min())

    stats = gate_statistics(ising, layers)
    trace: list[float] = []
    snapshots: list[dict] = []

    # ── NORMALISATION DES ANGLES — indispensable, et non évidente ────────
    #
    # Le layer de coût applique des rotations RZ(2γ·coefficient). Les
    # coefficients de l'Ising sont de l'ordre de `scale` (ici ~15), donc
    # F(γ,β) oscille en γ avec une période ~2π/scale ≈ 0,4. L'optimum vit
    # autour de γ ≈ 0,02.
    #
    # Or COBYLA part avec un rayon de simplexe `rhobeg = 1.0` par défaut :
    # son PREMIER pas serait 50× plus large que toute la plage utile de γ.
    # Il traverserait plusieurs oscillations et atterrirait dans un bassin
    # local arbitraire. C'est exactement ce qui se produisait, et aucune
    # augmentation de p ne le rattrapait — au contraire.
    #
    # On optimise donc sur γ̃ = γ·scale, dont la période naturelle est 2π,
    # comme β. Les deux familles de paramètres vivent alors sur la même
    # échelle O(1) et rhobeg devient pertinent pour les deux.
    scale = max(
        float(np.abs(ising.h).max(initial=0.0)),
        max((abs(v) for v in ising.J.values()), default=0.0),
        1e-12,
    )

    def split(params):
        """params normalisés → (γ réels, β). γ = γ̃ / scale."""
        params = np.asarray(params, dtype=float)
        return params[:layers] / scale, params[layers:]

    sim = AerSimulator(seed_simulator=seed, noise_model=noise_model)
    use_shots_for_cost = noise_model is not None

    # Avec bruit, chaque évaluation de la fonction de coût exige un véritable
    # échantillonnage : on ne peut plus lire le vecteur d'état. On en réduit
    # donc le nombre de tirages pendant la boucle, et on garde le budget
    # complet pour la mesure finale. C'est exactement ce que font les
    # expériences sur matériel réel, où chaque tir coûte du temps machine.
    loop_shots = max(256, shots // 8) if use_shots_for_cost else shots

    def probabilities(params) -> np.ndarray:
        """Distribution de probabilité sur les 2ⁿ états, pour ces angles."""
        gammas, betas = split(params)
        if use_shots_for_cost:
            # Avec bruit : on DOIT échantillonner, comme sur un vrai QPU.
            qc = build_circuit(ising, gammas, betas, measure=True)
            counts = sim.run(qc, shots=loop_shots).result().get_counts()
            probs = np.zeros(1 << n)
            for bits, c in counts.items():
                probs[int(bits.replace(" ", ""), 2)] = c / loop_shots
            return probs
        # Sans bruit : on lit le vecteur d'état. C'est EXACT (aucun bruit
        # statistique) et bien plus rapide. Impossible sur un vrai QPU — il
        # faudrait estimer ⟨H_C⟩ par échantillonnage. C'est documenté.
        # `evolve_statevector` produit rigoureusement le même état que le
        # circuit Qiskit (prouvé à 1e-10 près par tests/test_qaoa.py) en
        # exploitant le fait que H_C est diagonal.
        return np.abs(evolve_statevector(energies, n, gammas, betas)) ** 2

    n_evals = 0

    def cost(params) -> float:
        """⟨H_C⟩ = Σₓ p(x)·E(x). Le seul nombre que le classique voit du quantique."""
        nonlocal n_evals
        n_evals += 1
        value = float(probabilities(params) @ energies)
        if record_trace:
            trace.append(value)
        return value

    # ── Boucle variationnelle, avec redémarrages ─────────────────────────
    rng = np.random.default_rng(seed)
    best_params, best_value = None, np.inf

    for attempt in range(max(1, restarts)):
        x0 = _initial_params(attempt, layers, rng)
        # rhobeg : rayon du simplexe initial de COBYLA. Grâce à la
        # normalisation, γ̃ et β vivent tous deux sur [0, 2π] : un rayon de
        # 0,5 explore franchement sans sauter par-dessus les oscillations.
        res = minimize(cost, x0, method="COBYLA",
                       options={"maxiter": maxiter, "rhobeg": 0.5})
        if res.fun < best_value:
            best_value, best_params = float(res.fun), np.asarray(res.x)

    # ── Échantillonnage final ────────────────────────────────────────────
    if record_trace:
        for label, params in (("initial", _initial_params(0, layers, np.random.default_rng(seed))),
                              ("final", best_params)):
            probs = probabilities(params)
            top = np.argsort(probs)[::-1][:12]
            snapshots.append({
                "label": label,
                "states": [
                    {"selection": [i for i in range(n) if int(s) >> i & 1],
                     "probability": float(probs[s]),
                     "energy": float(energies[s])}
                    for s in top
                ],
            })

    best_gammas, best_betas = split(best_params)
    qc = build_circuit(ising, best_gammas, best_betas, measure=True)
    # Pas de transpilation : le circuit n'utilise que h / rz / rx / cx /
    # measure, qui font partie du jeu de portes natif d'AerSimulator. Le
    # transpileur de Qiskit coûterait ~500 ms pour produire un circuit
    # équivalent. `circuit_depth` est donc la profondeur telle que construite.
    counts = sim.run(qc, shots=shots).result().get_counts()

    # Le bitstring le plus probable, SANS filtrage : c'est ce que le circuit
    # produit réellement. Si P est trop petit, il violera le budget — et on
    # l'affiche au lieu de le cacher.
    raw_bits = max(counts, key=counts.get)
    raw_state = int(raw_bits.replace(" ", ""), 2)
    raw_selection = [i for i in range(n) if raw_state >> i & 1]

    # ── Qualité de la DISTRIBUTION, pas du meilleur tirage ───────────────
    # C'est ici que le bruit se voit. `optimal_energy` est connue puisqu'on a
    # énuméré les 2^N énergies pour calculer ⟨H_C⟩ ; on ne s'en sert que pour
    # MESURER la qualité du résultat, jamais pour l'orienter.
    total_shots = sum(counts.values())
    hits_optimum = 0
    hits_feasible = 0
    energy_sum = 0.0
    for bits, count in counts.items():
        state = int(bits.replace(" ", ""), 2)
        energy_sum += energies[state] * count
        if bin(state).count("1") <= instance.budget:
            hits_feasible += count
        if energies[state] <= optimal_energy + 1e-9:
            hits_optimum += count

    p_optimum = hits_optimum / total_shots if total_shots else 0.0
    p_feasible = hits_feasible / total_shots if total_shots else 0.0
    mean_sampled_energy = energy_sum / total_shots if total_shots else 0.0

    # Le meilleur bitstring FAISABLE parmi ceux effectivement mesurés.
    # C'est le protocole QAOA canonique : la sortie est une distribution, on
    # l'échantillonne et on garde le meilleur tirage. On n'utilise jamais la
    # force brute pour choisir — uniquement des états réellement mesurés.
    best_sel, best_weight = None, -1.0
    for bits in sorted(counts, key=counts.get, reverse=True):
        state = int(bits.replace(" ", ""), 2)
        sel = [i for i in range(n) if state >> i & 1]
        if len(sel) > instance.budget:
            continue
        ev = evaluate(sel, instance)
        if ev.covered_weight > best_weight:
            best_weight, best_sel = ev.covered_weight, sel

    if best_sel is None:
        # Aucun tirage faisable : arrive quand P est très en dessous de sa
        # borne. On assume et on renvoie le tirage brut, marqué infaisable.
        best_sel = raw_selection

    ev = evaluate(best_sel, instance)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    denom = abs(optimal_energy)
    return QaoaResult(
        selection=ev.selection,
        covered_weight=ev.covered_weight,
        coverage_ratio=ev.coverage_ratio,
        covered_zones=ev.covered_zones,
        uncovered_zones=ev.uncovered_zones,
        stations_used=ev.stations_used,
        feasible=ev.feasible,
        raw_selection=raw_selection,
        raw_stations=len(raw_selection),
        raw_probability=counts[raw_bits] / shots,
        budget_violated_in_raw=len(raw_selection) > instance.budget,
        iterations=n_evals,
        restarts=max(1, restarts),
        layers=layers,
        shots=shots,
        n_qubits=n,
        gate_count=stats["gate_count"],
        two_qubit_gates=stats["two_qubit_gates"],
        circuit_depth=qc.depth(),
        penalty=qubo.penalty,
        final_energy=best_value,
        optimal_energy=optimal_energy,
        approximation_ratio=(best_value / optimal_energy) if denom > 1e-12 else None,
        energy_trace=trace,
        amplitude_snapshots=snapshots,
        p_optimum=p_optimum,
        p_feasible=p_feasible,
        mean_sampled_energy=mean_sampled_energy,
        noisy=noise_model is not None,
        noise_params=noise_params,
        elapsed_ms=elapsed_ms,
    )


def _initial_params(attempt: int, layers: int, rng) -> np.ndarray:
    """Point de départ d'un redémarrage, en coordonnées NORMALISÉES.

    Le premier essai suit une rampe « adiabatique » : γ̃ croissant, β
    décroissant. On mime la transition lente de H_M vers H_C du théorème
    adiabatique, ce qui est nettement plus efficace qu'un départ aléatoire.
    Les essais suivants tirent au hasard sur la période complète — la
    surface F(γ̃,β) a plusieurs bassins locaux, un seul départ ne suffit pas.
    """
    if attempt == 0:
        return np.concatenate([
            np.linspace(0.3, 1.5, layers),          # γ̃ croissant
            np.linspace(np.pi / 2, 0.2, layers),    # β décroissant
        ])
    return np.concatenate([
        rng.uniform(0.0, 2.0 * np.pi, layers),
        rng.uniform(0.0, np.pi, layers),
    ])


def _format_bytes(n_bytes: float) -> str:
    """Taille lisible, avec l'unité qui convient à l'ordre de grandeur.

    Indispensable ici : à N = 17 le vecteur d'état pèse 2 Mo, et l'afficher
    en gigaoctets donnerait « 0,0 Go », ce qui viderait le message de son sens.
    """
    for unit, factor in (("To", 1e12), ("Go", 1e9), ("Mo", 1e6), ("Ko", 1e3)):
        if n_bytes >= factor:
            return f"{n_bytes / factor:,.1f} {unit}".replace(",", " ").replace(".", ",")
    return f"{n_bytes:.0f} octets"


def _fr(n: float) -> str:
    """Entier avec l'espace fine insécable en séparateur de milliers."""
    return f"{int(n):,}".replace(",", " ")


def _skipped(instance, n: int, max_qubits: int, layers: int, start: float) -> QaoaResult:
    """Dégradation gracieuse au-delà du plafond du simulateur.

    Le message est PÉDAGOGIQUE, pas seulement défensif : il explique que la
    limite est celle de l'émulation classique, pas celle de l'algorithme.
    C'est exactement le point que le sujet veut faire passer.
    """
    statevector_bytes = (2 ** n) * 16
    gates = layers * (2 * n + 3 * n * (n - 1) // 2) + n
    return QaoaResult(
        skipped=True,
        n_qubits=n,
        layers=layers,
        gate_count=gates,
        elapsed_ms=(time.perf_counter() - start) * 1000.0,
        reason=(
            f"N = {n} dépasse le plafond du simulateur, fixé à {max_qubits} qubits. "
            f"Simuler {n} qubits demanderait de stocker 2^{n} = {_fr(2 ** n)} amplitudes "
            f"complexes, soit {_format_bytes(statevector_bytes)} — et de les recalculer "
            f"intégralement à CHAQUE itération de la boucle variationnelle, "
            f"soit plusieurs centaines de fois. "
            f"Ce plafond est celui du SIMULATEUR, pas de l'algorithme : sur un vrai "
            f"processeur quantique, ce même problème tiendrait en {n} qubits et "
            f"{_fr(gates)} portes, un coût en O(p·N²) qui reste polynomial. "
            f"Le solveur classique, lui, continue de tourner normalement."
        ),
    )
