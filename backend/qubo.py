"""
Construction du QUBO et transformation en Hamiltonien de Ising.

C'est le pont entre le problème d'urbanisme et la mécanique quantique.
Le sujet est explicite : cette partie doit être comprise, pas copiée.

Voir explanation.md §5 et §6 — la dérivation complète y est faite.

───────────────────────────────────────────────────────────────────────────
RAPPEL DE LA FORMULATION

  Problème d'origine (non quadratique, contraint) :

      max  Σⱼ wⱼ · 𝟙[ Σᵢ∈Cⱼ xᵢ ≥ 1 ]     s.c.  Σᵢ xᵢ ≤ B

  Deux transformations pour atteindre la forme QUBO :

  ① LINÉARISATION DE LA COUVERTURE
     𝟙[couverte] = 1 − Πᵢ∈Cⱼ(1−xᵢ) = Σxᵢ − Σᵢ<ₖ xᵢxₖ + (degré ≥ 3)
     On tronque au degré 2 : un QUBO n'accepte pas plus, parce qu'un terme
     de degré 3 exigerait un couplage à trois corps qui n'existe pas sur le
     matériel quantique.
     → exact tant qu'au plus 2 bornes couvrent la même zone ; au-delà
       l'approximation sous-estime, donc elle PÉNALISE LA REDONDANCE.
       Le biais va dans le sens du vrai objectif.

  ② ABSORPTION DU BUDGET EN PÉNALITÉ
     f est monotone croissante ⇒ il existe toujours un optimum utilisant
     exactement B bornes ⇒ on peut remplacer « ≤ B » par « = B » sans
     perdre d'optimum, et une égalité se pénalise par un simple carré :
         P·(Σᵢ xᵢ − B)²
     Zéro variable d'écart, donc zéro qubit auxiliaire.

  QUBO final (à MINIMISER) :

      E(x) = − Σⱼ wⱼ·[Σᵢ∈Cⱼ xᵢ − Σᵢ<ₖ∈Cⱼ xᵢxₖ]  +  P·(Σᵢ xᵢ − B)²

  Coefficients, avec  Wᵢ = poids couvrable par i  et  Wᵢₖ = poids en doublon :

      Qᵢᵢ = −Wᵢ  + P(1 − 2B)          Qᵢₖ = +Wᵢₖ + 2P          c = P·B²
───────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Qubo:
    """Un QUBO sous forme matricielle triangulaire supérieure.

        E(x) = Σᵢ Q[i,i]·xᵢ  +  Σᵢ<ₖ Q[i,k]·xᵢxₖ  +  offset
    """

    Q: np.ndarray            # (n, n), triangulaire supérieure
    offset: float            # constante, sans effet sur l'argmin
    penalty: float           # le P effectivement utilisé
    max_marginal_gain: float # max Wᵢ — la borne théorique sur P
    n: int

    def energy(self, x) -> float:
        """Énergie d'un vecteur binaire. Sert aux tests et au diagnostic."""
        x = np.asarray(x, dtype=float)
        linear = np.diag(self.Q) @ x                  # Σᵢ Qᵢᵢ xᵢ
        quadratic = x @ np.triu(self.Q, 1) @ x        # Σᵢ<ₖ Qᵢₖ xᵢxₖ
        return float(linear + quadratic + self.offset)

    def all_energies(self) -> np.ndarray:
        """Énergie des 2ⁿ états, indexés par l'entier que forment leurs bits.

        L'indice `s` encode la sélection : le bit i de s vaut xᵢ.
        Cette convention est la MÊME que celle des masques de bits de
        geometry.py et que l'ordre des qubits de Qiskit (little-endian),
        ce qui évite toute inversion silencieuse.

        Coût mémoire : 8·2ⁿ octets. C'est le plafond du simulateur (§7.6).
        """
        size = 1 << self.n
        diag = np.diag(self.Q)
        upper = np.triu(self.Q, 1)

        # Matrice des bits : bits[s, i] = bit i de s
        states = np.arange(size, dtype=np.uint32)
        bits = ((states[:, None] >> np.arange(self.n)) & 1).astype(np.float64)

        linear = bits @ diag
        quadratic = np.einsum("si,ik,sk->s", bits, upper, bits, optimize=True)
        return linear + quadratic + self.offset


def marginal_gains(instance) -> np.ndarray:
    """Wᵢ = poids total que le candidat i peut couvrir à lui seul.

    C'est la quantité qui borne le poids de pénalité : le gain maximal qu'on
    pourrait tirer d'une borne supplémentaire ne dépasse jamais max Wᵢ.
    """
    W = np.zeros(instance.n_candidates)
    for j, cj in enumerate(instance.covering_sets):
        w = instance.weights[j]
        for i in cj:
            W[i] += w
    return W


