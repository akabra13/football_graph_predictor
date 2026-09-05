"""What was actually ON OFFER to the attacking team at an instant.

The zone-grid resistance graph in `routes.py` answers a structural question:
where is this defensive shape weak, regardless of who happens to be standing
there. That is the right question for "is this team vulnerable", but on its own
it over-states danger, because it will happily route the ball through a zone
containing no attacker at all.

This module answers the complementary question: given where the attacking
players actually are, what was the most dangerous thing available? A pass can
only go to a team-mate, and the freeze-frame tells us where the team-mates were.

The two measures together are the point:

    structural threat  - the hole exists
    available threat   - this attack was positioned to use it
    the gap between    - a weakness this particular opponent could not exploit

That gap is precisely the "can player/team X take advantage of it" question,
and it is why both measures are computed rather than just the flattering one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .frames import DEFENDING_GOAL
from .resistance import (
    ResistanceParams,
    lane_pressure,
    pass_success,
    reception_pressure,
    shot_probability,
)


@dataclass
class Option:
    """One concrete attacking option available at an instant."""

    threat: float           # P(goal) if this option is taken
    target: np.ndarray      # (2,) where the ball would go first
    via: np.ndarray | None  # (2,) second receiver for two-pass options
    hops: int
    pass_prob: float        # P(the first ball movement completes)
    shot_prob: float        # P(goal) from the finishing position


class AvailabilitySolver:
    """Depth-limited routing restricted to real team-mate positions."""

    def __init__(self, snapshot, params=None):
        self.snap = snapshot
        self.p = params or ResistanceParams()

        att = snapshot.attackers
        actor = snapshot.attacker_is_actor
        if actor is not None and len(actor) == len(att) and actor.any():
            att = att[~actor]
        # Only count team-mates the camera actually saw; an unseen team-mate is
        # unknown, not absent.
        if len(att):
            att = att[snapshot.is_visible(att)]
        self.attackers = att

    def options(self, max_hops: int = 2) -> list[Option]:
        """All available options, most dangerous first."""
        a = self.attackers
        if len(a) == 0:
            return []

        D = self.snap.defenders
        ball = self.snap.ball.reshape(1, 2)

        # First ball movement: carrier -> each team-mate.
        starts = np.repeat(ball, len(a), axis=0)
        lane = lane_pressure(starts, a, D, self.p.lane_sigma)
        recv = reception_pressure(a, D, self.p.reception_sigma)
        length = np.linalg.norm(a - ball, axis=1)
        p1 = pass_success(lane, recv, length)

        xg = shot_probability(a)
        out = [
            Option(float(p1[i] * xg[i]), a[i], None, 1, float(p1[i]), float(xg[i]))
            for i in range(len(a))
        ]

        # Shooting directly from the carrier's own position is always available.
        own = float(shot_probability(ball)[0])
        out.append(Option(own, self.snap.ball, None, 0, 1.0, own))

        if max_hops >= 2 and len(a) > 1:
            # Second movement: team-mate i -> team-mate j.
            ii, jj = np.nonzero(~np.eye(len(a), dtype=bool))
            lane2 = lane_pressure(a[ii], a[jj], D, self.p.lane_sigma)
            recv2 = reception_pressure(a[jj], D, self.p.reception_sigma)
            len2 = np.linalg.norm(a[jj] - a[ii], axis=1)
            p2 = pass_success(lane2, recv2, len2)
            threat2 = p1[ii] * p2 * xg[jj]
            for k in np.argsort(-threat2)[:20]:
                out.append(
                    Option(float(threat2[k]), a[ii[k]], a[jj[k]], 2,
                           float(p1[ii[k]]), float(xg[jj[k]]))
                )

        out.sort(key=lambda o: -o.threat)
        return out

    def best(self, max_hops: int = 2) -> Option | None:
        opts = self.options(max_hops)
        return opts[0] if opts else None

    @property
    def n_options(self) -> int:
        return len(self.attackers)
