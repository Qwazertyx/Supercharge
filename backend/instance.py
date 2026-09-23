"""
Chargement des données de Lyon et construction d'une instance du problème.

Une « instance » = les données géographiques fixes + un jeu de paramètres
choisi par l'utilisateur (budget, rayon, mode de poids, toggle inaccessible).
C'est l'objet que consomment les trois solveurs.

Les données brutes sont chargées UNE FOIS au démarrage (module-level cache).
Chaque requête de résolution construit une instance légère par-dessus.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .geometry import build_coverage

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

WEIGHT_MODES = ("uniform", "density")


# --------------------------------------------------------------------------
# Données statiques
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    id: int
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Zone:
    id: int
    lat: float
    lon: float
    weight_uniform: float
    weight_density: float
    inaccessible: bool
    blocked_by: str | None


@dataclass(frozen=True)
class StaticData:
    """Ce qui ne change jamais : la géographie de Lyon."""

    area: dict
    defaults: dict
    candidates: list[Candidate]
    zones: list[Zone]
    inaccessible_geojson: dict
    demand_poles: list[dict]


@lru_cache(maxsize=1)
def load_static_data() -> StaticData:
    """Lit les trois fichiers de data/. Mis en cache : lu une seule fois."""
    cand_doc = json.loads((DATA_DIR / "candidates.json").read_text(encoding="utf-8"))
    zones_doc = json.loads((DATA_DIR / "demand_zones.geojson").read_text(encoding="utf-8"))
    inacc_doc = json.loads((DATA_DIR / "inaccessible.geojson").read_text(encoding="utf-8"))

    candidates = [Candidate(**c) for c in cand_doc["candidates"]]

    zones = []
    for feature in zones_doc["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature["properties"]
        zones.append(Zone(
            id=props["id"], lat=lat, lon=lon,
            weight_uniform=props["weight_uniform"],
            weight_density=props["weight_density"],
            inaccessible=props["inaccessible"],
            blocked_by=props["blocked_by"],
        ))

    return StaticData(
        area=cand_doc["area"],
        defaults=cand_doc["defaults"],
        candidates=candidates,
        zones=zones,
        inaccessible_geojson=inacc_doc,
        demand_poles=cand_doc["demand_poles"],
    )


# --------------------------------------------------------------------------
# Instance paramétrée
# --------------------------------------------------------------------------

@dataclass
class Instance:
    """Le problème tel que les solveurs le voient.

    Attributs dérivés (calculés dans __post_init__) :
        covering_sets  covering_sets[j] = Cⱼ
        zone_masks     le même Cⱼ en masque de bits
        covered_by     covered_by[i] = zones couvrables par le candidat i
        weights        weights[j] = wⱼ, selon le mode choisi
        total_weight   Σⱼ wⱼ
    """

    candidates: list[Candidate]
    zones: list[Zone]
    budget: int
    radius_m: float
    weight_mode: str = "uniform"

    covering_sets: list[set[int]] = field(default_factory=list, repr=False)
    zone_masks: list[int] = field(default_factory=list, repr=False)
    covered_by: list[set[int]] = field(default_factory=list, repr=False)
    weights: list[float] = field(default_factory=list, repr=False)
    total_weight: float = 0.0

    def __post_init__(self) -> None:
        self.covering_sets, self.zone_masks, self.covered_by = build_coverage(
            self.candidates, self.zones, self.radius_m
        )
        attr = "weight_uniform" if self.weight_mode == "uniform" else "weight_density"
        self.weights = [getattr(z, attr) for z in self.zones]
        self.total_weight = sum(self.weights)

    @property
    def n_candidates(self) -> int:
        return len(self.candidates)

    @property
    def n_zones(self) -> int:
        return len(self.zones)


def build_instance(
    budget: int,
    radius_m: float,
    weight_mode: str = "uniform",
    respect_inaccessible: bool = True,
    n_candidates: int | None = None,
) -> Instance:
    """Construit une instance à partir des paramètres de l'interface.

    `respect_inaccessible` — sémantique documentée (voir explanation.md §2.4) :
        True  (défaut) les zones tombant dans le Rhône, la Saône ou l'emprise
                       ferroviaire sont RETIRÉES du problème. Personne n'habite
                       dans l'eau, il n'y a donc pas de demande à y couvrir.
        False          toutes les zones comptent. Les solveurs peuvent alors
                       « gagner » des points en couvrant un fleuve. C'est
                       volontairement absurde, et c'est pédagogique : ça montre
                       que le paramètre change réellement le résultat.

    `n_candidates` — tronque la liste des candidats aux N premiers. Sert au
    mode « scaling demo » et aux tests de montée en charge. None = tous.
    """
    if weight_mode not in WEIGHT_MODES:
        raise ValueError(f"weight_mode doit être dans {WEIGHT_MODES}, reçu {weight_mode!r}")

    static = load_static_data()

    candidates = static.candidates
    if n_candidates is not None:
        candidates = candidates[:n_candidates]

    zones = static.zones
    if respect_inaccessible:
        zones = [z for z in zones if not z.inaccessible]

    # Les identifiants de zone doivent rester denses (0..M-1) après filtrage,
    # sinon les masques de bits et les indices de listes divergent.
    zones = [
        Zone(id=new_id, lat=z.lat, lon=z.lon,
             weight_uniform=z.weight_uniform, weight_density=z.weight_density,
             inaccessible=z.inaccessible, blocked_by=z.blocked_by)
        for new_id, z in enumerate(zones)
    ]

    budget = max(0, min(int(budget), len(candidates)))

    return Instance(
        candidates=candidates,
        zones=zones,
        budget=budget,
        radius_m=float(radius_m),
        weight_mode=weight_mode,
    )