def auto_penalty(W: np.ndarray, margin: float = 1.1) -> float:
    """Le P par défaut : juste au-dessus du gain marginal maximal.

    RAISONNEMENT (explanation.md §5.6) — passer de B à B+1 bornes :
        gain  de couverture ≤ max Wᵢ
        coût  de pénalité   = P·(B+1−B)² − P·0² = P
    Violer le budget est donc désavantageux ssi  P > max Wᵢ.
    La condition est symétrique : elle bloque aussi le passage à B−1.

    La marge de 10 % assure l'inégalité stricte sans écraser le signal de
    couverture — un P trop grand aplatit le paysage énergétique et prive
    l'optimiseur classique de tout gradient exploitable.
    """
    if W.size == 0:
        return 1.0
    return float(margin * np.max(W)) or 1.0


@dataclass
class QuboFidelity:
    """Diagnostic : la troncature au degré 2 est-elle exacte ICI ?

    L'approximation `1 − Π(1−xᵢ) ≈ Σxᵢ − Σᵢ<ₖ xᵢxₖ` vaut, pour une zone
    couverte par `s` bornes construites :

        s=0 → 0   (exact)      s=2 → 1   (exact)      s=4 → −2  (sous-estime)
        s=1 → 1   (exact)      s=3 → 0   (sous-estime)

    Elle est donc EXACTE tant que s ≤ 2. Comme une sélection compte au plus
    B bornes et qu'une zone j n'est atteignable que par les |Cⱼ| candidats de
    son ensemble couvrant, on a toujours :

        s_max = maxⱼ min(|Cⱼ|, B)

    Si s_max ≤ 2, le QUBO n'est pas une approximation du problème : il est
    EXACT sur tous les états faisables. Le calcul est en O(M).
    """

    max_multiplicity: int   # s_max = maxⱼ min(|Cⱼ|, B)
    exact: bool             # s_max ≤ 2
    zones_at_risk: int      # nb de zones pouvant atteindre s ≥ 3
    message: str


def qubo_fidelity(instance) -> QuboFidelity:
    """Mesure l'exactitude de la troncature pour les paramètres courants.

    Exposé dans l'interface : l'utilisateur voit en direct si le QUBO qu'il
    fait résoudre est exact ou approché, et pourquoi. C'est la réponse
    honnête — et vérifiable — à « ta troncature est fausse ».
    """
    B = instance.budget
    at_risk = sum(1 for cj in instance.covering_sets if min(len(cj), B) >= 3)
    s_max = max((min(len(cj), B) for cj in instance.covering_sets), default=0)
    exact = s_max <= 2

    if exact:
        message = (
            f"QUBO exact : aucune zone n'est à portée de 3 bornes simultanément "
            f"(multiplicité max = {s_max}). La troncature au degré 2 ne perd "
            f"strictement rien sur ces paramètres."
        )
    else:
        message = (
            f"QUBO approché : {at_risk} zone(s) peuvent être couvertes par "
            f"{s_max} bornes à la fois. La troncature sous-estime alors leur "
            f"couverture, ce qui pénalise la redondance. Le score affiché reste "
            f"exact — il est calculé par la vraie fonction objectif, jamais par "
            f"l'énergie du QUBO."
        )

    return QuboFidelity(
        max_multiplicity=s_max,
        exact=exact,
        zones_at_risk=at_risk,
        message=message,
    )


