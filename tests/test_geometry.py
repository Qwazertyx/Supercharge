"""Géométrie : distances réelles et construction de la couverture."""

from __future__ import annotations

import math

import pytest

from backend.geometry import (
    build_coverage,
    haversine,
    indices_to_mask,
    mask_to_indices,
    point_in_polygon,
)
from backend.instance import load_static_data


# --------------------------------------------------------------------------
# Haversine
# --------------------------------------------------------------------------

def test_haversine_distance_nulle():
    assert haversine(45.7578, 4.8320, 45.7578, 4.8320) == pytest.approx(0.0, abs=1e-9)


def test_haversine_symetrique():
    a = haversine(45.7578, 4.8321, 45.7674, 4.8336)
    b = haversine(45.7674, 4.8336, 45.7578, 4.8321)
    assert a == pytest.approx(b, rel=1e-12)


def test_un_degre_de_latitude_vaut_environ_111_km():
    d = haversine(45.0, 4.8, 46.0, 4.8)
    assert d == pytest.approx(111_195, rel=0.002)


def test_un_degre_de_longitude_retrecit_avec_la_latitude():
    """C'est précisément l'erreur qu'une distance euclidienne commettrait.

    À la latitude de Lyon, un degré de longitude vaut ~cos(45,76°) ≈ 0,70 fois
    un degré de latitude. Utiliser une distance euclidienne sur des degrés
    surestimerait les distances est-ouest de plus de 40 %.
    """
    lat = 45.76
    d_lon = haversine(lat, 4.8, lat, 5.8)
    d_lat = haversine(45.0, 4.8, 46.0, 4.8)
    assert d_lon / d_lat == pytest.approx(math.cos(math.radians(lat)), rel=0.005)


def test_distance_bellecour_terreaux_conforme_au_terrain():
    """Bellecour → Terreaux : environ 1,05 km à vol d'oiseau dans Lyon."""
    d = haversine(45.7578, 4.8321, 45.7674, 4.8336)
    assert 1000 < d < 1150


# --------------------------------------------------------------------------
# Masques de bits
# --------------------------------------------------------------------------

@pytest.mark.parametrize("indices", [[], [0], [0, 2], [1, 3, 5], [0, 1, 2, 3, 4, 5, 6, 7, 8]])
def test_aller_retour_masque_indices(indices):
    assert mask_to_indices(indices_to_mask(indices), 9) == sorted(indices)


def test_le_masque_encode_bien_la_position_des_bits():
    assert indices_to_mask([0, 2]) == 0b101
    assert indices_to_mask([3]) == 0b1000


# --------------------------------------------------------------------------
# Point dans polygone
# --------------------------------------------------------------------------

CARRE = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]


@pytest.mark.parametrize("lat,lon,attendu", [
    (0.5, 0.5, True),     # centre
    (0.1, 0.9, True),     # près d'un coin, dedans
    (1.5, 0.5, False),    # au nord
    (-0.5, 0.5, False),   # au sud
    (0.5, 1.5, False),    # à l'est
    (0.5, -0.5, False),   # à l'ouest
])
def test_point_dans_polygone(lat, lon, attendu):
    assert point_in_polygon(lat, lon, CARRE) is attendu


# --------------------------------------------------------------------------
# Matrice de couverture
# --------------------------------------------------------------------------

def test_la_couverture_est_coherente_dans_les_deux_sens():
    """covering_sets et covered_by décrivent la même relation, transposée.

    Si ces deux vues divergeaient, un solveur et l'affichage pourraient
    travailler sur des couvertures différentes.
    """
    static = load_static_data()
    covering, masks, covered_by = build_coverage(static.candidates, static.zones, 300.0)

    for j, cj in enumerate(covering):
        for i in cj:
            assert j in covered_by[i], f"zone {j} dans C_{i} mais pas l'inverse"
    for i, zones in enumerate(covered_by):
        for j in zones:
            assert i in covering[j]


def test_le_masque_correspond_exactement_a_lensemble():
    static = load_static_data()
    covering, masks, _ = build_coverage(static.candidates, static.zones, 300.0)
    for cj, mask in zip(covering, masks):
        assert mask_to_indices(mask, len(static.candidates)) == sorted(cj)


def test_un_rayon_plus_grand_ne_peut_que_couvrir_davantage():
    """La couverture est monotone en r : c'est ce qui rend le curseur sensé."""
    static = load_static_data()
    petit, _, _ = build_coverage(static.candidates, static.zones, 200.0)
    grand, _, _ = build_coverage(static.candidates, static.zones, 400.0)
    for a, b in zip(petit, grand):
        assert a.issubset(b)


def test_un_rayon_enorme_couvre_tout():
    static = load_static_data()
    covering, _, _ = build_coverage(static.candidates, static.zones, 50_000.0)
    n = len(static.candidates)
    assert all(len(cj) == n for cj in covering)
