#!/usr/bin/env python3
"""
Génère l'instance de référence « Lyon — Presqu'île » de façon DÉTERMINISTE.

Produit trois fichiers dans data/ :
    candidates.json       les 9 emplacements candidats (vraies coordonnées Lyon)
    demand_zones.geojson  la grille de demande pondérée
    inaccessible.geojson  le Rhône, la Saône et l'emprise ferroviaire de Perrache

Ce script n'est PAS exécuté au démarrage de l'application : ses sorties sont
committées dans le dépôt. Il est fourni pour que l'instance soit auditable et
reproductible — on peut vérifier d'où sort chaque zone de demande.

    python scripts/generate_instance.py

Aucune dépendance réseau, aucune clé d'API. Tout est calculé localement.
"""

from __future__ import annotations

import json
from math import asin, cos, exp, radians, sin, sqrt
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EARTH_RADIUS_M = 6_371_000.0

# --------------------------------------------------------------------------
# 1. La zone d'étude : la Presqu'île de Lyon et ses deux rives
# --------------------------------------------------------------------------
# Du nord des pentes de la Croix-Rousse (Sathonay) jusqu'à Perrache au sud,
# et de la rive droite de la Saône à la rive gauche du Rhône (Guillotière).
# ~2,9 km nord-sud × ~2,0 km est-ouest, soit environ 5,8 km².

BBOX = {
    "lat_min": 45.7460,
    "lat_max": 45.7720,
    "lon_min": 4.8220,
    "lon_max": 4.8480,
}

# --------------------------------------------------------------------------
# 2. Les 9 emplacements candidats
# --------------------------------------------------------------------------
# Tous sont de vraies places ou de vrais pôles d'échange lyonnais, avec leurs
# coordonnées réelles. Ils sont choisis pour former une structure intéressante :
# certains se recouvrent partiellement à 300 m (les grappes), d'autres sont
# isolés. C'est ce recouvrement partiel qui rend le problème non trivial —
# voir explanation.md §11 piège P8.

CANDIDATES = [
    # --- INSTANCE DE RÉFÉRENCE (N = 9) ------------------------------------
    # Trois candidats par rive. Ce n'est pas un détail cosmétique : avec des
    # candidats massés sur la Presqu'île, un budget de 3 bornes n'avait plus
    # de choix géographique réel à faire, et la carte donnait l'impression que
    # les deux rives n'existaient pas. La demande, elle, est répartie
    # 30 % / 46 % / 24 % entre rive droite, Presqu'île et rive gauche.
    #
    # Toutes les coordonnées sont relevées sur OpenStreetMap.
    {"id": 0, "name": "Place Bellecour",          "lat": 45.7577, "lon": 4.8320},
    {"id": 1, "name": "Place des Terreaux",       "lat": 45.7674, "lon": 4.8336},
    {"id": 2, "name": "Place Beauregard",         "lat": 45.7578, "lon": 4.8233},
    {"id": 3, "name": "Gare de Perrache",         "lat": 45.7496, "lon": 4.8262},
    {"id": 4, "name": "Place Saint-Paul",         "lat": 45.7660, "lon": 4.8274},
    {"id": 5, "name": "Place Gabriel Péri",       "lat": 45.7558, "lon": 4.8434},
    {"id": 6, "name": "Vieux Lyon — Saint-Jean",  "lat": 45.7605, "lon": 4.8271},
    {"id": 7, "name": "Place Maréchal Lyautey",   "lat": 45.7689, "lon": 4.8411},
    {"id": 8, "name": "Quai Victor Augagneur",    "lat": 45.7624, "lon": 4.8413},
    # --- Au-delà de l'instance de référence -------------------------------
    # Les neuf premiers candidats constituent l'INSTANCE DE RÉFÉRENCE
    # documentée (N = 9). Les suivants ne servent que lorsque l'utilisateur
    # augmente N depuis l'interface : ils permettent d'observer la croissance
    # combinatoire sur de vraies données, et surtout d'atteindre le plafond
    # du simulateur pour voir la dégradation gracieuse de QAOA (sujet §VII.4).
    # Ce sont eux aussi de vrais lieux lyonnais.
    {"id": 9,  "name": "Place des Cordeliers",    "lat": 45.7639, "lon": 4.8362},
    {"id": 10, "name": "Place des Jacobins",      "lat": 45.7615, "lon": 4.8339},
    {"id": 11, "name": "Place Sathonay",          "lat": 45.7690, "lon": 4.8320},
    {"id": 12, "name": "Place des Célestins",     "lat": 45.7598, "lon": 4.8318},
    {"id": 13, "name": "Place Saint-Nizier",      "lat": 45.7647, "lon": 4.8331},
    {"id": 14, "name": "Place Louis Pradel",      "lat": 45.7684, "lon": 4.8367},
    {"id": 15, "name": "Place Antonin Jutard",    "lat": 45.7566, "lon": 4.8409},
    {"id": 16, "name": "Place Guichard",          "lat": 45.7588, "lon": 4.8465},
    {"id": 17, "name": "Quai Général Sarrail",    "lat": 45.7640, "lon": 4.8414},
    {"id": 18, "name": "Place du Change",         "lat": 45.7645, "lon": 4.8283},
    {"id": 19, "name": "Place Raspail",           "lat": 45.7558, "lon": 4.8404},
]

