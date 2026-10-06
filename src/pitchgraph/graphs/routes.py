"""How a team moves the ball up the pitch: progression routes through the lanes.

Mining raw zone sequences produces thousands of near-unique paths, too sparse
to count on one team's season. Instead each possession is summarised by WHERE it
crossed two lines, using the five vertical lanes coaches already use:

    wide left | left half-space | centre | right half-space | wide right

  entry_mid    lane where the ball first crossed x=40 (into the middle third)
  entry_final  lane where it first crossed x=80 (into the final third)

A route is the pair (entry_mid, entry_final): 25 route types, which is coarse
enough to count and still says something a coach recognises ("up the left
half-space, into the box from the left wing"). Lanes are in the attacking team's
frame; with StatsBomb's y-axis, low y is the team's LEFT.
"""

from __future__ import annotations

import polars as pl

LANES = ["wide_left", "halfspace_left", "centre", "halfspace_right", "wide_right"]
# Lane edges on the 0-80 y-axis: wide lanes are touchline to the edge of the
# 18-yard box (y=18 / y=62); half-spaces run from there to the edge of the
# 6-yard box (y=30 / y=50).
LANE_EDGES = [18.0, 30.0, 50.0, 62.0]
MID_LINE, FINAL_LINE = 40.0, 80.0


def lane_expr(y: pl.Expr) -> pl.Expr:
    e = LANE_EDGES
    return (pl.when(y < e[0]).then(pl.lit(LANES[0]))
            .when(y < e[1]).then(pl.lit(LANES[1]))
            .when(y < e[2]).then(pl.lit(LANES[2]))
            .when(y < e[3]).then(pl.lit(LANES[3]))
            .otherwise(pl.lit(LANES[4])))


def _crossing_y(line: float) -> pl.Expr:
    """y where a move's straight path crosses x=line (linear interpolation)."""
    t = (line - pl.col("x")) / (pl.col("end_x") - pl.col("x"))
    return pl.col("y") + t * (pl.col("end_y") - pl.col("y"))


def progressions(actions: pl.DataFrame) -> pl.DataFrame:
    """One row per possession that crossed at least one line, with its route.

    `actions` are one team's valued, in-possession actions with columns
    match_id, possession, idx, kind, x, y, end_x, end_y, player_id, xg_after.
    """
    moves = actions.filter(pl.col("kind") == "move")
    rows = []
    for line, name in ((MID_LINE, "mid"), (FINAL_LINE, "final")):
        crossed = (moves.filter((pl.col("x") < line) & (pl.col("end_x") >= line))
                   .sort("idx")
                   .group_by("match_id", "possession", maintain_order=True)
                   .agg(pl.first("idx").alias(f"idx_{name}"),
                        lane_expr(_crossing_y(line)).first().alias(f"entry_{name}"),
                        pl.first("player_id").alias(f"by_{name}")))
        rows.append(crossed)
    out = rows[0].join(rows[1], on=["match_id", "possession"], how="full", coalesce=True)
    outcome = actions.group_by("match_id", "possession").agg(
        started_deep=(pl.col("x").sort_by("idx").first() < MID_LINE),
        xg=pl.col("xg_after").max(),
        shot=(pl.col("kind") == "shot").any(),
    )
    return out.join(outcome, on=["match_id", "possession"], how="left")


def route_table(prog: pl.DataFrame) -> pl.DataFrame:
    """Frequency and outcome of each full route (entered middle, then final third)."""
    full = prog.filter(pl.col("entry_mid").is_not_null() & pl.col("entry_final").is_not_null())
    total = max(full.height, 1)
    return (full.group_by("entry_mid", "entry_final")
                .agg(n=pl.len(), shot_rate=pl.col("shot").mean(), xg=pl.col("xg").mean())
                .with_columns(share=pl.col("n") / total)
                .sort("n", descending=True))


def lane_shares(prog: pl.DataFrame, line: str) -> dict:
    """Share of crossings of one line (`mid` or `final`) by lane."""
    col = f"entry_{line}"
    s = prog.filter(pl.col(col).is_not_null())
    total = max(s.height, 1)
    counts = dict(s.group_by(col).len().iter_rows())
    return {lane: counts.get(lane, 0) / total for lane in LANES}
