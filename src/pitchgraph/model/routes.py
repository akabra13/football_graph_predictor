"""Depth-limited routing over the resistance graph, and load-bearing defenders.

WHY DEPTH-LIMITED. A 360 freeze-frame is an instant, and the median gap between
frames is 1.2s. A defensive shape is only meaningful for about as long as one
ball movement takes. Routing an unbounded shortest path through a frozen shape
silently assumes the defence stands still while four consecutive passes are
played, which is not merely approximate but physically wrong - and it saturates,
because with ~96 zones there is almost always *some* chain of safe passes. Depth
2 (at most two ball movements before the shot) is what a single snapshot can
actually support.

The routing is a small Bellman-style DP over the zone cost matrix rather than a
networkx shortest path: depth-limiting is native to the DP, and it is vectorised,
which matters because the leave-one-out analysis re-solves it once per defender.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .frames import DEFENDING_GOAL
from .resistance import (
    ResistanceParams,
    ZoneGrid,
    lane_pressure,
    pass_success,
    reception_pressure,
    shot_probability,
)

INF = np.inf


@dataclass
class Route:
    """The most dangerous available route from an instant of defensive shape."""

    threat: float          # P(goal) via the best route, 0 if none
    cost: float            # -log(threat)
    zones: list            # zone indices traversed, ball zone first
    points: np.ndarray     # (K, 2) pitch coordinates, ending at the goal
    hops: int              # number of ball movements before the shot
    observability: float   # fraction of the ball->goal corridor observed

    @property
    def is_direct_shot(self) -> bool:
        return self.hops == 0


class RouteSolver:
    """Builds the zone cost matrix for a snapshot and solves depth-limited routes.

    The cost matrix is the expensive part and depends only on defender positions,
    so it is built once and reused across queries.
    """

    def __init__(self, snapshot, params=None, grid=None, defenders=None,
                 hop_penalty: float = 0.0):
        self.snap = snapshot
        self.p = params or ResistanceParams()
        self.grid = grid or ZoneGrid(self.p.nx_zones, self.p.ny_zones)
        self.defenders = snapshot.defenders if defenders is None else defenders
        self.observed = snapshot.is_visible(self.grid.centres)
        # Optional extra cost per hop, representing the defence re-setting
        # between actions. Off by default; depth-limiting already handles this.
        self.hop_penalty = hop_penalty
        self._build_costs()

    def _build_costs(self):
        c = self.grid.centres
        p = self.p
        n = self.grid.n

        dist = np.linalg.norm(c[None, :, :] - c[:, None, :], axis=2)
        feasible = (dist > 1e-9) & (dist <= p.max_pass)
        feasible &= self.observed[:, None] & self.observed[None, :]

        C = np.full((n, n), INF)
        src, dst = np.nonzero(feasible)
        if len(src):
            lane = lane_pressure(c[src], c[dst], self.defenders, p.lane_sigma)
            recv = reception_pressure(c[dst], self.defenders, p.reception_sigma)
            succ = np.clip(pass_success(lane, recv, dist[src, dst]),
                           p.min_success, 1.0)
            C[src, dst] = -np.log(succ) + self.hop_penalty
        self.C = C

        shot = np.clip(shot_probability(c), p.min_success, 1.0)
        S = -np.log(shot)
        S[~self.observed] = INF
        self.S = S

    def solve(self, max_hops: int = 2):
        """Value iteration to a fixed depth.

        V_k[i] = min(shoot from i, min_j cost(i->j) + V_{k-1}[j])
        """
        V = self.S.copy()
        choice = [np.full(self.grid.n, -1, dtype=int)]  # -1 means "shoot"
        for _ in range(max_hops):
            total = self.C + V[None, :]           # (i, j)
            j_best = np.argmin(total, axis=1)
            v_move = total[np.arange(self.grid.n), j_best]
            take_move = v_move < V
            nxt = np.where(take_move, j_best, -1)
            V = np.where(take_move, v_move, V)
            choice.append(nxt)
        self._V, self._choice = V, choice
        return V

    def best_route(self, max_hops: int = 2, from_point=None) -> Route:
        V = self.solve(max_hops)
        start_pt = self.snap.ball if from_point is None else np.asarray(from_point)
        start = self.grid.index_of(start_pt)

        obs = self.corridor_observability()
        if not self.observed[start] or not np.isfinite(V[start]):
            return Route(0.0, INF, [], np.zeros((0, 2)), 0, obs)

        # Walk the policy from the deepest layer back to a shot.
        zones, node, layer = [start], start, max_hops
        while layer > 0:
            nxt = self._choice[layer][node]
            if nxt < 0:
                break
            zones.append(int(nxt))
            node, layer = int(nxt), layer - 1

        pts = [self.grid.centres[z] for z in zones] + [DEFENDING_GOAL]
        return Route(
            threat=float(np.exp(-V[start])),
            cost=float(V[start]),
            zones=zones,
            points=np.array(pts),
            hops=len(zones) - 1,
            observability=obs,
        )

    def corridor_observability(self) -> float:
        """Fraction observed in the band from the ball forward to the goal."""
        band = self.grid.centres[:, 0] >= (self.snap.ball[0] - 5.0)
        if band.sum() == 0:
            return 0.0
        return float(self.observed[band].mean())

    # -- who is holding the block together ---------------------------------
    def load_bearing(self, max_hops: int = 2):
        """Leave-one-out defender importance, as the threat increase without them.

        Note this is legitimate *within a snapshot* in a way that removing a
        player from a whole-match graph is not: over an instant there is no time
        for the defence to reorganise, so the counterfactual "this defender is
        not there" really does hold the rest of the shape fixed.
        """
        base = self.best_route(max_hops).threat
        out = []
        for k in range(len(self.defenders)):
            keep = np.delete(self.defenders, k, axis=0)
            solver = RouteSolver(self.snap, self.p, self.grid, defenders=keep,
                                 hop_penalty=self.hop_penalty)
            out.append(solver.best_route(max_hops).threat - base)
        return np.array(out)
