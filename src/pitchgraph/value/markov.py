"""Possession value as an absorbing Markov chain over a zone graph (xT-style).

The pitch is a graph of zones. From any zone the team in possession does one of
three things: shoots (absorbed, worth that zone's expected xG), loses the ball
(absorbed, worth 0), or moves the ball to another zone (a transition along a
graph edge). The value of a zone is the probability-weighted value of what
happens next, which is a linear system:

    V = s * g + m * (T @ V)      =>      (I - diag(m) T) V = s * g

  s(z)  P(shoot | act in z)       g(z)  mean xG of shots from z
  m(z)  P(move  | act in z)       T     zone-to-zone transition matrix of moves

Solving it exactly (no value iteration) gives each zone the probability that
possession there eventually produces a goal. Every action is then valued by how
much it changes that probability.

Design choices, stated so they can be challenged:
  * Open play only by default: set-piece deliveries and penalties are excluded,
    so a corner does not make the corner flag look like a dangerous place.
  * Turnovers are worth 0, not negative. The opponent's resulting threat is a
    separate question (a VAEP-style extension, not modelled here).
  * Carries always succeed in StatsBomb data; losing the ball on the dribble
    appears as Dispossessed / failed Dribble / Miscontrol, counted as turnovers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from pitchgraph.data.possessions import RESTARTS

PITCH_X, PITCH_Y = 120.0, 80.0
TURNOVER_TYPES = ["Dispossessed", "Miscontrol"]


def zone_expr(x: pl.Expr, y: pl.Expr, nx: int, ny: int) -> pl.Expr:
    zx = (x / (PITCH_X / nx)).floor().clip(0, nx - 1).cast(pl.Int32)
    zy = (y / (PITCH_Y / ny)).floor().clip(0, ny - 1).cast(pl.Int32)
    return zx * ny + zy


def classify_actions(events: pl.LazyFrame, open_play_only: bool = True) -> pl.LazyFrame:
    """Label in-possession actions as shot / move / turnover, with zones' inputs."""
    ev = events.filter(pl.col("x").is_not_null())
    if "in_possession" in ev.collect_schema().names():
        ev = ev.filter(pl.col("in_possession"))
    else:
        ev = ev.filter(pl.col("team_id") == pl.col("possession_team_id"))

    # NULL SAFETY: `sub_type` and `outcome` are null on most events, and in
    # polars `null.is_in(...)` and `null != "x"` are null, which a filter
    # treats as false. An unguarded version of this function silently dropped
    # ~92% of passes (every pass without a sub-type). Every comparison on a
    # nullable column below is filled explicitly.
    sub = pl.col("sub_type").fill_null("")
    is_pass = pl.col("type") == "Pass"
    failed_pass = is_pass & pl.col("outcome").is_not_null()
    kind = (
        pl.when((pl.col("type") == "Shot") & (sub != "Penalty")).then(pl.lit("shot"))
        .when(is_pass & pl.col("outcome").is_null() & pl.col("end_x").is_not_null()).then(pl.lit("move"))
        .when((pl.col("type") == "Carry") & pl.col("end_x").is_not_null()).then(pl.lit("move"))
        .when(failed_pass).then(pl.lit("turnover"))
        .when(pl.col("type").is_in(TURNOVER_TYPES)).then(pl.lit("turnover"))
        .when((pl.col("type") == "Dribble") & (pl.col("outcome") == "Incomplete")).then(pl.lit("turnover"))
        .otherwise(None)
    )
    ev = ev.with_columns(kind=kind).filter(pl.col("kind").is_not_null())
    if open_play_only:
        is_restart = is_pass & sub.is_in(RESTARTS)
        is_fk_shot = (pl.col("type") == "Shot") & (sub == "Free Kick")
        ev = ev.filter(~(is_restart | is_fk_shot))
    return ev


@dataclass
class MarkovValue:
    """Absorbing-chain possession value. Fit with `fit`, then value actions."""

    nx: int = 16
    ny: int = 12
    open_play_only: bool = True
    prior_turnovers: float = 1.0
    name: str = "markov_xt"
    values: np.ndarray | None = field(default=None, repr=False)
    counts: np.ndarray | None = field(default=None, repr=False)

    @property
    def n(self) -> int:
        return self.nx * self.ny

    def fit(self, events: pl.LazyFrame) -> "MarkovValue":
        act = classify_actions(events, self.open_play_only).with_columns(
            z0=zone_expr(pl.col("x"), pl.col("y"), self.nx, self.ny),
            z1=zone_expr(pl.col("end_x"), pl.col("end_y"), self.nx, self.ny),
        ).select("kind", "z0", "z1", "xg").collect()

        n = self.n
        total = np.bincount(act["z0"].to_numpy(), minlength=n).astype(float)
        shots = act.filter(pl.col("kind") == "shot")
        n_shot = np.bincount(shots["z0"].to_numpy(), minlength=n).astype(float)
        xg_sum = np.bincount(shots["z0"].to_numpy(),
                             weights=shots["xg"].fill_null(0.0).to_numpy(), minlength=n)
        moves = act.filter(pl.col("kind") == "move")
        z0, z1 = moves["z0"].to_numpy(), moves["z1"].to_numpy()
        n_move = np.bincount(z0, minlength=n).astype(float)
        T = np.zeros((n, n))
        np.add.at(T, (z0, z1), 1.0)

        # Every zone gets `prior_turnovers` pseudo-observations of losing the
        # ball. This keeps m < 1 (the system is always solvable, even for a zone
        # whose only data is a carry that stays inside it) and shrinks thinly
        # observed zones toward "you will probably lose it".
        denom = total + self.prior_turnovers
        s, m = n_shot / denom, n_move / denom
        g = np.divide(xg_sum, n_shot, out=np.zeros(n), where=n_shot > 0)
        T = np.divide(T, n_move[:, None], out=np.zeros_like(T), where=n_move[:, None] > 0)

        A = np.eye(n) - m[:, None] * T
        self.values = np.linalg.solve(A, s * g)
        self.counts = total
        self._parts = {"s": s, "m": m, "g": g}
        return self

    # -- ValueModel ----------------------------------------------------------
    def state_value(self, x: pl.Expr, y: pl.Expr) -> pl.Expr:
        if self.values is None:
            raise RuntimeError("fit the model first")
        z = zone_expr(x, y, self.nx, self.ny)
        return z.replace_strict(old=list(range(self.n)), new=self.values.tolist(),
                                return_dtype=pl.Float64)

    def add_action_values(self, events: pl.LazyFrame) -> pl.LazyFrame:
        """v_start, v_end, and value = what the action added to scoring chances."""
        v0 = self.state_value(pl.col("x"), pl.col("y"))
        v1 = self.state_value(pl.col("end_x"), pl.col("end_y"))
        act = classify_actions(events, open_play_only=False)
        return act.with_columns(v_start=v0, v_end=v1).with_columns(
            value=pl.when(pl.col("kind") == "move").then(pl.col("v_end") - pl.col("v_start"))
                   .when(pl.col("kind") == "shot").then(pl.col("xg").fill_null(0.0) - pl.col("v_start"))
                   .otherwise(-pl.col("v_start"))
        )

    def grid(self) -> np.ndarray:
        """Values as an (nx, ny) array, x along the first axis."""
        return self.values.reshape(self.nx, self.ny)

