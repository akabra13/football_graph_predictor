"""Style fingerprints: how far apart two teams' flow graphs are.

Two teams play alike when, in the zones where they spend their time, they do
the same things next. The distance is a visit-weighted Jensen-Shannon
divergence between the two chains' rows:

    d(A, B) = sum_i w_i * JS(P_A[i], P_B[i]),   w = (visits_A + visits_B) / 2

so a difference in a zone either team actually uses counts, and a difference
in a zone neither touches does not. JS is symmetric and bounded in [0, 1]
(base 2), which keeps distances comparable across leagues and seasons.

Whether this captures "style" rather than noise is tested directly by
`reidentify`: a team's fingerprint from half its matches should pick out the
same team's fingerprint from the other half.
"""

from __future__ import annotations

import numpy as np

from pitchgraph.chains.team import Chain


def _js_rows(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    M = 0.5 * (P + Q)

    def kl(A, B):
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(A > 0, A * np.log2(A / np.where(B > 0, B, 1.0)), 0.0)
        return t.sum(1)

    return 0.5 * kl(P, M) + 0.5 * kl(Q, M)


def visit_share(chain: Chain) -> np.ndarray:
    v = np.clip(chain.visits(), 0, None)
    return v / v.sum()


def distance(a: Chain, b: Chain) -> float:
    w = 0.5 * (visit_share(a) + visit_share(b))
    return float(w @ _js_rows(a.P, b.P))


def distance_matrix(rows: list[Chain], cols: list[Chain] | None = None) -> np.ndarray:
    cols = rows if cols is None else cols
    vr = [visit_share(c) for c in rows]
    vc = vr if cols is rows else [visit_share(c) for c in cols]
    D = np.zeros((len(rows), len(cols)))
    for i, a in enumerate(rows):
        for j, b in enumerate(cols):
            w = 0.5 * (vr[i] + vc[j])
            D[i, j] = w @ _js_rows(a.P, b.P)
    return D


def reidentify(first: list[Chain], second: list[Chain]) -> dict:
    """first[k] and second[k] are the same team from disjoint matches.

    Returns top-1 / top-3 accuracy and the rank of the true match for each team.
    Chance top-1 is 1/N.
    """
    D = distance_matrix(first, second)
    order = np.argsort(D, axis=1)
    ranks = np.array([int(np.where(order[k] == k)[0][0]) + 1 for k in range(len(first))])
    return {"n": len(first), "top1": float(np.mean(ranks == 1)),
            "top3": float(np.mean(ranks <= 3)), "chance_top1": 1.0 / len(first),
            "ranks": ranks.tolist()}


def mds(D: np.ndarray, k: int = 2) -> np.ndarray:
    """Classical multidimensional scaling: points whose distances approximate D."""
    n = len(D)
    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J @ (D ** 2) @ J
    vals, vecs = np.linalg.eigh(B)
    idx = np.argsort(vals)[::-1][:k]
    return vecs[:, idx] * np.sqrt(np.clip(vals[idx], 0, None))
