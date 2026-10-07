"""Team flow graphs: absorbing Markov chains estimated per team, shrunk to the league.

A team's season is a graph: zones are nodes, and from each zone the team moves
the ball along an edge, shoots, or loses it. Estimated from one team's matches
alone, most rows of that graph are thin (a few dozen actions per zone), so each
row is shrunk toward the league's row:

    P_team[i] = (counts_team[i] + kappa * P_league[i]) / (N_team[i] + kappa)

kappa is in units of "pseudo-actions": a zone where the team made 10 actions
and kappa = 30 is mostly league; one with 500 actions is mostly team. kappa is
not chosen by hand - `select_kappa` picks the value that best predicts each
team's held-out matches.

Shot quality per zone (mean xG per shot) is shrunk the same way with its own
weight, in units of shots.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pitchgraph.chains.counts import TeamCounts
from pitchgraph.chains.grid import Grid
from pitchgraph.value.markov import solve_values

KAPPA_GRID = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)
KAPPA_XG = 10.0
LEAGUE_PRIOR_TURNOVERS = 1.0


@dataclass
class Chain:
    """An absorbing chain over n zones. Rows of P: n move columns, shot, lose."""

    P: np.ndarray            # (n, n + 2), rows sum to 1
    g: np.ndarray            # (n,) mean xG of a shot from each zone
    start: np.ndarray        # (n,) where possessions begin, sums to 1
    grid: Grid
    _values: np.ndarray | None = field(default=None, repr=False)

    @property
    def n(self) -> int:
        return self.grid.n

    @property
    def move(self) -> np.ndarray:
        return self.P[:, : self.n]

    @property
    def shoot(self) -> np.ndarray:
        return self.P[:, self.n]

    @property
    def lose(self) -> np.ndarray:
        return self.P[:, self.n + 1]

    @property
    def values(self) -> np.ndarray:
        """P(goal) from each zone: the chain's exact absorption value."""
        if self._values is None:
            self._values = solve_values(self.move, self.shoot, self.g)
        return self._values

    @property
    def threat(self) -> float:
        """Expected goals per possession: start distribution x zone values."""
        return float(self.start @ self.values)

    def visits(self) -> np.ndarray:
        """Expected number of actions in each zone per possession."""
        return np.linalg.solve((np.eye(self.n) - self.move).T, self.start)

    def with_P(self, P: np.ndarray) -> "Chain":
        """Same chain with a different transition matrix (denial, matchup)."""
        return Chain(P, self.g, self.start, self.grid)


def _normalise(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.full_like(v, 1.0 / len(v))


def league_chain(C: np.ndarray, xg: np.ndarray, starts: np.ndarray, grid: Grid) -> Chain:
    """The pooled chain every team is shrunk toward.

    A small turnover prior keeps every row a proper distribution, even for a
    zone the whole league never acted in.
    """
    n = grid.n
    C = C.astype(float).copy()
    C[:, n + 1] += LEAGUE_PRIOR_TURNOVERS
    P = C / C.sum(1, keepdims=True)
    shots = C[:, n]
    g = np.divide(xg, shots, out=np.zeros(n), where=shots > 0)
    return Chain(P, g, _normalise(starts.astype(float)), grid)


def shrunk_chain(C: np.ndarray, xg: np.ndarray, starts: np.ndarray,
                 prior: Chain, kappa: float, kappa_xg: float = KAPPA_XG) -> Chain:
    """A team's chain: its own counts, shrunk row by row toward `prior`."""
    n = prior.n
    C = C.astype(float)
    N = C.sum(1, keepdims=True)
    P = (C + kappa * prior.P) / (N + kappa)
    shots = C[:, n]
    g = (xg + kappa_xg * prior.g) / (shots + kappa_xg)
    # Possession starts are shrunk too, in units of possessions.
    start = _normalise(starts.astype(float) + kappa * prior.start)
    return Chain(P, g, start, prior.grid)


def team_chain(tc: TeamCounts, prior: Chain, kappa: float,
               keep: np.ndarray | None = None) -> Chain:
    C, xg, st = tc.total(keep)
    return shrunk_chain(C, xg, st, prior, kappa)


def heldout_loglik(tc: TeamCounts, prior: Chain, kappa: float) -> tuple[float, float]:
    """Leave-one-match-out log-likelihood of a team's transitions under kappa.

    Returns (total log-likelihood, number of actions scored).
    """
    C_all = tc.C.astype(float)
    total = C_all.sum(0)
    ll, n_obs = 0.0, 0.0
    for m in range(tc.n_matches):
        held = C_all[m]
        rest = total - held
        P = (rest + kappa * prior.P) / (rest.sum(1, keepdims=True) + kappa)
        mask = held > 0
        ll += float((held[mask] * np.log(np.clip(P[mask], 1e-12, None))).sum())
        n_obs += float(held.sum())
    return ll, n_obs


def select_kappa(teams: list[TeamCounts], prior: Chain,
                 grid=KAPPA_GRID) -> tuple[float, dict]:
    """The kappa that best predicts each team's held-out matches, pooled."""
    scores = {}
    for k in grid:
        ll = obs = 0.0
        for tc in teams:
            if tc.n_matches < 3:
                continue
            a, b = heldout_loglik(tc, prior, k)
            ll, obs = ll + a, obs + b
        scores[k] = ll / max(obs, 1.0)
    best = max(scores, key=scores.get)
    return best, scores
