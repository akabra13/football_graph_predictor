"""Falsifiable tests of the team-flow-graph concept.

  reidentification  Is a "style fingerprint" a real, stable property of a team?
  matchup_experiment  Does "A's attack x B's leaks" predict what A actually does
                      against B, better than A's own habits alone?

Both use only data the prediction could have had: halves are disjoint, and every
matchup prediction is built from other matches (leave-one-match-out), including
the league prior it is shrunk toward.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.chains import fingerprint, matchup, players
from pitchgraph.chains.counts import CountStore
from pitchgraph.chains.team import league_chain, select_kappa, shrunk_chain
from pitchgraph.graphs.routes import LANE_EDGES, LANES


# The 12 complete league seasons in the open data (verified: every team plays
# every other home and away). Keys are competition_season ids.
COMPLETE_LEAGUES = {
    "2_27": "Premier League 15/16", "11_27": "La Liga 15/16", "12_27": "Serie A 15/16",
    "7_27": "Ligue 1 15/16", "1238_108": "Indian Super League 21/22",
    "182_281": "Liga F 23/24", "49_107": "NWSL 2023", "37_281": "WSL 23/24",
    "135_281": "Frauen Bundesliga 23/24", "37_90": "WSL 20/21",
    "131_281": "Serie A Women 23/24", "37_4": "WSL 18/19",
}


def prepare(store: CountStore, min_matches: int = 10):
    C, xg, st = store.league_total()
    league = league_chain(C, xg, st, store.grid)
    teams = [t for t in store.teams if store.team(t).n_matches >= min_matches]
    kappa, scores = select_kappa([store.team(t) for t in teams], league)
    return league, teams, kappa, scores


# -- re-identification -------------------------------------------------------------
def reidentification(store: CountStore, league, teams, kappa) -> dict:
    """Odd-numbered matches vs even-numbered matches, per team."""
    first, second = [], []
    for t in teams:
        tc = store.team(t)
        idx = np.arange(tc.n_matches)
        for half, out in ((idx % 2 == 0, first), (idx % 2 == 1, second)):
            C, xg, st = tc.total(half)
            out.append(shrunk_chain(C, xg, st, league, kappa))
    res = fingerprint.reidentify(first, second)
    res["teams"] = teams
    return res


# -- matchup experiment --------------------------------------------------------------
def _crossing_lanes(grid, line: float = 80.0) -> tuple[np.ndarray, np.ndarray]:
    c = grid.centres()
    crossing = (c[:, 0][:, None] < line) & (c[:, 0][None, :] >= line)
    t = (line - c[:, 0][:, None]) / (c[:, 0][None, :] - c[:, 0][:, None] + 1e-9)
    y = c[:, 1][:, None] + t * (c[:, 1][None, :] - c[:, 1][:, None])
    return crossing, np.searchsorted(LANE_EDGES, y, side="right")


def _observed_lanes(C: np.ndarray, n: int, crossing, lane) -> np.ndarray:
    moves = C[:, :n] * crossing
    return np.array([moves[lane == k].sum() for k in range(len(LANES))])


def _lane_ll(counts: np.ndarray, shares: np.ndarray) -> float:
    return float(counts @ np.log(np.clip(shares, 1e-9, None)))


def matchup_experiment(store: CountStore, kappa: float, min_matches: int = 10) -> pl.DataFrame:
    """One row per (match, attacking team) with every model's predictions and the outcome.

    Models
      own        A's own chain (its habits)
      strength   A's own chain, threat scaled by how much B concedes overall
      defence    B's conceded chain alone (what teams do against B)
      matchup    A's chain with B's leakiness applied edge by edge
    """
    n = store.n
    crossing, lane = _crossing_lanes(store.grid)
    LC, Lxg, Lst = store.league_total()
    per_match = store.match_totals()
    eligible = {t for t in store.teams if store.team(t).n_matches >= min_matches}
    rows = []
    for mid, (mC, mxg, mst) in per_match.items():
        league = league_chain(LC - mC, Lxg - mxg, Lst - mst, store.grid)
        pair = store.outcomes.filter(pl.col("match_id") == mid).select("team_id", "opp_id").unique()
        for a, b in pair.iter_rows():
            if a not in eligible or b not in eligible:
                continue
            ta, tb = store.team(a, "attack"), store.team(b, "conceded")
            keep_a, keep_b = ta.match_ids != mid, tb.match_ids != mid
            A = shrunk_chain(*ta.total(keep_a), league, kappa)
            B = shrunk_chain(*tb.total(keep_b), league, kappa)
            M = matchup.matchup_chain(A, B, league)

            k = int(np.where(ta.match_ids == mid)[0][0])
            C, xg, st = ta.C[k].astype(float), ta.xg[k].astype(float), ta.starts[k].astype(float)
            possessions = st.sum()
            if possessions < 20:
                continue
            obs_lanes = _observed_lanes(C, n, crossing, lane)
            row = {"match_id": mid, "team_id": a, "opp_id": b,
                   "possessions": possessions, "xg_per_poss": xg.sum() / possessions,
                   "entries": obs_lanes.sum(),
                   "pred_own": A.threat,
                   "pred_strength": A.threat * B.threat / league.threat,
                   "pred_defence": B.threat,
                   "pred_matchup": M.threat}
            for name, chain in (("own", A), ("defence", B), ("matchup", M), ("league", league)):
                row[f"lane_ll_{name}"] = _lane_ll(obs_lanes, matchup.entry_lanes(chain))
            rows.append(row)
    return pl.DataFrame(rows)


def _crossfit(df: pl.DataFrame, col: str | None) -> np.ndarray:
    """Out-of-half calibrated predictions: fit y = a + b * pred on the matches of
    one parity, predict the other, then swap. With col=None, predicts the mean.

    Chains are not calibrated to xG per possession (they stop at the first shot,
    among other things), so raw squared error would mostly score each model's
    scale. Cross-fitting scores what matters - how well it ranks threat -
    without letting any model see the matches it is scored on.
    """
    y = df["xg_per_poss"].to_numpy()
    w = df["possessions"].to_numpy()
    half = df["match_id"].to_numpy() % 2 == 0
    out = np.zeros_like(y)
    for fit, pred in ((half, ~half), (~half, half)):
        if col is None:
            out[pred] = np.average(y[fit], weights=w[fit])
            continue
        x = df[col].to_numpy()
        X = np.column_stack([np.ones(fit.sum()), x[fit]])
        sw = np.sqrt(w[fit])
        beta, *_ = np.linalg.lstsq(X * sw[:, None], y[fit] * sw, rcond=None)
        out[pred] = beta[0] + beta[1] * x[pred]
    return out


def summarise_matchup(df: pl.DataFrame, n_boot: int = 1000, seed: int = 0) -> dict:
    """Skill of each model, and paired bootstrap CIs (by match) for the key gaps."""
    y = df["xg_per_poss"].to_numpy()
    w = df["possessions"].to_numpy()
    out = {"rows": df.height, "matches": df["match_id"].n_unique()}
    se = {"const": (y - _crossfit(df, None)) ** 2 * w}
    for m in ("own", "strength", "defence", "matchup"):
        p = df[f"pred_{m}"].to_numpy()
        se[m] = (y - _crossfit(df, f"pred_{m}")) ** 2 * w
        out[f"threat_skill_{m}"] = float(1 - se[m].sum() / se["const"].sum())
        out[f"threat_corr_{m}"] = float(np.corrcoef(y, p)[0, 1])
    E = df["entries"].to_numpy()
    for m in ("league", "own", "defence", "matchup"):
        out[f"lane_ll_{m}"] = float(df[f"lane_ll_{m}"].sum() / E.sum())

    # Paired bootstrap over MATCHES (both teams of a match move together).
    rng = np.random.default_rng(seed)
    mids = df["match_id"].to_numpy()
    uniq = np.unique(mids)
    groups = {m: np.where(mids == m)[0] for m in uniq}
    ll = {m: df[f"lane_ll_{m}"].to_numpy() for m in ("league", "own", "matchup")}
    gaps = {"threat_matchup_vs_strength": [], "threat_matchup_vs_own": [],
            "lane_own_vs_league": [], "lane_matchup_vs_own": []}
    for _ in range(n_boot):
        idx = np.concatenate([groups[m] for m in rng.choice(uniq, len(uniq))])
        base = se["const"][idx].sum()
        # Positive = matchup explains more of the variance than the comparison.
        gaps["threat_matchup_vs_strength"].append((se["strength"][idx].sum() - se["matchup"][idx].sum()) / base)
        gaps["threat_matchup_vs_own"].append((se["own"][idx].sum() - se["matchup"][idx].sum()) / base)
        gaps["lane_own_vs_league"].append((ll["own"][idx].sum() - ll["league"][idx].sum()) / E[idx].sum())
        gaps["lane_matchup_vs_own"].append((ll["matchup"][idx].sum() - ll["own"][idx].sum()) / E[idx].sum())
    for k, v in gaps.items():
        v = np.array(v)
        out[k] = (float(np.percentile(v, 5)), float(np.percentile(v, 95)))
    return out


# -- player absences ------------------------------------------------------------------
def absences(actions: pl.DataFrame, lineups: pl.DataFrame) -> pl.DataFrame:
    """Predicted (player-chain removal) vs observed (opponent-adjusted) drop in
    threat for every regular who missed and played at least 3 matches."""
    rates = players.opponent_adjusted_rates(actions)
    rows = []
    for t in actions["team_id"].unique().to_list():
        rows += [{**r, "team_id": t} for r in players.missed_matches(actions, lineups, t, rates=rates)]
    return pl.DataFrame(rows)


def summarise_absences(df: pl.DataFrame, n_perm: int = 5000, seed: int = 0) -> dict:
    df = df.filter(pl.col("observed_drop").is_finite())
    mid = ((df["pred_adapt"] + df["pred_no_adapt"]) / 2).to_numpy()
    obs = df["observed_drop"].to_numpy()
    r = float(np.corrcoef(obs, mid)[0, 1])
    rng = np.random.default_rng(seed)
    null = np.array([np.corrcoef(rng.permutation(obs), mid)[0, 1] for _ in range(n_perm)])
    return {"n": int(df.height), "r": r, "p": float(np.mean(null >= r))}


# -- the whole suite, in the shape the Library's Method page reads ----------------------
def run_suite(seasons: list[tuple[str, pl.LazyFrame, pl.DataFrame | None]], log=print) -> dict:
    """seasons: (label, events of one competition-season, its lineups or None)."""
    out = {"reid": [], "lanes": [], "volume": [], "per_season": []}
    absence_rows = []
    for label, events, lineups in seasons:
        store = CountStore.from_events(events)
        league, teams, kappa, _ = prepare(store)
        reid = reidentification(store, league, teams, kappa)
        summary = summarise_matchup(matchup_experiment(store, kappa))
        out["reid"].append([label, reid["top1"], reid["chance_top1"]])
        out["lanes"].append([label, *summary["lane_matchup_vs_own"]])
        out["volume"].append([label, *summary["threat_matchup_vs_strength"]])
        out["per_season"].append({"season": label, "kappa": kappa, "teams": len(teams),
                                  "reid_top3": reid["top3"], **{k: v for k, v in summary.items()
                                                                if not isinstance(v, tuple)}})
        if lineups is not None:
            absence_rows.append(absences(players.player_actions(events), lineups))
        log(f"  {label}: re-ID {reid['top1']:.2f} (chance {reid['chance_top1']:.2f}), kappa {kappa:g}")
    if absence_rows:
        out["missed"] = summarise_absences(pl.concat(absence_rows, how="diagonal_relaxed"))
    out["scope"] = f"{len(seasons)} complete league seasons from the full open data"
    return out
