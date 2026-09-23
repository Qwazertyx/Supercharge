"""
L'API et la cohérence de bout en bout.

Le test qui compte le plus ici est celui de la COHÉRENCE : les chiffres
renvoyés au frontend doivent raconter exactement la même histoire que la
carte. Le sujet prévient : « Numbers that contradict the map will be caught. »
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

RAPIDE = {"run_annealing": False, "record_trace": False}


@pytest.fixture(scope="module")
def reponse():
    r = client.post("/api/solve", json=dict(RAPIDE))
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------
# Routes de base
# --------------------------------------------------------------------------

def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_le_frontend_est_servi():
    r = client.get("/")
    assert r.status_code == 200
    assert "Supercharge" in r.text


@pytest.mark.parametrize("chemin", [
    "/css/style.css", "/js/app.js", "/js/maps.js", "/js/charts.js",
    "/js/panels.js", "/js/api.js",
    "/vendor/leaflet.js", "/vendor/leaflet.css", "/vendor/chart.umd.js",
])
def test_toutes_les_ressources_du_frontend_sont_servies(chemin):
    """Les bibliothèques sont versionnées dans le dépôt : l'application doit
    se charger même si aucun CDN n'est joignable."""
    assert client.get(chemin).status_code == 200


# --------------------------------------------------------------------------
# L'instance de référence
# --------------------------------------------------------------------------

def test_linstance_de_reference_correspond_au_readme():
    d = client.get("/api/instance").json()
    assert d["defaults"] == {
        "budget": 3, "radius_m": 300, "weight_mode": "uniform",
        "respect_inaccessible": True, "n_candidates": 9,
    }
    assert d["area"]["city"] == "Lyon, France"
    assert len(d["candidates"]) == 20        # emplacements disponibles
    assert d["limits"]["max_candidates"] == 20


def test_les_candidats_sont_dans_la_zone_detude():
    d = client.get("/api/instance").json()
    bbox = d["area"]["bbox"]
    for c in d["candidates"]:
        assert bbox["lat_min"] <= c["lat"] <= bbox["lat_max"], c["name"]
        assert bbox["lon_min"] <= c["lon"] <= bbox["lon_max"], c["name"]


def test_les_identifiants_de_candidats_sont_denses():
    d = client.get("/api/instance").json()
    assert [c["id"] for c in d["candidates"]] == list(range(len(d["candidates"])))


# --------------------------------------------------------------------------
# Cohérence des chiffres renvoyés
# --------------------------------------------------------------------------

def test_les_defauts_de_lapi_sont_ceux_de_linstance_de_reference(reponse):
    p = reponse["params"]
    assert (p["budget"], p["radius_m"], p["weight_mode"]) == (3, 300.0, "uniform")
    assert p["n_candidates"] == 9
    assert p["penalty_is_auto"]


def test_les_trois_solveurs_couvrent_ce_quils_annoncent(reponse):
    """couverture = poids couvert / poids total, et zones couvertes +
    non couvertes = toutes les zones. Aucune de ces égalités ne peut être
    fausse sans que la carte mente."""
    total = reponse["instance"]["total_weight"]
    n_zones = reponse["instance"]["n_zones"]

    for nom in ("classical", "quantum"):
        s = reponse["solvers"][nom]
        if s["skipped"]:
            continue
        assert s["coverage_ratio"] == pytest.approx(s["covered_weight"] / total)
        assert len(s["covered_zones"]) + len(s["uncovered_zones"]) == n_zones
        assert not set(s["covered_zones"]) & set(s["uncovered_zones"])
        assert s["stations_used"] == len(s["selection"])
        assert s["stations_used"] <= reponse["params"]["budget"]


