"""The defensive resistance graph.

This is the load-bearing idea of the project. Rather than describing how a team
passes, we model how hard it is to move the ball THROUGH a defensive shape.

Construction, per snapshot:
  nodes  = pitch-zone centres, plus a virtual GOAL node
  edges  = feasible ball movements between zones
  cost   = -log P(the movement succeeds against the visible defenders)

Because costs are negative log-probabilities, the shortest path from the ball to
GOAL is exactly the most likely route to a goal, and its total cost converts back
to a probability. "How vulnerable is this defence right now" therefore has units
rather than being an index with invented weights.

Every constant below is FITTED, not chosen:
  * pass completion - logistic over lane pressure, reception pressure and length,
    fit on 20,354 labelled passes carrying a 360 frame (AUC 0.882, Brier 0.102
    vs 0.145 baseline). See scripts/fit_pass_model.py.
  * shot probability - log-linear in distance and lateral offset, fit against 654
    non-penalty StatsBomb xG values (corr 0.72). See scripts/fit_shot_model.py.

Censoring is handled by refusing to answer rather than guessing: zones outside
the camera polygon are unobserved, and a route through them is not evidence of a
gap. Results carry observability so downstream analysis can filter on it.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from .frames import DEFENDING_GOAL, PITCH_LENGTH, PITCH_WIDTH, Snapshot

GOAL = "GOAL"

# --- fitted pass-completion model (scripts/fit_pass_model.py) ---------------
LANE_SIGMA = 1.25
RECV_SIGMA = 3.0
PASS_INTERCEPT = 3.4747
PASS_LANE_COEF = -1.4393
PASS_RECV_COEF = -3.0287
PASS_LEN_COEF = -0.0141
PASS_LEN2_COEF = -0.0533

# --- fitted shot model (scripts/fit_shot_model.py) --------------------------
SHOT_INTERCEPT = -0.9316
SHOT_DIST_COEF = -0.08619
SHOT_LATERAL_COEF = -0.04681


@dataclass(frozen=True)
class ResistanceParams:
    nx_zones: int = 12
    ny_zones: int = 8
    max_pass: float = 45.0
    lane_sigma: float = LANE_SIGMA
    reception_sigma: float = RECV_SIGMA
    min_success: float = 1e-4


class ZoneGrid:
    """Fixed pitch discretisation. Never force-directed, always pitch coordinates."""

    def __init__(self, nx_zones: int = 12, ny_zones: int = 8):
        self.nx, self.ny = nx_zones, ny_zones
        self.dx = PITCH_LENGTH / nx_zones
        self.dy = PITCH_WIDTH / ny_zones
        xs = (np.arange(nx_zones) + 0.5) * self.dx
        ys = (np.arange(ny_zones) + 0.5) * self.dy
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        self.centres = np.column_stack([gx.ravel(), gy.ravel()])
        self.n = len(self.centres)

    def index_of(self, point):
        i = int(np.clip(point[0] // self.dx, 0, self.nx - 1))
        j = int(np.clip(point[1] // self.dy, 0, self.ny - 1))
        return i * self.ny + j


def lane_pressure(starts, ends, defenders, sigma=LANE_SIGMA):
    """Summed defender interference along each start->end segment.

    A defender counts by perpendicular distance to the segment, but only within
    the span of that segment: someone behind the passer, or beyond the target,
    is not in the way.
    """
    if len(defenders) == 0:
        return np.zeros(len(starts))
    seg = ends - starts
    length2 = np.maximum(np.einsum("ij,ij->i", seg, seg), 1e-9)
    rel = defenders[None, :, :] - starts[:, None, :]
    t = np.clip(np.einsum("edk,ek->ed", rel, seg) / length2[:, None], 0.0, 1.0)
    closest = starts[:, None, :] + t[:, :, None] * seg[:, None, :]
    perp = np.linalg.norm(defenders[None, :, :] - closest, axis=2)
    return np.exp(-0.5 * (perp / sigma) ** 2).sum(axis=1)


def reception_pressure(ends, defenders, sigma=RECV_SIGMA):
    """Pressure on the receiving zone from the nearest defender (0 = free)."""
    if len(defenders) == 0:
        return np.zeros(len(ends))
    d = np.linalg.norm(ends[:, None, :] - defenders[None, :, :], axis=2)
    return np.exp(-0.5 * (d.min(axis=1) / sigma) ** 2)


def pass_success(lane, recv, length):
    """Fitted P(pass completes) given lane pressure, reception pressure, length."""
    z = (
        PASS_INTERCEPT
        + PASS_LANE_COEF * lane
        + PASS_RECV_COEF * recv
        + PASS_LEN_COEF * length
        + PASS_LEN2_COEF * (length ** 2) / 100.0
    )
    return 1.0 / (1.0 + np.exp(-z))


def shot_probability(points):
    """Fitted P(goal) if a shot is taken from each point."""
    d = np.linalg.norm(points - DEFENDING_GOAL, axis=1)
    lateral = np.abs(points[:, 1] - DEFENDING_GOAL[1])
    return np.clip(
        np.exp(SHOT_INTERCEPT + SHOT_DIST_COEF * d + SHOT_LATERAL_COEF * lateral),
        1e-6,
        0.999,
    )


class ResistanceGraph:
    """A defensive resistance graph built from one snapshot."""

    def __init__(self, snapshot, params=None, grid=None, defenders=None):
        self.snap = snapshot
        self.p = params or ResistanceParams()
        self.grid = grid or ZoneGrid(self.p.nx_zones, self.p.ny_zones)
        # `defenders` override supports leave-one-out without rebuilding the grid.
        self.defenders = snapshot.defenders if defenders is None else defenders
        self.observed = snapshot.is_visible(self.grid.centres)
        self.graph = self._build()

    def _build(self):
        c = self.grid.centres
        p = self.p
        g = nx.DiGraph()

        dist = np.linalg.norm(c[None, :, :] - c[:, None, :], axis=2)
        # All movements within range, including lateral: switches are one of the
        # vulnerability types we look for. Costs are strictly positive, so
        # Dijkstra never routes through a cycle.
        feasible = (dist > 1e-9) & (dist <= p.max_pass)
        # A route may only be claimed through pitch we actually observed.
        feasible &= self.observed[:, None] & self.observed[None, :]

        src, dst = np.nonzero(feasible)
        if len(src) == 0:
            return g

        lane = lane_pressure(c[src], c[dst], self.defenders, p.lane_sigma)
        recv = reception_pressure(c[dst], self.defenders, p.reception_sigma)
        succ = np.clip(pass_success(lane, recv, dist[src, dst]), p.min_success, 1.0)

        g.add_weighted_edges_from(
            zip(src.tolist(), dst.tolist(), (-np.log(succ)).tolist())
        )

        shot_cost = -np.log(np.clip(shot_probability(c), p.min_success, 1.0))
        for i in np.nonzero(self.observed)[0]:
            g.add_edge(int(i), GOAL, weight=float(shot_cost[i]))
        return g

    def best_route(self, from_point=None):
        """Cheapest route from the ball to GOAL as (cost, path, probability)."""
        start_pt = self.snap.ball if from_point is None else np.asarray(from_point)
        start = self.grid.index_of(start_pt)
        if start not in self.graph or not self.observed[start]:
            return float("inf"), [], 0.0
        try:
            cost, path = nx.single_source_dijkstra(
                self.graph, start, GOAL, weight="weight"
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return float("inf"), [], 0.0
        return float(cost), path, float(np.exp(-cost))

    @property
    def observability(self):
        """Fraction of the whole pitch grid inside the camera polygon."""
        return float(self.observed.mean())

    def corridor_observability(self):
        """Fraction observed in the band between the ball and the goal.

        This is the number that matters. Whole-pitch observability is low simply
        because the camera ignores the far half, which says nothing about whether
        we can assess the route in front of the ball.
        """
        c = self.grid.centres
        band = c[:, 0] >= (self.snap.ball[0] - 5.0)
        if band.sum() == 0:
            return 0.0
        return float(self.observed[band].mean())

    def route_points(self, path):
        pts = [self.grid.centres[i] for i in path if i != GOAL]
        if path and path[-1] == GOAL:
            pts.append(DEFENDING_GOAL)
        return np.array(pts) if pts else np.zeros((0, 2))
