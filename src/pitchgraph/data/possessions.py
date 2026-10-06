"""Possession context for every event.

Adds, per event:
  in_possession   the event's team is the team in possession
  xg_after        xG of the possession team's shots from this event to the end of
                  the possession (the "what did this lead to" target)
  goal_after      the possession went on to score from this event onwards
  pos_start_x     where the possession began (in the possession team's frame)
  pos_seconds     seconds since the possession began
  phase           build_up | progression | final_third, by the event's x
  transition      within TRANSITION_SECONDS of a possession won in open play
  restart         the event IS a set-piece delivery (corner, free kick, throw-in,
                  goal kick, kick off), else null

Note on set pieces: StatsBomb's `play_pattern` labels how a POSSESSION began,
not what an event is. "From Free Kick" tags every event in that possession, and
v1 measured that naive exclusion drops ~25% of open play. So only the delivery
itself is marked (`restart`), from the pass sub-type.

Coordinates stay in the event team's frame (attacking toward x=120), which for
in-possession events is the possession team's own frame.
"""

from __future__ import annotations

import polars as pl

TRANSITION_SECONDS = 10.0
RESTARTS = ["Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"]
REGAIN_TYPES = ["Ball Recovery", "Interception", "Duel", "Block", "Clearance",
                "Goal Keeper", "Pressure", "Foul Won", "Dispossessed", "Miscontrol"]


def _clock():
    # Seconds since kick-off of the period, ordered across periods.
    return pl.col("period") * 10_000 + pl.col("period_seconds")


def add_possession_context(events: pl.LazyFrame) -> pl.LazyFrame:
    key = ["match_id", "possession"]
    ev = events.with_columns(
        in_possession=pl.col("team_id") == pl.col("possession_team_id"),
        clock=_clock(),
    )
    shot_xg = (pl.when(pl.col("in_possession") & (pl.col("type") == "Shot"))
               .then(pl.col("xg").fill_null(0.0)).otherwise(0.0))
    goal = (pl.col("in_possession") & (pl.col("type") == "Shot")
            & (pl.col("outcome") == "Goal")).cast(pl.Int32)

    ev = ev.sort(["match_id", "possession", "idx"]).with_columns(
        xg_after=shot_xg.cum_sum(reverse=True).over(key),
        goal_after=(goal.cum_sum(reverse=True).over(key) > 0),
    )

    starts = (ev.filter(pl.col("in_possession") & pl.col("x").is_not_null())
                .group_by(key)
                .agg(pos_start_x=pl.col("x").sort_by("idx").first(),
                     pos_start_clock=pl.col("clock").min(),
                     pos_first_type=pl.col("type").sort_by("idx").first(),
                     pos_xg=pl.col("xg").filter(pl.col("type") == "Shot").sum(),
                     pos_shot=(pl.col("type") == "Shot").any()))
    ev = ev.join(starts, on=key, how="left")

    # Nullable columns are filled before comparison: null.is_in(...) is null in
    # polars, which silently turns a boolean flag into a missing value.
    pattern = pl.col("play_pattern").fill_null("")
    open_play_start = pattern.is_in(["Regular Play", "From Counter"])
    won_back = pl.col("pos_first_type").fill_null("").is_in(REGAIN_TYPES) | (pattern == "From Counter")
    return ev.with_columns(
        pos_seconds=(pl.col("clock") - pl.col("pos_start_clock")),
        phase=pl.when(pl.col("x") < 40).then(pl.lit("build_up"))
               .when(pl.col("x") < 80).then(pl.lit("progression"))
               .when(pl.col("x").is_not_null()).then(pl.lit("final_third"))
               .otherwise(None),
        restart=pl.when((pl.col("type") == "Pass") & pl.col("sub_type").fill_null("").is_in(RESTARTS))
                 .then(pl.col("sub_type")).otherwise(None),
    ).with_columns(
        transition=open_play_start & won_back & (pl.col("pos_seconds") <= TRANSITION_SECONDS),
    ).drop("pos_start_clock")
