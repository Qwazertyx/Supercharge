"""
Primitives géométriques.

Tout le projet repose sur une seule question : « ce candidat couvre-t-il cette
zone ? ». Ce module y répond, et rien d'autre.

Voir explanation.md §2.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000.0

Polygon = list[tuple[float, float]]  # liste de (lat, lon)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique, en mètres, entre deux points GPS.

    On ne peut PAS utiliser une distance euclidienne sur des degrés : à Lyon
    (45,76 °N) un degré de longitude vaut ~77,7 km contre ~111,3 km pour un
    degré de latitude. Une distance euclidienne se tromperait de ~43 %.

    Haversine modélise la Terre comme une sphère. L'erreur résiduelle face à
    un modèle ellipsoïdal (Vincenty) est de l'ordre du mètre sur quelques
    kilomètres — négligeable devant un rayon de couverture de 300 m.
    """
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def point_in_polygon(lat: float, lon: float, polygon: Polygon) -> bool:
    """Test point-dans-polygone par lancer de rayon (ray casting).

    On lance un rayon depuis le point et on compte combien de côtés du
    polygone il traverse. Nombre impair → le point est dedans, nombre pair →
    il est dehors. C'est le théorème de la courbe de Jordan.
    """
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


def build_coverage(candidates, zones, radius_m: float):
    """Calcule la structure de couverture du problème.

    C'est LA précomputation centrale. Elle ne dépend que de la géométrie et du
    rayon — jamais d'une solution. On la calcule donc une seule fois par jeu de
    paramètres, et les trois solveurs la réutilisent telle quelle.

    Retourne un triplet :
        covering_sets  list[set[int]]  covering_sets[j] = Cⱼ, les candidats
                                       capables de couvrir la zone j
        zone_masks     list[int]       le même Cⱼ encodé en masque de bits
        covered_by     list[set[int]]  covered_by[i] = les zones que le
                                       candidat i peut couvrir

    Le masque de bits est une optimisation décisive pour la force brute : au
    lieu de parcourir un ensemble, tester « la zone j est-elle couverte par la
    sélection S ? » devient un simple ET binaire, une instruction machine.

        Cⱼ = {0, 2}   →   0b101 = 5
        S  = {0, 2}   →   0b101 = 5
        couverte ?    →   (S & Cⱼ) != 0
    """
    covering_sets: list[set[int]] = []
    zone_masks: list[int] = []
    covered_by: list[set[int]] = [set() for _ in candidates]

    for j, zone in enumerate(zones):
        cj: set[int] = set()
        mask = 0
        for i, cand in enumerate(candidates):
            if haversine(cand.lat, cand.lon, zone.lat, zone.lon) <= radius_m:
                cj.add(i)
                mask |= 1 << i
                covered_by[i].add(j)
        covering_sets.append(cj)
        zone_masks.append(mask)

    return covering_sets, zone_masks, covered_by


def mask_to_indices(mask: int, n: int) -> list[int]:
    """Convertit un masque de bits en liste d'indices triée."""
    return [i for i in range(n) if mask >> i & 1]


def indices_to_mask(indices) -> int:
    """Convertit un itérable d'indices en masque de bits."""
    mask = 0
    for i in indices:
        mask |= 1 << i
    return mask