# --------------------------------------------------------------------------
# 3. Les pôles générateurs de demande
# --------------------------------------------------------------------------
# La demande en recharge n'est pas uniforme : elle se concentre autour des
# pôles d'activité (gares, places commerçantes, quartiers denses). On modélise
# chaque pôle par une gaussienne d'intensité décroissante, et le poids d'une
# cellule est la somme des contributions.
#
# `intensity` est une pondération relative sans unité, calibrée à la main sur
# la fréquentation observable de chaque pôle. C'est un choix de modélisation
# assumé, pas une donnée officielle : il est documenté dans le README.

DEMAND_POLES = [
    {"name": "Bellecour",          "lat": 45.7578, "lon": 4.8321, "intensity": 1.00},
    {"name": "Hôtel de Ville",     "lat": 45.7676, "lon": 4.8345, "intensity": 0.95},
    {"name": "Cordeliers",         "lat": 45.7639, "lon": 4.8362, "intensity": 0.90},
    {"name": "Perrache",           "lat": 45.7496, "lon": 4.8262, "intensity": 0.85},
    {"name": "Guillotière",        "lat": 45.7541, "lon": 4.8431, "intensity": 0.80},
    {"name": "Jacobins",           "lat": 45.7615, "lon": 4.8339, "intensity": 0.75},
    {"name": "Vieux Lyon",         "lat": 45.7609, "lon": 4.8274, "intensity": 0.70},
    {"name": "Opéra / République", "lat": 45.7680, "lon": 4.8375, "intensity": 0.70},
    {"name": "Ainay",              "lat": 45.7540, "lon": 4.8295, "intensity": 0.60},
    {"name": "Sathonay",           "lat": 45.7692, "lon": 4.8318, "intensity": 0.55},
    {"name": "Quais du Rhône",     "lat": 45.7590, "lon": 4.8415, "intensity": 0.50},
]

SIGMA_M = 350.0          # portée de la décroissance gaussienne, en mètres
GRID_STEP_M = 180.0      # taille d'une cellule de la grille de demande
WEIGHT_THRESHOLD = 0.20  # en dessous, la demande est trop diffuse pour une infrastructure

# --------------------------------------------------------------------------
# 4. Les zones inaccessibles
# --------------------------------------------------------------------------
# On ne construit pas une borne dans un fleuve, et personne n'habite dans
# l'eau : une zone de demande dont le centre tombe dans un de ces polygones
# est retirée du problème. Voir explanation.md §2.4.
#
# Les fleuves sont décrits par leur axe, puis épaissis en polygone.

# Les emprises du Rhône et de la Saône sont les POLYGONES RÉELS, relevés sur
# OpenStreetMap (relations 7317123 « La Saône » et 660056 « Le Rhône »), puis
# découpés sur la zone d'étude et simplifiés par Douglas-Peucker à ~9 m près.
#
# Ils sont figés ici sous forme de littéraux : le script reste hors-ligne et
# déterministe, et le dépôt n'acquiert aucune dépendance réseau.
#
# Pourquoi ne pas garder un axe épaissi à largeur constante, comme avant ? Parce
# qu'un ruban droit ne peut pas représenter le coude de la Saône, qui s'écarte
# vers l'ouest en descendant sur Perrache puis quitte la zone au nord de
# Saint-Paul. L'ancienne approximation plaçait la Saône jusqu'à 350 m de sa
# position réelle, et le Rhône 180 m trop à l'ouest.
#
# Simplifier ne change rien au problème : on a vérifié que les 129 cellules de
# la grille reçoivent exactement le même classement accessible / inaccessible
# avec le polygone complet (1300 points) et avec sa version simplifiée.

