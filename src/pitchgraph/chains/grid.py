"""Pitch grids for team flow graphs, including non-uniform ones.

The default is the TACTICAL grid: six 20-yard bands up the pitch x the five
lanes coaches use (wide, half-space, centre, half-space, wide). It was chosen on
evidence, not taste. On Premier League 2015/16, a 12x8 grid gave team chains
that barely beat the league average on held-out matches (+0.55 milli-nats per
action) and re-identified 25% of teams from half a season. A 6x4 grid gained
+3.36 and re-identified 100%: at fine resolution a team's habits are mostly
noise. A uniform 6x4 grid, though, puts its row centres exactly on lane edges,
so the tactical grid keeps that coarseness while aligning with the lanes.

Coordinates are the attacking team's frame (x toward goal, low y = its left).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from pitchgraph.graphs.routes import LANE_EDGES

PITCH_X, PITCH_Y = 120.0, 80.0


@dataclass(frozen=True)
class Grid:
    x_edges: tuple   # interior x boundaries, ascending
    y_edges: tuple   # interior y boundaries, ascending
    name: str = ""

    @classmethod
    def uniform(cls, nx: int, ny: int) -> "Grid":
        return cls(tuple(PITCH_X / nx * k for k in range(1, nx)),
                   tuple(PITCH_Y / ny * k for k in range(1, ny)), f"{nx}x{ny}")

    @property
    def nx(self) -> int:
        return len(self.x_edges) + 1

    @property
    def ny(self) -> int:
        return len(self.y_edges) + 1

    @property
    def n(self) -> int:
        return self.nx * self.ny

    def index_expr(self, x: pl.Expr, y: pl.Expr) -> pl.Expr:
        """Zone index (column * ny + row) as a polars expression."""
        zx = pl.sum_horizontal([(x >= e).cast(pl.Int32) for e in self.x_edges]) if self.x_edges else pl.lit(0)
        zy = pl.sum_horizontal([(y >= e).cast(pl.Int32) for e in self.y_edges]) if self.y_edges else pl.lit(0)
        return (zx * self.ny + zy).cast(pl.Int32)

    def index(self, x, y) -> np.ndarray:
        zx = np.searchsorted(self.x_edges, x, side="right")
        zy = np.searchsorted(self.y_edges, y, side="right")
        return zx * self.ny + zy

    def centres(self) -> np.ndarray:
        xb = np.concatenate([[0.0], self.x_edges, [PITCH_X]])
        yb = np.concatenate([[0.0], self.y_edges, [PITCH_Y]])
        xc, yc = (xb[:-1] + xb[1:]) / 2, (yb[:-1] + yb[1:]) / 2
        i, j = np.divmod(np.arange(self.n), self.ny)
        return np.column_stack([xc[i], yc[j]])

    def bounds(self) -> np.ndarray:
        """(n, 4) array of x0, x1, y0, y1 per zone, for drawing."""
        xb = np.concatenate([[0.0], self.x_edges, [PITCH_X]])
        yb = np.concatenate([[0.0], self.y_edges, [PITCH_Y]])
        i, j = np.divmod(np.arange(self.n), self.ny)
        return np.column_stack([xb[i], xb[i + 1], yb[j], yb[j + 1]])


TACTICAL = Grid((20.0, 40.0, 60.0, 80.0, 100.0), tuple(LANE_EDGES), "tactical 6x5")
