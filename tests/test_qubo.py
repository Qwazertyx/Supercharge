"""
Le QUBO et sa traduction en Hamiltonien de Ising.

C'est la partie du projet que le sujet demande explicitement de comprendre
plutôt que de recopier. Ces tests en constituent la preuve exécutable :

  • la transformation QUBO → Ising est exacte sur les 2^N états, pas « à peu
    près » ni « sur quelques cas » ;
  • l'état fondamental du QUBO est bien l'optimum du vrai problème ;
  • la borne théorique sur le poids de pénalité est la bonne, et la franchir
    produit exactement la défaillance annoncée ;
  • le diagnostic de fidélité dit vrai.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.instance import build_instance
from backend.objective import evaluate
from backend.qubo import (
    build_qubo,
    ising_energy,
    marginal_gains,
    qubo_fidelity,
    qubo_to_ising,
)
from backend.solvers import brute_force


@pytest.fixture(scope="module")
def reference():
    return build_instance(budget=3, radius_m=300, weight_mode="uniform", n_candidates=9)


def tous_les_etats(n: int):
    for s in range(1 << n):
        yield s, [(s >> i) & 1 for i in range(n)]


# --------------------------------------------------------------------------
# Structure de la matrice
# --------------------------------------------------------------------------

def test_la_matrice_est_triangulaire_superieure(reference):
    Q = build_qubo(reference).Q
    assert np.allclose(np.tril(Q, -1), 0.0), "aucun coefficient sous la diagonale"


def test_les_termes_de_couplage_sont_positifs(reference):
    """Qᵢₖ = Wᵢₖ + 2P, avec Wᵢₖ ≥ 0 et P > 0.

    Le signe positif est ce qui DÉCOURAGE de prendre deux candidats ensemble :
    c'est à la fois l'anti-redondance issue de la troncature au degré 2 et le
    frein budgétaire issu de la pénalité. Un couplage négatif signalerait une
    erreur de signe qui inciterait à empiler les bornes.
    """
    Q = build_qubo(reference).Q
    hors_diag = np.triu(Q, 1)
    assert (hors_diag[np.triu_indices_from(hors_diag, 1)] > 0).all()


def test_la_diagonale_est_negative_elle_recompense(reference):
    """Qᵢᵢ = −Wᵢ + P(1−2B). Avec B ≥ 1, les deux termes tirent vers le bas :
    construire doit faire BAISSER l'énergie."""
    Q = build_qubo(reference).Q
    assert (np.diag(Q) < 0).all()


def test_les_gains_marginaux_correspondent_a_la_geometrie(reference):
    """Wᵢ doit égaler le poids réellement couvert par le candidat i seul."""
    W = marginal_gains(reference)
    for i in range(reference.n_candidates):
        assert W[i] == pytest.approx(evaluate([i], reference).covered_weight)


# --------------------------------------------------------------------------
# Énergies
# --------------------------------------------------------------------------

def test_la_version_vectorisee_egale_la_version_scalaire(reference):
    qubo = build_qubo(reference)
    toutes = qubo.all_energies()
    for s, x in tous_les_etats(qubo.n):
        assert toutes[s] == pytest.approx(qubo.energy(x), abs=1e-9)


def test_qubo_et_ising_donnent_la_meme_energie_sur_tous_les_etats(reference):
    """LA preuve que le pont classique → quantique est correct.

    On ne teste pas quelques cas : on teste les 512. Si ce test passe, la
    transformation xᵢ = (1 − zᵢ)/2 et les formules de hᵢ, Jᵢₖ et de l'offset
    sont démontrées sans trou.
    """
    qubo = build_qubo(reference)
    ising = qubo_to_ising(qubo)
    for _s, x in tous_les_etats(qubo.n):
        assert ising_energy(ising, x) == pytest.approx(qubo.energy(x), abs=1e-9)


@pytest.mark.parametrize("budget,radius,mode", [
    (1, 200.0, "uniform"), (2, 300.0, "density"),
    (4, 450.0, "uniform"), (5, 600.0, "density"),
])
def test_lequivalence_qubo_ising_tient_sur_dautres_parametres(budget, radius, mode):
    inst = build_instance(budget=budget, radius_m=radius, weight_mode=mode, n_candidates=8)
    qubo = build_qubo(inst)
    ising = qubo_to_ising(qubo)
    for _s, x in tous_les_etats(qubo.n):
        assert ising_energy(ising, x) == pytest.approx(qubo.energy(x), abs=1e-9)


# --------------------------------------------------------------------------
# L'état fondamental est-il la bonne solution ?
# --------------------------------------------------------------------------

def test_letat_fondamental_du_qubo_est_loptimum_du_vrai_probleme(reference):
    qubo = build_qubo(reference)
    energies = qubo.all_energies()
    meilleur = int(np.argmin(energies))
    selection = [i for i in range(qubo.n) if (meilleur >> i) & 1]

    attendu = brute_force.solve(reference)
    assert len(selection) <= reference.budget, "l'état fondamental doit être faisable"
    assert evaluate(selection, reference).covered_weight == pytest.approx(
        attendu.covered_weight)


def test_tous_les_optima_degeneres_sont_au_fond_du_puits(reference):
    """Le problème admet plusieurs placements de même couverture optimale.

    Tous doivent partager la même énergie minimale : c'est ce qui explique
    que QAOA puisse renvoyer un placement différent de la force brute sans
    qu'aucun des deux n'ait tort.
    """
    qubo = build_qubo(reference)
    energies = qubo.all_energies()
    e_min = energies.min()
    optimum = brute_force.solve(reference).covered_weight

    fondamentaux = np.flatnonzero(np.isclose(energies, e_min))
    assert len(fondamentaux) >= 1
    for s in fondamentaux:
        selection = [i for i in range(qubo.n) if (int(s) >> i) & 1]
        assert evaluate(selection, reference).covered_weight == pytest.approx(optimum)


