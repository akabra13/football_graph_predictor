"""Predictability audit: which pre-match statements about a team hold in its next match?

Design and reading rules: docs/predictability_audit.md.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.chains import denial
from pitchgraph.chains.counts import CountStore
from pitchgraph.chains.denial_test import region_links
from pitchgraph.chains.validate import _crossing_lanes, _observed_lanes
from pitchgraph.graphs.routes import LANE_EDGES

MIN_POSSESSIONS = 20
PSEUDO = 5.0
LANES5 = ["left_flank", "left_halfspace", "centre", "right_halfspace", "right_flank"]
FEATURES = (
    [f"entry_{k}" for k in LANES5]
    + ["final_third_share", "left_right_balance", "width_final_third", "start_height",
       "possession", "directness", "long_forward_share", "switch_share", "turnover_rate",
       "own_third_turnover_share",
       "shots_per_possession", "xg_per_shot", "xg_per_possession", "central_entries_per_possession",
       "lever_share",
       "entropy_rate", "spectral_gap", "reciprocity", "hodge_circulation"]
)
GRAPH_FEATURES = ("entropy_rate", "spectral_gap", "reciprocity", "hodge_circulation")


# -- graph structure of a region flow matrix ------------------------------------
def entropy_rate(R: np.ndarray) -> float:
    """Bits per move of the region-to-region chain (rows weighted by how often they are used)."""
    rows = R.sum(1)
    total = rows.sum()
    if total <= 0:
        return float("nan")
    P = np.divide(R, rows[:, None], out=np.zeros_like(R, dtype=float), where=rows[:, None] > 0)
    logs = np.log2(P, out=np.zeros_like(P), where=P > 0)
    return float(-(rows / total) @ (P * logs).sum(1))


def spectral_gap(R: np.ndarray) -> float:
    """1 - |second eigenvalue| of the row-normalised chain: how fast position mixes."""
    rows = R.sum(1)
    k = len(R)
    P = np.where(rows[:, None] > 0, R / np.clip(rows[:, None], 1e-12, None), 1.0 / k)
    ev = np.sort(np.abs(np.linalg.eigvals(P)))[::-1]
    return float(1.0 - ev[1])


def reciprocity(R: np.ndarray) -> float:
    """Share of between-region movement that is cancelled by movement the other way."""
    F = R.astype(float).copy()
    np.fill_diagonal(F, 0.0)
    gross = F.sum()
    return float(1.0 - np.abs(F - F.T).sum() / 2.0 / gross) if gross > 0 else float("nan")


def hodge_circulation(R: np.ndarray) -> float:
    """Share of the NET flow between regions that is cyclic rather than a gradient.

    Combinatorial Hodge decomposition: the net flow Y = F - F^T on the edges
    is split into the part explained by a potential on the regions (ball
    going from "lower" to "higher" regions: progression) and the remainder,
    which flows around loops (circulation). Returns |cyclic|^2 / |Y|^2.
    """
    F = R.astype(float).copy()
    np.fill_diagonal(F, 0.0)
    k = len(F)
    i, j = np.triu_indices(k, 1)
    used = (F[i, j] + F[j, i]) > 0
    i, j = i[used], j[used]
    if len(i) == 0:
        return float("nan")
    y = F[i, j] - F[j, i]
    if not np.any(y):
        return float("nan")
    B = np.zeros((len(i), k))
    B[np.arange(len(i)), i] = -1.0
    B[np.arange(len(i)), j] = 1.0
    s = np.linalg.lstsq(B, y, rcond=None)[0]
    resid = y - B @ s
    return float(resid @ resid / (y @ y))


# -- one team in one match --------------------------------------------------------
class Geometry:
    """Per-grid constants, computed once."""

    def __init__(self, grid):
        c = grid.centres()
        self.n = grid.n
        self.x, self.lane = c[:, 0], np.searchsorted(LANE_EDGES, c[:, 1], side="right")
        self.dx = self.x[None, :] - self.x[:, None]
        self.dlane = np.abs(self.lane[None, :] - self.lane[:, None])
        self.regions = denial.zone_regions(grid)
        self.crossing, self.cross_lane = _crossing_lanes(grid)


def match_features(C: np.ndarray, xg: np.ndarray, st: np.ndarray, geo: Geometry,
                   opp_moves: float) -> dict:
    """The candidate features for one team's open-play actions in one match."""
    n = geo.n
    C = C.astype(float)
    moves, shots, losses = C[:, :n], C[:, n], C[:, n + 1]
    m_tot, poss = moves.sum(), float(st.sum())
    actions = C.sum(1)
    a_tot = actions.sum()
    out = {}
    lanes = _observed_lanes(C, n, geo.crossing, geo.cross_lane)
    for k, name in enumerate(LANES5):
        out[f"entry_{name}"] = lanes[k] / lanes.sum() if lanes.sum() > 0 else np.nan
    final = geo.x >= 80
    out["final_third_share"] = actions[final].sum() / a_tot if a_tot else np.nan
    out["left_right_balance"] = (actions[geo.lane <= 1].sum() - actions[geo.lane >= 3].sum()) / a_tot \
        if a_tot else np.nan
    f_act = actions[final].sum()
    out["width_final_third"] = actions[final & ((geo.lane == 0) | (geo.lane == 4))].sum() / f_act \
        if f_act else np.nan
    out["start_height"] = float(st @ geo.x) / poss if poss else np.nan
    out["possession"] = m_tot / (m_tot + opp_moves) if (m_tot + opp_moves) else np.nan
    out["directness"] = float((moves * geo.dx).sum()) / m_tot if m_tot else np.nan
    out["long_forward_share"] = moves[geo.dx >= 40].sum() / m_tot if m_tot else np.nan
    out["switch_share"] = moves[geo.dlane >= 2].sum() / m_tot if m_tot else np.nan
    out["turnover_rate"] = losses.sum() / a_tot if a_tot else np.nan
    out["own_third_turnover_share"] = losses[geo.x < 40].sum() / losses.sum() if losses.sum() else np.nan
    out["shots_per_possession"] = shots.sum() / poss if poss else np.nan
    out["xg_per_shot"] = float(xg.sum()) / shots.sum() if shots.sum() else np.nan
    out["xg_per_possession"] = float(xg.sum()) / poss if poss else np.nan
    R = region_links(moves, geo.regions)
    out["central_entries_per_possession"] = (R[:, 12].sum() - R[12, 12]) / poss if poss else np.nan
    out["lever_share"] = (R[11, 12] + R[13, 12]) / m_tot if m_tot else np.nan
    out["entropy_rate"] = entropy_rate(R)
    out["spectral_gap"] = spectral_gap(R)
    out["reciprocity"] = reciprocity(R)
    out["hodge_circulation"] = hodge_circulation(R)
    return out


