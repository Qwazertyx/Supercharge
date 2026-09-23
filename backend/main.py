"""
Application FastAPI — API de résolution + service du frontend statique.

Un seul processus sert tout : pas de second conteneur, pas de CORS, pas de
build step. `docker compose up` et c'est en ligne.

Routes :
    GET  /api/instance    l'instance de référence de Lyon (état par défaut)
    POST /api/solve       résout avec les 2 (ou 3) solveurs et compare
    POST /api/complexity  les quatre courbes de croissance
    GET  /api/health      sonde de vivacité
    GET  /                le frontend
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import complexity as complexity_mod
from .compare import build_metrics_table, build_verdict, classify_agreement, diff_solutions
from .instance import build_instance, load_static_data
from .models import ComplexityRequest, SolveRequest
from .qubo import build_qubo, marginal_gains, qubo_fidelity, qubo_to_ising
from .solvers import annealing as annealing_solver
from .solvers import brute_force, qaoa

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="Supercharge",
    description=(
        "Placement optimal de bornes de recharge sur la Presqu'île de Lyon — "
        "force brute exacte contre QAOA quantique, sur la même instance."
    ),
    version="1.0.0",
)


# --------------------------------------------------------------------------
# Sérialisation
# --------------------------------------------------------------------------

def _solver_payload(result, kind: str, label: str, work_label: str, work_value) -> dict:
    """Forme commune à tous les solveurs, pour que le frontend soit générique."""
    if getattr(result, "skipped", False):
        return {
            "kind": kind, "label": label, "skipped": True,
            "reason": result.reason,
            "n_qubits": getattr(result, "n_qubits", 0),
            "gate_count": getattr(result, "gate_count", 0),
            "elapsed_ms": round(result.elapsed_ms, 3),
        }

    return {
        "kind": kind,
        "label": label,
        "skipped": False,
        "selection": result.selection,
        "covered_weight": round(result.covered_weight, 6),
        "coverage_ratio": result.coverage_ratio,
        "covered_zones": result.covered_zones,
        "uncovered_zones": result.uncovered_zones,
        "stations_used": result.stations_used,
        "feasible": getattr(result, "feasible", True),
        "work_label": work_label,
        "work_value": work_value,
        "elapsed_ms": round(result.elapsed_ms, 3),
    }


def _quantum_extras(result) -> dict:
    """Les diagnostics propres au solveur quantique."""
    if result.skipped:
        return {}
    return {
        "iterations": result.iterations,
        "restarts": result.restarts,
        "layers": result.layers,
        "shots": result.shots,
        "n_qubits": result.n_qubits,
        "gate_count": result.gate_count,
        "two_qubit_gates": result.two_qubit_gates,
        "circuit_depth": result.circuit_depth,
        "penalty": result.penalty,
        "final_energy": result.final_energy,
        "optimal_energy": result.optimal_energy,
        "energy_trace": result.energy_trace,
        "amplitude_snapshots": result.amplitude_snapshots,
        # Qualité de la distribution mesurée : c'est CELA que le bruit dégrade.
        "p_optimum": result.p_optimum,
        "p_feasible": result.p_feasible,
        "mean_sampled_energy": result.mean_sampled_energy,
        "noisy": result.noisy,
        "noise_params": result.noise_params,
        # Ce que le circuit a produit SANS filtrage : c'est ici que se voit
        # l'effet d'un poids de pénalité mal choisi.
        "raw_selection": result.raw_selection,
        "raw_stations": result.raw_stations,
        "raw_probability": result.raw_probability,
        "budget_violated_in_raw": result.budget_violated_in_raw,
    }


def _build_noise_model(noise):
    """[BONUS] Modèle de bruit dépolarisant, construit à la demande.

    L'import est local : sans bruit demandé, on ne paie jamais le coût de
    chargement du module de bruit d'Aer.
    """
    if not noise.enabled:
        return None, None

    from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

    model = NoiseModel()
    if noise.one_qubit_error > 0:
        model.add_all_qubit_quantum_error(
            depolarizing_error(noise.one_qubit_error, 1), ["rz", "rx", "h", "sx", "x"])
    if noise.two_qubit_error > 0:
        model.add_all_qubit_quantum_error(
            depolarizing_error(noise.two_qubit_error, 2), ["cx"])
    if noise.readout_error > 0:
        e = noise.readout_error
        model.add_all_qubit_readout_error(ReadoutError([[1 - e, e], [e, 1 - e]]))

    return model, {
        "one_qubit_error": noise.one_qubit_error,
        "two_qubit_error": noise.two_qubit_error,
        "readout_error": noise.readout_error,
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/instance")
def get_instance() -> dict:
    """L'instance de référence : géographie de Lyon et valeurs par défaut.

    C'est l'état exact dans lequel l'application démarre, pour que
    l'évaluation soit reproductible (sujet §IX).
    """
    static = load_static_data()
    return {
        "area": static.area,
        "defaults": static.defaults,
        "candidates": [
            {"id": c.id, "name": c.name, "lat": c.lat, "lon": c.lon}
            for c in static.candidates
        ],
        "zones": [
            {"id": z.id, "lat": z.lat, "lon": z.lon,
             "weight_uniform": z.weight_uniform, "weight_density": z.weight_density,
             "inaccessible": z.inaccessible, "blocked_by": z.blocked_by}
            for z in static.zones
        ],
        "inaccessible": static.inaccessible_geojson,
        "demand_poles": static.demand_poles,
        "limits": {
            "max_candidates": len(static.candidates),
            "qaoa_max_qubits": qaoa.DEFAULT_MAX_QUBITS,
        },
    }


@app.post("/api/solve")
def solve(req: SolveRequest) -> dict:
    """Résout l'instance courante avec tous les solveurs et les compare.

    Omettre `n_candidates` donne l'INSTANCE DE RÉFÉRENCE documentée, et non
    la totalité des emplacements disponibles. Le dépôt embarque 20 lieux
    lyonnais, mais l'instance de référence n'en utilise que 9 : un correcteur
    qui appelle cette route avec un corps vide doit retrouver exactement les
    chiffres du README (sujet §IX, reproductibilité de l'évaluation).
    """
    defaults = load_static_data().defaults
    n_candidates = req.n_candidates
    if n_candidates is None:
        n_candidates = defaults.get("n_candidates")

    instance = build_instance(
        budget=req.budget,
        radius_m=req.radius_m,
        weight_mode=req.weight_mode,
        respect_inaccessible=req.respect_inaccessible,
        n_candidates=n_candidates,
    )

    # ── Les trois solveurs, sur la MÊME instance ─────────────────────────
    classical = brute_force.solve(instance)

    noise_model, noise_params = _build_noise_model(req.noise)
    quantum = qaoa.solve(
        instance,
        layers=req.layers, maxiter=req.maxiter, shots=req.shots,
        seed=req.seed, penalty=req.penalty, restarts=req.restarts,
        max_qubits=req.max_qubits, record_trace=req.record_trace,
        noise_model=noise_model, noise_params=noise_params,
    )

    heuristic = None
    if req.run_annealing:
        heuristic = annealing_solver.solve(
            instance, penalty=req.penalty, seed=req.seed, record_trace=req.record_trace)

    # ── Diagnostic du QUBO ───────────────────────────────────────────────
    qubo = build_qubo(instance, penalty=req.penalty)
    ising = qubo_to_ising(qubo)
    fidelity = qubo_fidelity(instance)
    W = marginal_gains(instance)

    # ── Comparaison ──────────────────────────────────────────────────────
    diff = diff_solutions(classical, quantum, instance) if not quantum.skipped else None
    agreement = classify_agreement(classical, quantum, diff) if diff else \
        {"code": "skipped", "label": "QAOA ignoré", "detail": quantum.reason}

    return {
        "params": {
            "budget": instance.budget,
            "radius_m": instance.radius_m,
            "weight_mode": instance.weight_mode,
            "respect_inaccessible": req.respect_inaccessible,
            "n_candidates": instance.n_candidates,
            "layers": req.layers,
            "shots": req.shots,
            "restarts": req.restarts,
            "seed": req.seed,
            "penalty_requested": req.penalty,
            "penalty_used": qubo.penalty,
            "penalty_is_auto": req.penalty is None,
            "max_qubits": req.max_qubits,
        },
        "instance": {
            "n_candidates": instance.n_candidates,
            "n_zones": instance.n_zones,
            "total_weight": round(instance.total_weight, 6),
            "candidates": [
                {"id": c.id, "name": c.name, "lat": c.lat, "lon": c.lon,
                 "marginal_weight": round(float(W[i]), 4)}
                for i, c in enumerate(instance.candidates)
            ],
            "zones": [
                {"id": z.id, "lat": z.lat, "lon": z.lon,
                 "weight": round(instance.weights[j], 4)}
                for j, z in enumerate(instance.zones)
            ],
        },
        "qubo": {
            "penalty": qubo.penalty,
            "penalty_lower_bound": qubo.max_marginal_gain,
            "max_marginal_gain": qubo.max_marginal_gain,
            "penalty_is_safe": qubo.penalty > qubo.max_marginal_gain,
            "n_ising_terms": ising.n_terms,
            "n_couplings": len(ising.J),
            "fidelity": {
                "max_multiplicity": fidelity.max_multiplicity,
                "exact": fidelity.exact,
                "zones_at_risk": fidelity.zones_at_risk,
                "message": fidelity.message,
            },
        },
        "solvers": {
            "classical": {
                **_solver_payload(classical, "classical", "Force brute (exact)",
                                  "combinaisons évaluées",
                                  classical.combinations_evaluated),
                "combinations_evaluated": classical.combinations_evaluated,
                "optimal_ties": classical.optimal_ties,
            },
            "quantum": {
                **_solver_payload(quantum, "quantum", "QAOA (approché)",
                                  "itérations", getattr(quantum, "iterations", 0)),
                **_quantum_extras(quantum),
            },
            "annealing": None if heuristic is None else {
                **_solver_payload(heuristic, "annealing", "Recuit simulé (approché)",
                                  "propositions", heuristic.iterations),
                "accepted": heuristic.accepted,
                "uphill_accepted": heuristic.uphill_accepted,
                "final_energy": heuristic.final_energy,
                "energy_trace": heuristic.energy_trace,
                "restarts": heuristic.restarts,
            },
        },
        "comparison": {
            "diff": diff,
            "agreement": agreement,
            "metrics": build_metrics_table(instance, classical, quantum, heuristic),
            "verdict": build_verdict(classical, quantum, instance, heuristic),
        },
    }


@app.post("/api/complexity")
def complexity(req: ComplexityRequest) -> dict:
    """Les quatre courbes de croissance — le visuel n°1 du projet."""
    curves = complexity_mod.build_curves(
        n_max=req.n_max, budget=req.budget, layers=req.layers,
        maxiter=req.maxiter, budget_scales_with_n=req.budget_scales_with_n,
    )
    for point in curves["points"]:
        point["brute_force_duration"] = complexity_mod.humanize_duration(point["brute_force"])
        point["search_space_duration"] = complexity_mod.humanize_duration(point["search_space"])
    return curves


# --------------------------------------------------------------------------
# Frontend statique — monté en dernier pour ne pas masquer /api
# --------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
