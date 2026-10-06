"""How a team presses, as a graph and as a few coach-legible facts.

  co-pressing graph  nodes = the team's players; edge A-B weighted by how often
                     one pressed within PAIR_SECONDS of the other in the same
                     opponent possession. Dense edges are the units that press
                     together (e.g. 9 + 10 jumping the centre-backs together).
  press starts       where the first pressure of an opponent possession happens
  who they press     the position of the opponent player on the ball when the
                     press starts (from the opponent's under-pressure event)
  recoveries         where they win the ball back
  PPDA               opponent passes allowed per defensive action in the
                     opponent's 60% of the pitch: lower = more intense

All coordinates are in the pressing team's own frame (attacking toward x=120),
so a high x means pressing high up the pitch.
"""

from __future__ import annotations

import networkx as nx
import polars as pl

PAIR_SECONDS = 2.0
DEFENSIVE_ACTIONS = ["Interception", "Foul Committed"]


def _clock():
    return pl.col("period") * 10_000 + pl.col("period_seconds")


def pressures(events: pl.DataFrame, team_id: int) -> pl.DataFrame:
    return (events.filter((pl.col("type") == "Pressure") & (pl.col("team_id") == team_id))
                  .with_columns(clock=_clock())
                  .sort("match_id", "clock"))


def copress_graph(events: pl.DataFrame, team_id: int, min_pairs: int = 3) -> nx.Graph:
    pr = pressures(events, team_id).select("match_id", "possession", "clock",
                                            "player_id", "player", "x", "y")
    g = nx.Graph()
    nodes = pr.group_by("player_id").agg(name=pl.first("player"), n=pl.len(),
                                         x=pl.col("x").median(), y=pl.col("y").median())
    for r in nodes.iter_rows(named=True):
        g.add_node(r["player_id"], name=r["name"], pressures=r["n"], x=r["x"], y=r["y"])
    a = pr.rename({"clock": "c1", "player_id": "p1"}).select("match_id", "possession", "c1", "p1")
    b = pr.rename({"clock": "c2", "player_id": "p2"}).select("match_id", "possession", "c2", "p2")
    pairs = (a.join(b, on=["match_id", "possession"])
              .filter((pl.col("c2") > pl.col("c1")) & (pl.col("c2") - pl.col("c1") <= PAIR_SECONDS)
                      & (pl.col("p1") != pl.col("p2")))
              .with_columns(lo=pl.min_horizontal("p1", "p2"), hi=pl.max_horizontal("p1", "p2"))
              .group_by("lo", "hi").len())
    for r in pairs.filter(pl.col("len") >= min_pairs).iter_rows(named=True):
        g.add_edge(r["lo"], r["hi"], weight=r["len"])
    return g


def press_starts(events: pl.DataFrame, team_id: int) -> pl.DataFrame:
    """First pressure of each opponent possession, with who was pressed."""
    first = (pressures(events, team_id)
             .group_by("match_id", "possession", maintain_order=True)
             .agg(pl.first("clock"), pl.first("x"), pl.first("y"), pl.first("player")))
    target = (events.filter((pl.col("team_id") != team_id) & pl.col("under_pressure")
                            & pl.col("position").is_not_null())
                    .with_columns(clock=_clock())
                    .select("match_id", "possession", pl.col("clock").alias("t_clock"),
                            pl.col("position").alias("pressed_position")))
    joined = (first.join(target, on=["match_id", "possession"], how="left")
                   .with_columns(gap=(pl.col("t_clock") - pl.col("clock")).abs())
                   .sort("gap")
                   .group_by("match_id", "possession", maintain_order=True)
                   .agg(pl.first("x"), pl.first("y"), pl.first("player"),
                        pl.when(pl.first("gap") <= 1.5).then(pl.first("pressed_position"))
                          .otherwise(None).alias("pressed_position")))
    return joined


def recoveries(events: pl.DataFrame, team_id: int) -> pl.DataFrame:
    fail = pl.col("outcome").fill_null("")
    won = ((pl.col("type") == "Ball Recovery")
           | ((pl.col("type") == "Interception") & ~fail.is_in(["Lost", "Lost In Play", "Lost Out"])))
    return events.filter((pl.col("team_id") == team_id) & won & pl.col("x").is_not_null())


def ppda(events: pl.DataFrame, team_id: int) -> pl.DataFrame:
    """PPDA per match. Opponent frame x<72 is the team's frame x>48."""
    opp_passes = (events.filter((pl.col("team_id") != team_id) & (pl.col("type") == "Pass")
                                & (pl.col("x") < 72))
                        .group_by("match_id").agg(passes=pl.len()))
    sub = pl.col("sub_type").fill_null("")
    defn = (events.filter((pl.col("team_id") == team_id) & (pl.col("x") > 48)
                          & (pl.col("type").is_in(DEFENSIVE_ACTIONS)
                             | ((pl.col("type") == "Duel") & (sub == "Tackle"))))
                  .group_by("match_id").agg(def_actions=pl.len()))
    return (opp_passes.join(defn, on="match_id", how="left").fill_null(0)
                      .with_columns(ppda=pl.col("passes") / pl.col("def_actions").clip(lower_bound=1)))