def test_le_tableau_de_metriques_reprend_les_valeurs_des_solveurs(reponse):
    """Le panneau ne recalcule rien : il doit refléter exactement les
    solveurs. Ce test empêche qu'une divergence s'installe."""
    metrics = {m["key"]: m for m in reponse["comparison"]["metrics"]}
    classique = reponse["solvers"]["classical"]
    quantique = reponse["solvers"]["quantum"]

    assert metrics["coverage"]["classical"] == pytest.approx(
        classique["coverage_ratio"] * 100)
    assert metrics["stations"]["classical"] == classique["stations_used"]
    assert metrics["uncovered"]["classical"] == len(classique["uncovered_zones"])
    assert metrics["work"]["classical"] == classique["combinations_evaluated"]

    if not quantique["skipped"]:
        assert metrics["coverage"]["quantum"] == pytest.approx(
            quantique["coverage_ratio"] * 100)
        assert metrics["work"]["quantum"] == quantique["iterations"]


def test_le_diff_est_coherent_avec_les_deux_selections(reponse):
    diff = reponse["comparison"]["diff"]
    c = set(reponse["solvers"]["classical"]["selection"])
    q = set(reponse["solvers"]["quantum"]["selection"])
    assert set(diff["shared_stations"]) == c & q
    assert set(diff["only_classical_stations"]) == c - q
    assert set(diff["only_quantum_stations"]) == q - c
    assert diff["identical_placement"] == (c == q)


def test_la_force_brute_reste_la_reference(reponse):
    """QAOA ne peut pas dépasser une méthode exacte."""
    c = reponse["solvers"]["classical"]
    q = reponse["solvers"]["quantum"]
    if not q["skipped"]:
        assert q["covered_weight"] <= c["covered_weight"] + 1e-9


def test_le_verdict_ne_revendique_pas_une_victoire_quantique(reponse):
    """Exigence explicite du sujet : « do not claim a quantum "win" that the
    numbers do not show »."""
    v = reponse["comparison"]["verdict"]
    assert v["winner"] == "classical"
    assert "CLASSIQUE" in v["headline"]
    assert "ASYMPTOTIQUE" in v["detail"]


def test_le_diagnostic_du_qubo_est_expose(reponse):
    q = reponse["qubo"]
    assert q["penalty"] > q["penalty_lower_bound"]
    assert q["penalty_is_safe"]
    assert q["fidelity"]["exact"]
    assert q["fidelity"]["max_multiplicity"] == 2


# --------------------------------------------------------------------------
# Les paramètres atteignent réellement les solveurs
# --------------------------------------------------------------------------

@pytest.mark.parametrize("champ,valeur", [
    ("budget", 5),
    ("radius_m", 600.0),
    ("weight_mode", "density"),
    ("respect_inaccessible", False),
])
def test_changer_un_parametre_change_le_resultat(champ, valeur, reponse):
    """Vérifié pendant l'évaluation : « A parameter changed in the UI must
    change the result of both solvers accordingly »."""
    r = client.post("/api/solve", json={**RAPIDE, champ: valeur}).json()
    assert r["params"][champ if champ != "respect_inaccessible" else champ] == valeur
    avant = reponse["solvers"]["classical"]
    apres = r["solvers"]["classical"]
    assert (apres["coverage_ratio"] != pytest.approx(avant["coverage_ratio"])
            or apres["selection"] != avant["selection"]), f"{champ} n'a rien changé"


def test_une_penalite_trop_faible_est_signalee():
    """Le tirage brut du circuit doit révéler la violation de budget plutôt
    que de la masquer derrière un filtrage silencieux."""
    r = client.post("/api/solve", json={**RAPIDE, "penalty": 0.5}).json()
    assert not r["qubo"]["penalty_is_safe"]
    q = r["solvers"]["quantum"]
    assert q["budget_violated_in_raw"]
    assert q["raw_stations"] > r["params"]["budget"]
    # la solution AFFICHÉE reste faisable : on montre le problème sans
    # produire un placement invalide sur la carte
    assert q["stations_used"] <= r["params"]["budget"]