# --------------------------------------------------------------------------
# Le poids de pénalité — la question que le sujet annonce
# --------------------------------------------------------------------------

def test_la_penalite_automatique_depasse_sa_borne_theorique(reference):
    qubo = build_qubo(reference)
    assert qubo.penalty > qubo.max_marginal_gain


def test_une_penalite_suffisante_rend_letat_fondamental_faisable(reference):
    """Si P > max Wᵢ, l'optimum du QUBO respecte le budget. C'est le
    raisonnement de explanation.md §5.6, ici vérifié numériquement."""
    W = marginal_gains(reference)
    for facteur in (1.05, 1.5, 5.0, 50.0):
        qubo = build_qubo(reference, penalty=facteur * float(W.max()))
        meilleur = int(np.argmin(qubo.all_energies()))
        assert bin(meilleur).count("1") <= reference.budget, f"facteur {facteur}"


def test_une_penalite_insuffisante_rend_letat_fondamental_infaisable(reference):
    """La défaillance « P trop petit », reproduite volontairement.

    Ce test est important : il prouve que la borne max Wᵢ n'est pas une
    précaution décorative mais la frontière réelle du régime correct.
    """
    W = marginal_gains(reference)
    qubo = build_qubo(reference, penalty=0.1 * float(W.max()))
    meilleur = int(np.argmin(qubo.all_energies()))
    assert bin(meilleur).count("1") > reference.budget


def test_une_penalite_enorme_aplatit_le_paysage(reference):
    """La défaillance « P trop grand ».

    L'état fondamental reste CORRECT — c'est le point subtil. Ce qui se
    dégrade, c'est le contraste entre les états qui saturent le budget,
    rapporté à l'échelle totale des énergies. Il décroît comme 1/P, et c'est
    ce qui prive l'optimiseur classique de gradient exploitable.
    """
    W = marginal_gains(reference)
    base = float(W.max())
    contrastes = []
    for facteur in (1.1, 100.0, 10_000.0):
        qubo = build_qubo(reference, penalty=facteur * base)
        energies = qubo.all_energies()
        saturants = np.array([bin(s).count("1") == reference.budget
                              for s in range(1 << qubo.n)])
        etendue = energies[saturants].max() - energies[saturants].min()
        contrastes.append(etendue / (energies.max() - energies.min()))

    assert contrastes[0] > contrastes[1] > contrastes[2], "le contraste doit décroître"
    assert contrastes[2] < contrastes[0] / 100, "il doit s'effondrer, pas juste baisser"


# --------------------------------------------------------------------------
# Fidélité de la troncature au degré 2
# --------------------------------------------------------------------------

def test_la_troncature_est_exacte_sur_linstance_de_reference(reference):
    """À 300 m, aucune zone de la Presqu'île n'est à portée de trois
    candidats : le QUBO n'est donc pas une approximation, il est exact."""
    fid = qubo_fidelity(reference)
    assert fid.exact
    assert fid.max_multiplicity <= 2
    assert fid.zones_at_risk == 0


def test_lenergie_egale_exactement_la_couverture_quand_la_troncature_est_exacte(reference):
    """Dans le régime exact, pour tout état saturant le budget :

        énergie QUBO  =  −(poids réellement couvert)

    car la pénalité s'annule et la troncature ne perd rien. C'est la
    vérification la plus directe que l'encodage est correct.
    """
    assert qubo_fidelity(reference).exact
    qubo = build_qubo(reference)
    energies = qubo.all_energies()
    for s in range(1 << qubo.n):
        selection = [i for i in range(qubo.n) if (s >> i) & 1]
        if len(selection) != reference.budget:
            continue
        reelle = evaluate(selection, reference).covered_weight
        assert energies[s] == pytest.approx(-reelle, abs=1e-9)


def test_la_fidelite_bascule_en_approche_quand_le_rayon_augmente():
    """Au-delà de ~400 m, des zones deviennent atteignables par trois bornes.
    Le diagnostic doit le signaler au lieu de le taire."""
    large = build_instance(budget=3, radius_m=600, n_candidates=9)
    fid = qubo_fidelity(large)
    assert not fid.exact
    assert fid.max_multiplicity >= 3
    assert fid.zones_at_risk > 0


def test_la_borne_de_multiplicite_ne_depasse_jamais_le_budget():
    """s_max = maxⱼ min(|Cⱼ|, B) : on ne peut pas être couvert par plus de
    bornes qu'on n'en construit."""
    for budget in (1, 2, 3, 5):
        inst = build_instance(budget=budget, radius_m=800, n_candidates=9)
        assert qubo_fidelity(inst).max_multiplicity <= budget


# --------------------------------------------------------------------------
# Structure de l'Ising
# --------------------------------------------------------------------------

def test_le_graphe_de_couplage_est_complet(reference):
    """La pénalité P(Σxᵢ − B)² crée un terme xᵢxₖ pour CHAQUE paire, même
    entre deux candidats géographiquement sans rapport. Le graphe est donc
    complet : N(N−1)/2 couplages. C'est le prix de l'encodage de la
    contrainte, et cela vaut d'être su en soutenance."""
    ising = qubo_to_ising(build_qubo(reference))
    n = reference.n_candidates
    assert len(ising.J) == n * (n - 1) // 2


def test_les_cles_de_couplage_sont_ordonnees(reference):
    ising = qubo_to_ising(build_qubo(reference))
    assert all(i < k for (i, k) in ising.J)
