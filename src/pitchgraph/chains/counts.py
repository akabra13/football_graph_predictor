"""Per-match outcome counts: the raw material of every team flow graph.

For each match and each team in possession, count what happened from every
zone: moves to each other zone, shots (with their xG), and losing the ball.
Counts are kept PER MATCH, never pre-summed, because everything downstream
needs to leave matches out or resample them:

  * shrinkage weights are chosen by leave-one-match-out likelihood,
  * the matchup experiment predicts each match from the others,
  * bootstraps resample matches.

Layout of one match's array C (n zones, n + 2 outcome columns):
    C[i, j]      moves from zone i to zone j      (j < n)
    C[i, SHOT]   shots from zone i                (SHOT = n)
    C[i, LOSE]   ball lost in zone i              (LOSE = n + 1)
plus xg[i] (summed xG of those shots) and starts[i] (possessions whose first
open-play action was in zone i).

Coordinates are the attacking team's own frame, so a team's "conceded" counts
are simply its opponents' attacking counts in matches against it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from pitchgraph.chains.grid import TACTICAL, Grid
from pitchgraph.value.markov import classify_actions


def outcome_table(events: pl.LazyFrame, grid: Grid = TACTICAL) -> pl.DataFrame:
    """Long table: match_id, team_id, opp_id, z0, out, n, xg.

    `out` is the destination zone for moves, n for shots, n + 1 for turnovers.
    `events` needs home_team_id / away_team_id (as `Lake.events()` provides).
    """
    n = grid.n
    act = classify_actions(events, open_play_only=True)
    opp = (pl.when(pl.col("team_id") == pl.col("home_team_id"))
             .then(pl.col("away_team_id")).otherwise(pl.col("home_team_id")))
    out = (pl.when(pl.col("kind") == "move").then(grid.index_expr(pl.col("end_x"), pl.col("end_y")))
             .when(pl.col("kind") == "shot").then(pl.lit(n))
             .otherwise(pl.lit(n + 1)))
    return (act.with_columns(opp_id=opp, z0=grid.index_expr(pl.col("x"), pl.col("y")),
                             out=out.cast(pl.Int32))
               .group_by("match_id", "team_id", "opp_id", "z0", "out")
               .agg(n=pl.len(), xg=pl.col("xg").fill_null(0.0).sum())
               .collect())


def start_table(events: pl.LazyFrame, grid: Grid = TACTICAL) -> pl.DataFrame:
    """Possession starts: zone of each possession's first open-play action."""
    act = classify_actions(events, open_play_only=True)
    first = (act.sort("idx")
                .group_by("match_id", "possession", "team_id", maintain_order=True)
                .agg(pl.first("x"), pl.first("y")))
    return (first.with_columns(z=grid.index_expr(pl.col("x"), pl.col("y")))
                 .group_by("match_id", "team_id", "z").agg(n=pl.len())
                 .collect())


@dataclass
class TeamCounts:
    """One team's per-match counts on one side (attacking or conceded)."""

    team_id: int
    side: str                 # "attack" or "conceded"
    match_ids: np.ndarray     # (M,)
    C: np.ndarray             # (M, n, n + 2)
    xg: np.ndarray            # (M, n)
    starts: np.ndarray        # (M, n)

    @property
    def n_matches(self) -> int:
        return len(self.match_ids)

    def total(self, keep: np.ndarray | None = None):
        """Summed counts over matches (all, or a boolean / index selection)."""
        sel = slice(None) if keep is None else keep
        return self.C[sel].sum(0), self.xg[sel].sum(0), self.starts[sel].sum(0)


class CountStore:
    """Dense per-match count arrays for every team in one set of matches."""

    def __init__(self, outcomes: pl.DataFrame, starts: pl.DataFrame, grid: Grid = TACTICAL):
        self.grid = grid
        self.n = grid.n
        self.outcomes, self.starts = outcomes, starts
        self.teams = sorted(set(outcomes["team_id"].unique().to_list()))
        self._cache: dict = {}

    @classmethod
    def from_events(cls, events: pl.LazyFrame, grid: Grid = TACTICAL) -> "CountStore":
        return cls(outcome_table(events, grid), start_table(events, grid), grid)

    def _dense(self, rows: pl.DataFrame, srows: pl.DataFrame, match_ids):
        n = self.n
        index = {m: k for k, m in enumerate(match_ids)}
        C = np.zeros((len(match_ids), n, n + 2), dtype=np.float32)
        xg = np.zeros((len(match_ids), n), dtype=np.float32)
        st = np.zeros((len(match_ids), n), dtype=np.float32)
        if rows.height:
            k = np.array([index[m] for m in rows["match_id"].to_list()])
            z0, out = rows["z0"].to_numpy(), rows["out"].to_numpy()
            np.add.at(C, (k, z0, out), rows["n"].to_numpy())
            np.add.at(xg, (k, z0), rows["xg"].to_numpy())
        if srows.height:
            k = np.array([index[m] for m in srows["match_id"].to_list()])
            np.add.at(st, (k, srows["z"].to_numpy()), srows["n"].to_numpy())
        return C, xg, st

    def team(self, team_id: int, side: str = "attack") -> TeamCounts:
        key = (team_id, side)
        if key in self._cache:
            return self._cache[key]
        col = "team_id" if side == "attack" else "opp_id"
        rows = self.outcomes.filter(pl.col(col) == team_id)
        match_ids = np.array(sorted(set(rows["match_id"].to_list())))
        attackers = rows.select("match_id", "team_id").unique()
        srows = self.starts.join(attackers, on=["match_id", "team_id"], how="inner")
        C, xg, st = self._dense(rows, srows, match_ids)
        tc = TeamCounts(team_id, side, match_ids, C, xg, st)
        self._cache[key] = tc
        return tc

    def match_totals(self) -> dict:
        """{match_id: (C, xg, starts)} summed over both teams in the match.

        League totals minus one match's totals give a leave-one-match-out league
        without re-aggregating the whole table.
        """
        out = {}
        n = self.n
        for (mid,), rows in self.outcomes.group_by(["match_id"]):
            C = np.zeros((n, n + 2))
            np.add.at(C, (rows["z0"].to_numpy(), rows["out"].to_numpy()), rows["n"].to_numpy())
            xg = np.bincount(rows["z0"].to_numpy(), weights=rows["xg"].to_numpy(), minlength=n)
            s = self.starts.filter(pl.col("match_id") == mid)
            st = np.bincount(s["z"].to_numpy(), weights=s["n"].to_numpy(), minlength=n)
            out[mid] = (C, xg.astype(float), st.astype(float))
        return out

    def league_total(self, exclude_match: int | None = None):
        """Summed counts over every team (optionally leaving one match out)."""
        rows = self.outcomes if exclude_match is None else \
            self.outcomes.filter(pl.col("match_id") != exclude_match)
        srows = self.starts if exclude_match is None else \
            self.starts.filter(pl.col("match_id") != exclude_match)
        n = self.n
        C = np.zeros((n, n + 2))
        np.add.at(C, (rows["z0"].to_numpy(), rows["out"].to_numpy()), rows["n"].to_numpy())
        xg = np.bincount(rows["z0"].to_numpy(), weights=rows["xg"].to_numpy(), minlength=n)
        st = np.bincount(srows["z"].to_numpy(), weights=srows["n"].to_numpy(), minlength=n)
        return C, xg.astype(float), st.astype(float)