def build_qubo(instance, penalty: float | None = None) -> Qubo:
    """Assemble la matrice Q du problème.

    `penalty=None` → P calculé automatiquement par `auto_penalty`.
    Une valeur explicite permet à l'interface de démontrer en direct ce qui
    se passe quand P est trop petit (solution infaisable) ou trop grand
    (paysage plat, solution faisable mais médiocre).
    """
    n = instance.n_candidates
    B = instance.budget
    weights = instance.weights

    W = marginal_gains(instance)
    P = auto_penalty(W) if penalty is None else float(penalty)

    Q = np.zeros((n, n), dtype=np.float64)

    # ── Diagonale ────────────────────────────────────────────────────────
    #   −Wᵢ        récompense : construire en i rapporte ce qu'il couvre
    #   P(1−2B)    incitation : pousse à ATTEINDRE B bornes, pas à rester à 0
    for i in range(n):
        Q[i, i] = -W[i] + P * (1 - 2 * B)

    # ── Hors-diagonale, partie « doublon de couverture » ─────────────────
    #   +Wᵢₖ  : si i et k couvrent les mêmes zones, les prendre ENSEMBLE
    #           coûte cher. C'est exactement le terme de degré 2 issu de la
    #           troncature de 1 − Π(1−xᵢ), et il a un sens urbain direct :
    #           ne pas empiler deux bornes sur le même pâté de maisons.
    for j, cj in enumerate(instance.covering_sets):
        w = weights[j]
        members = sorted(cj)
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                Q[members[a], members[b]] += w

    # ── Hors-diagonale, partie « frein budgétaire » ──────────────────────
    #   +2P : issu du développement de P(Σxᵢ − B)².
    #   Remarquable : les deux mécanismes — anti-redondance et respect du
    #   budget — atterrissent sur le MÊME coefficient. Ce n'est pas un
    #   hasard, tous deux disent « n'empile pas les bornes ».
    for i in range(n):
        for k in range(i + 1, n):
            Q[i, k] += 2 * P

    return Qubo(
        Q=Q,
        offset=P * B * B,
        penalty=P,
        max_marginal_gain=float(np.max(W)) if W.size else 0.0,
        n=n,
    )


# --------------------------------------------------------------------------
# QUBO → Ising
# --------------------------------------------------------------------------

@dataclass
class Ising:
    """Hamiltonien de coût, diagonal dans la base de calcul.

        H_C = Σᵢ hᵢ·Zᵢ  +  Σᵢ<ₖ Jᵢₖ·ZᵢZₖ  +  offset·I

    Propriété fondamentale :  H_C|x⟩ = E(x)|x⟩
    Trouver l'état fondamental de H_C ≡ résoudre le QUBO.
    """

    h: np.ndarray                       # champs locaux, taille n
    J: dict[tuple[int, int], float]     # couplages, clés (i, k) avec i < k
    offset: float
    n: int

    @property
    def n_terms(self) -> int:
        return int(np.count_nonzero(self.h)) + len(self.J)


def qubo_to_ising(qubo: Qubo) -> Ising:
    """Change de variable xᵢ = (1 − zᵢ)/2, avec zᵢ ∈ {−1, +1}.

    Un QUBO parle de bits {0,1} ; un qubit a pour observable naturelle la
    matrice de Pauli-Z, de valeurs propres {−1,+1} (Z|0⟩=+|0⟩, Z|1⟩=−|1⟩).
    La convention retenue est donc :

        zᵢ = +1  (état |0⟩)  →  xᵢ = 0   « on ne construit pas »
        zᵢ = −1  (état |1⟩)  →  xᵢ = 1   « on construit »

    En substituant xᵢxₖ = (1 − zᵢ − zₖ + zᵢzₖ)/4 et en regroupant :

        hᵢ  = −Qᵢᵢ/2 − (1/4)·Σ_{k≠i} Q̃ᵢₖ         (Q̃ = Q symétrisée)
        Jᵢₖ = Qᵢₖ/4
        off = offset + Σᵢ Qᵢᵢ/2 + Σᵢ<ₖ Qᵢₖ/4
    """
    Q = qubo.Q
    n = qubo.n

    # Q est triangulaire supérieure : Qᵢₖ avec k < i est rangé en Q[k, i].
    # On symétrise pour pouvoir sommer « toute la ligne et toute la colonne ».
    upper = np.triu(Q, 1)
    symmetric = upper + upper.T

    diag = np.diag(Q)
    h = -diag / 2.0 - symmetric.sum(axis=1) / 4.0

    J: dict[tuple[int, int], float] = {}
    for i in range(n):
        for k in range(i + 1, n):
            if Q[i, k] != 0.0:
                J[(i, k)] = Q[i, k] / 4.0

    offset = qubo.offset + diag.sum() / 2.0 + upper.sum() / 4.0

    return Ising(h=h, J=J, offset=float(offset), n=n)


def ising_energy(ising: Ising, x) -> float:
    """Énergie d'un vecteur binaire, calculée côté Ising.

    Sert uniquement à PROUVER par test que la transformation est correcte :
    pour tout x, `ising_energy(...) == qubo.energy(x)`. Si ce test passe sur
    les 2ⁿ états, le pont classique → quantique est démontré sans trou.
    """
    x = np.asarray(x, dtype=float)
    z = 1.0 - 2.0 * x                                # xᵢ=0 → zᵢ=+1 ; xᵢ=1 → zᵢ=−1
    total = float(ising.h @ z) + ising.offset
    for (i, k), Jik in ising.J.items():
        total += Jik * z[i] * z[k]
    return total