SAONE_POLYGON = [
    (45.76756, 4.81956), (45.76812, 4.82265), (45.76831, 4.82525),
    (45.76822, 4.82660), (45.76789, 4.82783), (45.76678, 4.82982),
    (45.76561, 4.83092), (45.76512, 4.83122), (45.76314, 4.83133),
    (45.76231, 4.83122), (45.76071, 4.83062), (45.75905, 4.82918),
    (45.75632, 4.82620), (45.75458, 4.82544), (45.75302, 4.82456),
    (45.75139, 4.82303), (45.75131, 4.82320), (45.74880, 4.81950),
    (45.75039, 4.81950), (45.75148, 4.82170), (45.75326, 4.82340),
    (45.75600, 4.82464), (45.75698, 4.82541), (45.75949, 4.82793),
    (45.76054, 4.82854), (45.76057, 4.82871), (45.76219, 4.82944),
    (45.76349, 4.82966), (45.76530, 4.82940), (45.76617, 4.82903),
    (45.76641, 4.82885), (45.76720, 4.82767), (45.76756, 4.82636),
    (45.76753, 4.82376), (45.76743, 4.82265), (45.76679, 4.82014),
    (45.76674, 4.81950), (45.76755, 4.81950), (45.76756, 4.81956),
]

RHONE_POLYGON = [
    (45.77424, 4.84161), (45.77255, 4.84060), (45.76947, 4.84046),
    (45.76539, 4.84092), (45.76389, 4.84085), (45.75843, 4.84012),
    (45.75636, 4.83930), (45.75228, 4.83648), (45.74578, 4.83143),
    (45.74454, 4.82997), (45.74350, 4.82908), (45.74350, 4.82654),
    (45.74724, 4.82974), (45.74880, 4.83124), (45.74904, 4.83131),
    (45.75436, 4.83506), (45.75559, 4.83598), (45.75563, 4.83620),
    (45.75604, 4.83650), (45.75618, 4.83643), (45.75728, 4.83723),
    (45.75936, 4.83797), (45.76278, 4.83868), (45.76534, 4.83855),
    (45.76539, 4.83864), (45.76730, 4.83842), (45.76928, 4.83836),
    (45.77135, 4.83839), (45.77152, 4.83851), (45.77348, 4.83868),
    (45.77450, 4.83933), (45.77445, 4.84172), (45.77424, 4.84161),
]

PERRACHE_RAILYARD = [
    (45.7512, 4.8238), (45.7512, 4.8336), (45.7484, 4.8340),
    (45.7478, 4.8300), (45.7480, 4.8240),
]


# --------------------------------------------------------------------------
# Outils géométriques
# --------------------------------------------------------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique en mètres. Voir explanation.md §2.2."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def meters_to_deg_lat(m: float) -> float:
    """1 degré de latitude vaut ~111 320 m partout sur le globe."""
    return m / 111_320.0


def meters_to_deg_lon(m: float, at_lat: float) -> float:
    """1 degré de longitude rétrécit avec le cosinus de la latitude.
    À Lyon (45,76 °N) il ne vaut plus que ~77 700 m."""
    return m / (111_320.0 * cos(radians(at_lat)))