def season_table(store: CountStore, min_matches: int = 10) -> pl.DataFrame:
    """One row per eligible team-match: match_id, team_id, opp_id and every feature."""
    geo = Geometry(store.grid)
    n = store.n
    eligible = {t for t in store.teams if store.team(t).n_matches >= min_matches}
    pairs = store.outcomes.select("match_id", "team_id", "opp_id").unique()
    moves_of = {}
    for t in store.teams:
        tc = store.team(t)
        for k, mid in enumerate(tc.match_ids):
            moves_of[(int(mid), t)] = float(tc.C[k][:, :n].sum())
    rows = []
    for mid, a, b in pairs.iter_rows():
        if a not in eligible or b not in eligible:
            continue
        tc = store.team(a)
        k = int(np.where(tc.match_ids == mid)[0][0])
        if tc.starts[k].sum() < MIN_POSSESSIONS:
            continue
        f = match_features(tc.C[k], tc.xg[k], tc.starts[k], geo, moves_of.get((int(mid), b), 0.0))
        rows.append({"match_id": int(mid), "team_id": int(a), "opp_id": int(b), **f})
    return pl.DataFrame(rows)


# -- leave-one-match-out predictions -----------------------------------------------
def _loo_shrunk(values: np.ndarray, groups: np.ndarray, league_loo: np.ndarray) -> np.ndarray:
    """For each row: the mean of the OTHER rows in its group, shrunk to that row's league mean."""
    out = np.empty(len(values))
    ok = np.isfinite(values)
    for g in np.unique(groups):
        idx = np.flatnonzero(groups == g)
        v = values[idx]
        good = ok[idx]
        s, c = np.nansum(v), good.sum()
        s_other = s - np.where(good, v, 0.0)
        c_other = c - good.astype(int)
        out[idx] = (s_other + PSEUDO * league_loo[idx]) / (c_other + PSEUDO)
    return out


