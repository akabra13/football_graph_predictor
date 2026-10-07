"""Matchups: one team's attacking flow graph against another's defensive one.

B's conceded chain records what opponents managed against B. Dividing it by the
league chain gives B's LEAKINESS on every edge: above 1 where teams find that
move easier against B than against an average side, below 1 where B shuts it
down. The matchup chain applies B's leakiness to A's own tendencies:

    P_AB[i, k]  proportional to  P_A[i, k] * clip(Q_B[i, k] / P_L[i, k])

then renormalises each row. Shot quality and possession starts are adjusted
the same way. This is a deliberately simple, multiplicative interaction: it
says A keeps its habits, and B makes some of them easier and some harder.

`entry_lanes` turns any chain into the share of final-third entries expected in
each lane, which is what the headline experiment compares with reality.
"""

from __future__ import annotations

import numpy as np

from pitchgraph.chains.team import Chain
from pitchgraph.graphs.routes import LANE_EDGES, LANES

CLIP = (0.25, 4.0)


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    r = np.divide(a, b, out=np.ones_like(a, dtype=float), where=b > 0)
    return np.clip(r, *CLIP)


def matchup_chain(attack: Chain, conceded: Chain, league: Chain) -> Chain:
    P = attack.P * _ratio(conceded.P, league.P)
    P = P / P.sum(1, keepdims=True)
    g = attack.g * _ratio(conceded.g, league.g)
    start = attack.start * _ratio(conceded.start, league.start)
    return Chain(P, g, start / start.sum(), attack.grid)


def entry_lanes(chain: Chain, line: float = 80.0) -> np.ndarray:
    """Expected share of entries across x=line by lane (LANES order)."""
    c = chain.grid.centres()
    crossing = (c[:, 0][:, None] < line) & (c[:, 0][None, :] >= line)
    flow = chain.visits()[:, None] * chain.move * crossing
    # Lane of the crossing point, interpolating between the two zone centres.
    t = (line - c[:, 0][:, None]) / (c[:, 0][None, :] - c[:, 0][:, None] + 1e-9)
    y = c[:, 1][:, None] + t * (c[:, 1][None, :] - c[:, 1][:, None])
    lane = np.searchsorted(LANE_EDGES, y, side="right")
    shares = np.array([flow[lane == k].sum() for k in range(len(LANES))])
    return shares / shares.sum() if shares.sum() > 0 else np.full(len(LANES), 1 / len(LANES))
