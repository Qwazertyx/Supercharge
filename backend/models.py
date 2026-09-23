"""
Schémas de requête (Pydantic).

Toute valeur venant de l'interface est bornée ICI, une seule fois. Les
solveurs peuvent alors supposer leurs entrées saines — aucun d'eux ne
re-valide, et aucun ne peut être appelé avec un rayon négatif ou un nombre
de couches absurde.

Les bornes sont aussi ce qui protège le serveur : sans plafond sur `layers`
ou `shots`, une requête pourrait faire tourner le simulateur indéfiniment.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .solvers.qaoa import (
    DEFAULT_LAYERS,
    DEFAULT_MAX_QUBITS,
    DEFAULT_MAXITER,
    DEFAULT_RESTARTS,
    DEFAULT_SEED,
    DEFAULT_SHOTS,
)

WEIGHT_MODES = ("uniform", "density")


class NoiseRequest(BaseModel):
    """[BONUS] Modèle de bruit dépolarisant appliqué au circuit QAOA.

    Les valeurs par défaut correspondent à l'ordre de grandeur d'un
    processeur supraconducteur de 2024 : les portes à deux qubits se
    trompent ~100× plus souvent que celles à un qubit. C'est ce rapport
    qui fait tout le problème, puisque le circuit QAOA contient O(p·N²)
    portes CX.
    """

    enabled: bool = False
    one_qubit_error: float = Field(default=1e-3, ge=0.0, le=0.5)
    two_qubit_error: float = Field(default=1e-2, ge=0.0, le=0.5)
    readout_error: float = Field(default=1e-2, ge=0.0, le=0.5)


class SolveRequest(BaseModel):
    """Paramètres de résolution, tous pilotés depuis l'interface."""

    # ── Le problème ──────────────────────────────────────────────────────
    budget: int = Field(default=3, ge=0, le=32,
                        description="B — nombre maximum de bornes constructibles")
    radius_m: float = Field(default=300.0, ge=10.0, le=5000.0,
                            description="r — rayon de couverture d'une borne, en mètres")
    weight_mode: str = Field(default="uniform",
                             description="'uniform' (défaut du sujet) ou 'density'")
    respect_inaccessible: bool = Field(default=True,
                                       description="retirer les zones dans l'eau / sur les voies")
    n_candidates: int | None = Field(default=None, ge=1, le=32,
                                     description="tronque à N candidats (mode scaling). None = tous")

    # ── Le QUBO ──────────────────────────────────────────────────────────
    penalty: float | None = Field(default=None, gt=0.0,
                                  description="P. None = calculé automatiquement (1,1 × max Wᵢ)")

    # ── QAOA ─────────────────────────────────────────────────────────────
    layers: int = Field(default=DEFAULT_LAYERS, ge=1, le=12, description="p — nb de couches")
    shots: int = Field(default=DEFAULT_SHOTS, ge=128, le=32768)
    restarts: int = Field(default=DEFAULT_RESTARTS, ge=1, le=16)
    maxiter: int = Field(default=DEFAULT_MAXITER, ge=10, le=2000)
    seed: int = Field(default=DEFAULT_SEED, ge=0)
    max_qubits: int = Field(default=DEFAULT_MAX_QUBITS, ge=2, le=24,
                            description="plafond du simulateur ; au-delà, QAOA est ignoré")
    noise: NoiseRequest = Field(default_factory=NoiseRequest)

    # ── Extras ───────────────────────────────────────────────────────────
    run_annealing: bool = Field(default=True, description="[bonus] 3e solveur, recuit simulé")
    record_trace: bool = Field(default=True,
                               description="[bonus] enregistrer la convergence et les amplitudes")

    @field_validator("weight_mode")
    @classmethod
    def _check_weight_mode(cls, v: str) -> str:
        if v not in WEIGHT_MODES:
            raise ValueError(f"weight_mode doit valoir {' ou '.join(WEIGHT_MODES)}")
        return v


class ComplexityRequest(BaseModel):
    """Paramètres de la courbe de complexité — le visuel n°1 du projet."""

    n_max: int = Field(default=60, ge=4, le=200)
    budget: int = Field(default=3, ge=1, le=64)
    layers: int = Field(default=DEFAULT_LAYERS, ge=1, le=12)
    maxiter: int = Field(default=DEFAULT_MAXITER, ge=10, le=2000)
    budget_scales_with_n: bool = Field(
        default=False,
        description="si vrai, B = N/2 — le régime des déploiements réels, "
                    "où C(N, N/2) ≈ 2^N/√N redevient exponentiel",
    )