def test_au_dela_du_plafond_lapi_repond_quand_meme():
    """Pas d'erreur 500, pas de gel : une réponse 200 avec un motif clair."""
    r = client.post("/api/solve", json={**RAPIDE, "n_candidates": 18})
    assert r.status_code == 200
    d = r.json()
    assert d["solvers"]["quantum"]["skipped"]
    assert "plafond" in d["solvers"]["quantum"]["reason"].lower()
    assert not d["solvers"]["classical"]["skipped"]
    assert d["comparison"]["agreement"]["code"] == "skipped"


# --------------------------------------------------------------------------
# Validation des entrées
# --------------------------------------------------------------------------

@pytest.mark.parametrize("charge", [
    {"budget": -1},
    {"radius_m": 0},
    {"radius_m": 99_999},
    {"weight_mode": "inexistant"},
    {"layers": 0},
    {"layers": 99},
    {"shots": 1},
    {"penalty": -5},
    {"n_candidates": 0},
])
def test_les_parametres_invalides_sont_refuses(charge):
    """Les bornes sont posées une seule fois, dans les schémas Pydantic.
    Les solveurs peuvent donc supposer leurs entrées saines."""
    assert client.post("/api/solve", json={**RAPIDE, **charge}).status_code == 422


def test_un_budget_superieur_au_nombre_de_candidats_est_ramene():
    r = client.post("/api/solve", json={**RAPIDE, "budget": 15, "n_candidates": 6}).json()
    assert r["params"]["budget"] == 6


# --------------------------------------------------------------------------
# Courbe de complexité
# --------------------------------------------------------------------------

def test_les_quatre_courbes_sont_presentes():
    d = client.post("/api/complexity", json={"n_max": 30}).json()
    cles = {s["key"] for s in d["series"]}
    assert cles == {"search_space", "brute_force", "qaoa_circuit", "qaoa_simulation"}


def test_lespace_de_recherche_double_a_chaque_candidat():
    d = client.post("/api/complexity", json={"n_max": 20}).json()
    points = {p["n"]: p for p in d["points"]}
    for n in range(3, 20):
        assert points[n]["search_space"] == pytest.approx(2 * points[n - 1]["search_space"])


def test_le_circuit_qaoa_croit_de_facon_polynomiale():
    """L'argument central du projet, sous forme de test : quand N est
    multiplié par 4, un coût quadratique croît d'environ ×16, alors que
    l'espace de recherche est multiplié par 2^(3N/4)."""
    d = client.post("/api/complexity", json={"n_max": 40}).json()
    points = {p["n"]: p for p in d["points"]}
    ratio_circuit = points[40]["qaoa_circuit"] / points[10]["qaoa_circuit"]
    ratio_espace = points[40]["search_space"] / points[10]["search_space"]
    assert ratio_circuit < 30           # ~16, polynomial
    assert ratio_espace > 1e8           # 2^30, exponentiel


def test_le_mode_budget_proportionnel_rend_la_force_brute_exponentielle():
    """À B fixé, Σₖ≤B C(N,k) est polynomial. À B = N/2, il redevient
    exponentiel : c'est le régime des déploiements réels."""
    fixe = client.post("/api/complexity",
                       json={"n_max": 40, "budget": 3}).json()["points"]
    variable = client.post("/api/complexity",
                           json={"n_max": 40, "budget_scales_with_n": True}).json()["points"]
    f = {p["n"]: p["brute_force"] for p in fixe}
    v = {p["n"]: p["brute_force"] for p in variable}
    assert v[40] > f[40] * 1e6


def test_les_durees_lisibles_sont_calculees():
    d = client.post("/api/complexity", json={"n_max": 80}).json()
    points = {p["n"]: p for p in d["points"]}
    assert "µs" in points[10]["search_space_duration"] or "ms" in points[10]["search_space_duration"]
    assert "ann" in points[80]["search_space_duration"]   # années / milliards d'années
