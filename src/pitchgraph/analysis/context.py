"""Per-event match context shared by every analysis module."""

from __future__ import annotations

import polars as pl

from pitchgraph.data.possessions import add_possession_context
from pitchgraph.value.base import ValueModel


def _clock():
    return pl.col("period") * 10_000 + pl.col("period_seconds")


def add_score_state(ev: pl.LazyFrame) -> pl.LazyFrame:
    """home_goals / away_goals scored BEFORE each event (own goals included).

    StatsBomb records an own goal twice: "Own Goal Against" on the conceding
    side and "Own Goal For" on the benefiting side, so the scorer of record is
    the team on the "Own Goal For" event.
    """
    is_goal = (((pl.col("type") == "Shot") & (pl.col("outcome").fill_null("") == "Goal"))
               | (pl.col("type") == "Own Goal For"))
    ev = ev.with_columns(clock=_clock()).sort("match_id", "clock", "idx")
    home = (is_goal & (pl.col("team_id") == pl.col("home_team_id"))).cast(pl.Int32)
    away = (is_goal & (pl.col("team_id") == pl.col("away_team_id"))).cast(pl.Int32)
    return ev.with_columns(
        home_goals=(home.cum_sum().over("match_id") - home),
        away_goals=(away.cum_sum().over("match_id") - away),
    )


def score_diff_for(team_id: int) -> pl.Expr:
    """Goal difference from `team_id`'s point of view, before each event."""
    return (pl.when(pl.col("home_team_id") == team_id)
              .then(pl.col("home_goals") - pl.col("away_goals"))
              .otherwise(pl.col("away_goals") - pl.col("home_goals")))


def time_bucket() -> pl.Expr:
    return (pl.when(pl.col("minute") < 30).then(pl.lit("0-30"))
              .when(pl.col("minute") < 60).then(pl.lit("30-60"))
              .otherwise(pl.lit("60-90+")))


def prepare(events: pl.LazyFrame, model: ValueModel) -> pl.DataFrame:
    """Events with possession context, score state, and action values joined on.

    Every event keeps its row; `kind` and `value` are null for events that are
    not valued actions (pressures, duels, ...).
    """
    ev = add_score_state(add_possession_context(events))
    valued = model.add_action_values(ev).select("event_id", "kind", "value", "v_start", "v_end")
    return (ev.join(valued, on="event_id", how="left")
              .with_columns(bucket=time_bucket())
              .collect())
