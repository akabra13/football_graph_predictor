"""Does the denial planner rank links the way real matches do?

The planner says: take link L away and the team's threat falls by between
`drop_adapt` and `drop_no_adapt`. Nobody removes a link on purpose in the
data, but matches differ in how much of each link a team got to use. So:

  y    a team's threat in one match (xG per possession) relative to what
       its strength and the opponent's leakiness predict, both measured on
       the OTHER matches only
  u_L  how much of link L the team used in that match relative to its own
       usual share of moves, again from its other matches (-1 = none of it)

Regressing y on all the u_L together gives, per link, the share of threat
that goes missing when the link is fully suppressed and the others are held
fixed: the same quantity the planner's range claims to bracket.

This is observational. A team that is playing badly also uses its dangerous
links less, so slopes can overstate a link's causal value. What the test can
show is whether the planner orders the links correctly and whether its
ranges are the right size; it cannot prove that denying a link causes the drop.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.chains import denial
from pitchgraph.chains.counts import CountStore
from pitchgraph.chains.team import Chain, league_chain, shrunk_chain

N_REGIONS = 15
MIN_POSSESSIONS = 20
MIN_USUAL_SHARE = 0.002     # below this a team's usual share is too small to form a ratio
U_CLIP = (-1.0, 3.0)


def region_links(moves: np.ndarray, regions: np.ndarray) -> np.ndarray:
    """(15, 15) move counts between regions from an (n, n) zone move matrix."""
    Z = np.eye(N_REGIONS)[regions]
    return Z.T @ moves @ Z


def _mid_drops(chain: Chain, masks: list[np.ndarray]) -> np.ndarray:
    base = chain.threat
    return np.array([0.5 * ((base - denial.deny(chain, m, adapt=True).threat)
                            + (base - denial.deny(chain, m, adapt=False).threat)) / base for m in masks])


def match_rows(store: CountStore, min_matches: int = 10,
               excess_links: list[tuple[int, int]] | None = None, kappa: float | None = None):
    """Per team-match: y, the (15, 15) relative usage deviations, match id, and
    the raw link shares (for choosing which links are common enough to test).

    Everything a row is compared with comes from other matches.

    With `excess_links` (and the season's `kappa`), a fifth array gives, per
    row and link, the planner's midpoint drop on the team's own leave-this-
    match-out chain minus the same on the leave-this-match-out league chain.
    """
    masks = None
    if excess_links is not None:
        reg = denial.zone_regions(store.grid)
        masks = [denial.link_mask(reg, a, b) for a, b in excess_links]
    E = []
    n = store.n
    regions = denial.zone_regions(store.grid)
    eligible = {t for t in store.teams if store.team(t).n_matches >= min_matches}
    LC, Lxg, Lst = store.league_total()
    per_match = store.match_totals()
    Y, U, M, S = [], [], [], []
    for mid, (mC, mxg, mst) in per_match.items():
        league_rate = (Lxg.sum() - mxg.sum()) / max(Lst.sum() - mst.sum(), 1.0)
        pair = store.outcomes.filter(pl.col("match_id") == mid).select("team_id", "opp_id").unique()
        for a, b in pair.iter_rows():
            if a not in eligible or b not in eligible:
                continue
            ta, tb = store.team(a, "attack"), store.team(b, "conceded")
            k = int(np.where(ta.match_ids == mid)[0][0])
            poss = float(ta.starts[k].sum())
            if poss < MIN_POSSESSIONS:
                continue
            rest_a, rest_b = ta.match_ids != mid, tb.match_ids != mid
            a_rate = ta.xg[rest_a].sum() / max(ta.starts[rest_a].sum(), 1.0)
            b_rate = tb.xg[rest_b].sum() / max(tb.starts[rest_b].sum(), 1.0)
            expected = a_rate * b_rate / league_rate if league_rate > 0 else 0.0
            if expected <= 0:
                continue
            y = float(ta.xg[k].sum()) / poss / expected - 1.0

            now = ta.C[k][:, :n].astype(float)
            usual = ta.C[rest_a].sum(0)[:, :n].astype(float)
            share_now = region_links(now, regions) / max(now.sum(), 1.0)
            share_usual = region_links(usual, regions) / max(usual.sum(), 1.0)
            u = np.where(share_usual >= MIN_USUAL_SHARE,
                         share_now / np.clip(share_usual, 1e-12, None) - 1.0, 0.0)
            Y.append(y); U.append(np.clip(u, *U_CLIP)); M.append(mid); S.append(share_usual)
            if masks is not None:
                league = league_chain(LC - mC, Lxg - mxg, Lst - mst, store.grid)
                team = shrunk_chain(*ta.total(rest_a), league, kappa)
                E.append(_mid_drops(team, masks) - _mid_drops(league, masks))
    if masks is not None:
        return np.array(Y), np.array(U), np.array(M), np.array(S), np.array(E)
    return np.array(Y), np.array(U), np.array(M), np.array(S)


def gamma_test(y, X, Z, match_ids, n_boot: int = 500, seed: int = 0) -> dict:
    """Coefficient on the team-specific term Z (one column) in the joint
    regression of y on X and Z, with a 90% interval by resampling matches."""
    rng = np.random.default_rng(seed)
    A = np.column_stack([X, Z])
    g = float(fit_slopes(y, A)[-1])
    uniq, inv = np.unique(match_ids, return_inverse=True)
    rows_of = [np.flatnonzero(inv == i) for i in range(len(uniq))]
    boots = []
    for _ in range(n_boot):
        idx = np.concatenate([rows_of[i] for i in rng.integers(0, len(uniq), len(uniq))])
        boots.append(fit_slopes(y[idx], A[idx])[-1])
    lo, hi = float(np.percentile(boots, 5)), float(np.percentile(boots, 95))
    return {"gamma": g, "ci": [lo, hi], "passes_bar": bool(lo > 0)}


def model_drops(league: Chain, links: list[tuple[int, int]]) -> np.ndarray:
    """(len(links), 2): the planner's adapt / no-adapt drop for each link on the league chain."""
    regions = denial.zone_regions(league.grid)
    base = league.threat
    out = []
    for a, b in links:
        mask = denial.link_mask(regions, a, b)
        out.append([(base - denial.deny(league, mask, adapt=True).threat) / base,
                    (base - denial.deny(league, mask, adapt=False).threat) / base])
    return np.array(out)


def league_of(store: CountStore) -> Chain:
    C, xg, st = store.league_total()
    return league_chain(C, xg, st, store.grid)


def fit_slopes(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Joint least-squares slopes of y on the columns of X (with an intercept)."""
    A = np.column_stack([np.ones(len(y)), X])
    return np.linalg.lstsq(A, y, rcond=None)[0][1:]


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def evaluate(y, X, match_ids, model_mid, usage, n_boot: int = 500, seed: int = 0) -> dict:
    """Slopes, their rank agreement with the planner and with plain usage, and
    90% intervals from resampling whole matches."""
    rng = np.random.default_rng(seed)
    beta = fit_slopes(y, X)
    uniq, inv = np.unique(match_ids, return_inverse=True)
    rows_of = [np.flatnonzero(inv == i) for i in range(len(uniq))]
    boots, rs_model, rs_usage = [], [], []
    for _ in range(n_boot):
        idx = np.concatenate([rows_of[i] for i in rng.integers(0, len(uniq), len(uniq))])
        b = fit_slopes(y[idx], X[idx])
        boots.append(b)
        rs_model.append(spearman(b, model_mid))
        rs_usage.append(spearman(b, usage))
    boots, rs_model, rs_usage = np.array(boots), np.array(rs_model), np.array(rs_usage)
    ci = lambda v: [float(np.percentile(v, 5)), float(np.percentile(v, 95))]
    return {"beta": beta.tolist(),
            "beta_ci": [ci(boots[:, j]) for j in range(X.shape[1])],
            "spearman_model": spearman(beta, model_mid), "spearman_model_ci": ci(rs_model),
            "spearman_usage": spearman(beta, usage), "spearman_usage_ci": ci(rs_usage),
            "spearman_diff_ci": ci(rs_model - rs_usage)}