def point_in_polygon(lat: float, lon: float, polygon) -> bool:
    """Ray casting. Voir explanation.md §2.4."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if (lon_i > lon) != (lon_j > lon):
            lat_cross = lat_i + (lon - lon_i) / (lon_j - lon_i) * (lat_j - lat_i)
            if lat < lat_cross:
                inside = not inside
        j = i
    return inside


# --------------------------------------------------------------------------
# Génération
# --------------------------------------------------------------------------

def build_inaccessible_polygons():
    return [
        {"name": "La Saône", "kind": "water", "polygon": SAONE_POLYGON},
        {"name": "Le Rhône", "kind": "water", "polygon": RHONE_POLYGON},
        {"name": "Emprise ferroviaire de Perrache", "kind": "infrastructure",
         "polygon": PERRACHE_RAILYARD},
    ]


def build_demand_zones(inaccessible):
    """Grille régulière sur la bbox, pondérée par proximité aux pôles.

    Chaque cellule reçoit deux poids :
      weight_uniform = 1.0   (le mode par défaut du sujet)
      weight_density = somme gaussienne des pôles, normalisée sur [0, 1]

    Les cellules trop faibles (personne n'y habite) sont écartées, ainsi que
    celles dont le centre tombe dans un polygone inaccessible.
    """
    mid_lat = (BBOX["lat_min"] + BBOX["lat_max"]) / 2
    step_lat = meters_to_deg_lat(GRID_STEP_M)
    step_lon = meters_to_deg_lon(GRID_STEP_M, mid_lat)

    raw = []
    lat = BBOX["lat_min"] + step_lat / 2
    while lat < BBOX["lat_max"]:
        lon = BBOX["lon_min"] + step_lon / 2
        while lon < BBOX["lon_max"]:
            density = 0.0
            for pole in DEMAND_POLES:
                d = haversine(lat, lon, pole["lat"], pole["lon"])
                density += pole["intensity"] * exp(-(d * d) / (2 * SIGMA_M * SIGMA_M))
            raw.append({"lat": lat, "lon": lon, "density": density})
            lon += step_lon
        lat += step_lat

    max_density = max(c["density"] for c in raw)

    zones = []
    for cell in raw:
        normalized = cell["density"] / max_density
        if normalized < WEIGHT_THRESHOLD:
            continue  # pas de demande ici : on ne crée pas de zone
        blocked = next(
            (z["name"] for z in inaccessible
             if point_in_polygon(cell["lat"], cell["lon"], z["polygon"])),
            None,
        )
        zones.append({
            "id": len(zones),
            "lat": round(cell["lat"], 6),
            "lon": round(cell["lon"], 6),
            "weight_uniform": 1.0,
            "weight_density": round(normalized, 4),
            "inaccessible": blocked is not None,
            "blocked_by": blocked,
        })
    return zones


def zones_to_geojson(zones):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [z["lon"], z["lat"]]},
                "properties": {
                    "id": z["id"],
                    "weight_uniform": z["weight_uniform"],
                    "weight_density": z["weight_density"],
                    "inaccessible": z["inaccessible"],
                    "blocked_by": z["blocked_by"],
                },
            }
            for z in zones
        ],
    }


def inaccessible_to_geojson(inaccessible):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    # GeoJSON veut [lon, lat] et un anneau fermé
                    "coordinates": [[[lon, lat] for lat, lon in z["polygon"]]
                                    + [[z["polygon"][0][1], z["polygon"][0][0]]]],
                },
                "properties": {"name": z["name"], "kind": z["kind"]},
            }
            for z in inaccessible
        ],
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    inaccessible = build_inaccessible_polygons()
    zones = build_demand_zones(inaccessible)

    reference_n = 9   # taille de l'instance de référence documentée

    candidates_doc = {
        "area": {
            "name": "Lyon — Presqu'île et ses rives",
            "city": "Lyon, France",
            "bbox": BBOX,
            "center": {
                "lat": (BBOX["lat_min"] + BBOX["lat_max"]) / 2,
                "lon": (BBOX["lon_min"] + BBOX["lon_max"]) / 2,
            },
            "default_zoom": 14,
        },
        "defaults": {"budget": 3, "radius_m": 300, "weight_mode": "uniform",
                     "respect_inaccessible": True, "n_candidates": reference_n},
        "candidates": CANDIDATES,
        "demand_poles": DEMAND_POLES,
    }

    (DATA_DIR / "candidates.json").write_text(
        json.dumps(candidates_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA_DIR / "demand_zones.geojson").write_text(
        json.dumps(zones_to_geojson(zones), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    (DATA_DIR / "inaccessible.geojson").write_text(
        json.dumps(inaccessible_to_geojson(inaccessible), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")

    blocked = sum(1 for z in zones if z["inaccessible"])
    print(f"candidats           : {len(CANDIDATES)}  (instance de référence : {reference_n})")
    print(f"zones de demande    : {len(zones)}")
    print(f"  dont inaccessibles: {blocked}  (retirées quand le toggle est actif)")
    print(f"  soit actives      : {len(zones) - blocked}")
    print(f"polygones bloquants : {len(inaccessible)}")


if __name__ == "__main__":
    main()
