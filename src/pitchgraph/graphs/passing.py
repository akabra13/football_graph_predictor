"""Value-weighted passing graphs.

A classic passing network counts passes. Here each edge also carries the VALUE
those passes added (from any `ValueModel`), so the graph shows where a team's
threat actually flows, not just where the ball circulates. Two views:

  player graph  nodes = players, edge A->B = completed passes from A to B
  zone graph    nodes = pitch zones, edge = ball movements (passes + carries)

Both are plain networkx DiGraphs with attributes, so any graph algorithm applies.
Positions are fixed pitch coordinates (a player's median on-ball location),
never a force-directed layout.
"""

from __future__ import annotations

import networkx as nx
import polars as pl

from pitchgraph.value.markov import zone_expr


def player_graph(actions: pl.DataFrame, min_passes: int = 3) -> nx.DiGraph:
    """Player passing graph from valued actions of ONE team.

    `actions` must carry: player_id, player, recipient_id, type, kind, value, x, y.
    """
    g = nx.DiGraph()
    touches = actions.filter(pl.col("player_id").is_not_null()).group_by("player_id").agg(
        name=pl.col("player").first(),
        x=pl.col("x").median(), y=pl.col("y").median(),
        actions=pl.len(),
        value=pl.col("value").sum(),
    )
    for r in touches.iter_rows(named=True):
        g.add_node(r["player_id"], name=r["name"], x=r["x"], y=r["y"],
                   actions=r["actions"], value=r["value"])

    passes = (actions.filter((pl.col("type") == "Pass") & (pl.col("kind") == "move")
                             & pl.col("recipient_id").is_not_null())
              .group_by("player_id", "recipient_id")
              .agg(n=pl.len(), value=pl.col("value").sum(),
                   positive=pl.col("value").clip(lower_bound=0).sum()))
    for r in passes.filter(pl.col("n") >= min_passes).iter_rows(named=True):
        if r["recipient_id"] in g:
            g.add_edge(r["player_id"], r["recipient_id"], n=r["n"],
                       value=r["value"], positive=r["positive"])
    return g


def zone_graph(actions: pl.DataFrame, nx_zones: int = 6, ny_zones: int = 4) -> nx.DiGraph:
    """Coarse zone graph of ball movements (passes and carries) for one team."""
    moves = actions.filter(pl.col("kind") == "move").with_columns(
        z0=zone_expr(pl.col("x"), pl.col("y"), nx_zones, ny_zones),
        z1=zone_expr(pl.col("end_x"), pl.col("end_y"), nx_zones, ny_zones),
    )
    g = nx.DiGraph(nx=nx_zones, ny=ny_zones)
    dx, dy = 120.0 / nx_zones, 80.0 / ny_zones
    for z in range(nx_zones * ny_zones):
        g.add_node(z, x=(z // ny_zones + 0.5) * dx, y=(z % ny_zones + 0.5) * dy)
    agg = moves.group_by("z0", "z1").agg(n=pl.len(), value=pl.col("value").sum())
    for r in agg.iter_rows(named=True):
        g.add_edge(r["z0"], r["z1"], n=r["n"], value=r["value"])
    return g