def predictions(table: pl.DataFrame, feature: str) -> dict:
    """y and the three leave-this-match-out predictions for one feature in one season."""
    y = table[feature].to_numpy().astype(float)
    mid = table["match_id"].to_numpy()
    ok = np.isfinite(y)
    total, count = np.nansum(y), ok.sum()
    # league without this match: both teams' rows of the match are removed
    per_match_sum = {m: 0.0 for m in np.unique(mid)}
    per_match_cnt = {m: 0 for m in per_match_sum}
    for v, m, g in zip(y, mid, ok):
        if g:
            per_match_sum[m] += v
            per_match_cnt[m] += 1
    league = np.array([(total - per_match_sum[m]) / max(count - per_match_cnt[m], 1) for m in mid])
    team = _loo_shrunk(y, table["team_id"].to_numpy(), league)
    # what teams do against O: rows where the OPPONENT is O, excluding this match
    conceded = _loo_shrunk(y, table["opp_id"].to_numpy(), league)
    return {"y": y, "match": mid, "league": league, "team": team, "both": team + (conceded - league)}


def score(parts: list[dict], n_boot: int = 500, seed: int = 0) -> dict:
    """Pooled out-of-sample R2 for a feature, with 90% intervals by resampling matches."""
    y = np.concatenate([p["y"] for p in parts])
    keys = np.concatenate([np.array([f"{i}_{m}" for m in p["match"]]) for i, p in enumerate(parts)])
    e = {k: (y - np.concatenate([p[k] for p in parts])) ** 2 for k in ("league", "team", "both")}
    ok = np.isfinite(y)
    for k in e:
        e[k] = np.where(ok, e[k], 0.0)
    uniq, inv = np.unique(keys, return_inverse=True)
    sums = {k: np.bincount(inv, weights=e[k], minlength=len(uniq)) for k in e}

    def r2(w):
        s0 = (w * sums["league"]).sum()
        if s0 <= 0:
            return np.nan, np.nan
        rt = 1 - (w * sums["team"]).sum() / s0
        rb = 1 - (w * sums["both"]).sum() / s0
        return rt, rb - rt

    rt, gain = r2(np.ones(len(uniq)))
    rng = np.random.default_rng(seed)
    boots = np.array([r2(np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq)).astype(float))
                      for _ in range(n_boot)])
    ci = lambda v: [float(np.nanpercentile(v, 5)), float(np.nanpercentile(v, 95))]
    r_ci, g_ci = ci(boots[:, 0]), ci(boots[:, 1])
    tier = "lead" if rt >= 0.20 and r_ci[0] > 0 else "usable" if rt >= 0.05 and r_ci[0] > 0 else "drop"
    return {"n": int(ok.sum()), "r2_team": float(rt), "r2_team_ci": r_ci, "gain_opponent": float(gain),
            "gain_opponent_ci": g_ci, "tier": tier, "opponent_matters": bool(g_ci[0] > 0)}
