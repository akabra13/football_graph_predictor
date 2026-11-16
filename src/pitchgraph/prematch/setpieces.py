"""Set-piece calls: what about corners and free kicks is knowable before kick-off?

Design and reading rules: docs/set_pieces.md.
"""
from __future__ import annotations

import polars as pl

FEATURES = ["corners", "att_free_kicks", "sp_shots", "sp_xg", "sp_xg_share", "shots_per_corner"]
LABELS = {
    "corners": "Corners",
    "att_free_kicks": "Free kicks in the final third",
    "sp_shots": "Shots from set pieces",
    "sp_xg": "xG from set pieces",
    "sp_xg_share": "Set-piece share of threat",
    "shots_per_corner": "Shots per corner",
}
SET_PIECE = ["From Corner", "From Free Kick"]
LINE = 80.0


def setpiece_table(ev) -> pl.DataFrame:
    """One row per team-match with every candidate call.

    `ev` is one competition-season of `Lake.events()` (lazy or not). A team
    with no shots has no set-piece share; a team with no corners has no
    shots per corner (both NaN, skipped by the calls).
    """
    kind = pl.col("sub_type").fill_null("")
    shot = (pl.col("type") == "Shot") & (pl.col("period") <= 4) & (kind != "Penalty")
    from_sp = shot & pl.col("play_pattern").is_in(SET_PIECE)
    t = (ev.lazy().filter(pl.col("period") <= 4).group_by("match_id", "team_id").agg(
        corners=((pl.col("type") == "Pass") & (kind == "Corner")).sum(),
        att_free_kicks=(pl.col("type").is_in(["Pass", "Shot"]) & (kind == "Free Kick")
                        & (pl.col("x").fill_null(0.0) >= LINE)).sum(),
        sp_shots=from_sp.sum(),
        sp_xg=pl.when(from_sp).then(pl.col("xg").fill_null(0.0)).otherwise(0.0).sum(),
        corner_shots=(shot & (pl.col("play_pattern") == "From Corner")).sum(),
        xg_all=pl.when(shot).then(pl.col("xg").fill_null(0.0)).otherwise(0.0).sum(),
    ).collect())
    nan = float("nan")
    opp = t.select("match_id", pl.col("team_id").alias("opp_id"))
    t = (t.join(opp, on="match_id").filter(pl.col("team_id") != pl.col("opp_id"))
         .with_columns(
             pl.col("corners", "att_free_kicks", "sp_shots").cast(pl.Float64),
             sp_xg_share=pl.when(pl.col("xg_all") > 0).then(pl.col("sp_xg") / pl.col("xg_all")).otherwise(nan),
             shots_per_corner=pl.when(pl.col("corners") > 0)
             .then(pl.col("corner_shots") / pl.col("corners")).otherwise(nan)))
    return t.select("match_id", "team_id", "opp_id", *FEATURES).sort("match_id", "team_id")
