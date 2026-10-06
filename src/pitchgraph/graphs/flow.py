"""Who the team's threat flows through.

Two measures, both deliberately simpler than graph centralities (v1 showed that
betweenness on a pass graph describes circulation, not danger):

  involvement  share of the team's positive value added in which the player took
               part: as the actor (pass, carry, shot) or as the pass receiver
  dependency   share of the team's progressions into the final third in which the
               player touched the ball on the way. It is the node-removal
               counterfactual stated honestly: "this share of progressions ran
               through them", NOT "this share would vanish without them" - real
               teams reorganise, and this data cannot say how.
"""

from __future__ import annotations

import polars as pl


def involvement(actions: pl.DataFrame) -> pl.DataFrame:
    pos = actions.with_columns(v=pl.col("value").clip(lower_bound=0.0))
    total = float(pos["v"].sum()) or 1.0
    as_actor = pos.group_by("player_id").agg(v_actor=pl.col("v").sum())
    as_recv = (pos.filter(pl.col("recipient_id").is_not_null())
                  .group_by(pl.col("recipient_id").alias("player_id"))
                  .agg(v_recv=pl.col("v").sum()))
    names = (actions.filter(pl.col("player_id").is_not_null())
                    .group_by("player_id").agg(player=pl.first("player"),
                                               actions=pl.len()))
    out = (names.join(as_actor, on="player_id", how="left")
                .join(as_recv, on="player_id", how="left")
                # Fill only the value columns: a frame-wide fill_null(0.0)
                # silently casts the integer player_id to float.
                .with_columns(pl.col("v_actor", "v_recv").fill_null(0.0)))
    # A pass's value is credited to both ends, so shares can sum past 1.
    return out.with_columns(
        involvement=(pl.col("v_actor") + pl.col("v_recv")) / total,
        created=pl.col("v_actor") / total,
    ).sort("involvement", descending=True)


def dependency(actions: pl.DataFrame, prog: pl.DataFrame) -> pl.DataFrame:
    """Share of final-third entries whose build-up the player touched."""
    entries = prog.filter(pl.col("idx_final").is_not_null()).select(
        "match_id", "possession", "idx_final")
    n = max(entries.height, 1)
    touched = (actions.filter(pl.col("player_id").is_not_null())
                      .join(entries, on=["match_id", "possession"])
                      .filter(pl.col("idx") <= pl.col("idx_final"))
                      .group_by("player_id")
                      .agg(pl.struct("match_id", "possession").n_unique().alias("k")))
    return touched.with_columns(dependency=pl.col("k") / n).drop("k")
