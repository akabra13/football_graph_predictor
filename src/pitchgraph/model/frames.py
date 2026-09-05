"""Freeze-frame -> defensive point cloud, in a single normalised frame of reference.

Three things here are load-bearing and were each verified against the data before
being written; getting any of them wrong corrupts everything downstream silently.

1. COORDINATE FRAME. StatsBomb gives coordinates from the perspective of the
   *event* team, which always attacks toward x=120. But ~19% of events are made
   by the team NOT in possession (Pressure, Clearance, Block, ...). For those the
   pitch is mirrored relative to the attack. We normalise everything so that the
   ATTACKING (possession) team always attacks toward x=120, which means the
   DEFENDING goal is always at (120, 40).

2. TEAMMATE FLAG. `teammate` is relative to the event's actor, not to the
   attacking team. Combined with (1), the mapping to attacker/defender flips for
   that same 19% of events.

3. CENSORING. `visible_area` is the broadcast camera's polygon. Anything outside
   it is UNOBSERVED, not empty. A defender who is off-camera must never be
   counted as absent, or unseen pitch masquerades as a gap in the defence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from matplotlib.path import Path as MplPath

PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0
DEFENDING_GOAL = np.array([120.0, 40.0])
GOAL_HALF_WIDTH = 4.0  # goal spans y in [36, 44]


def _flip(points: np.ndarray) -> np.ndarray:
    """Mirror through the pitch centre (180 deg rotation)."""
    if points.size == 0:
        return points
    out = points.copy()
    out[:, 0] = PITCH_LENGTH - out[:, 0]
    out[:, 1] = PITCH_WIDTH - out[:, 1]
    return out


def event_time_seconds(ev: dict) -> float:
    """Seconds since kickoff of the period, offset so periods sort correctly."""
    h, m, s = ev["timestamp"].split(":")
    within = int(h) * 3600 + int(m) * 60 + float(s)
    return (ev.get("period", 1) - 1) * 1e5 + within


@dataclass
class Snapshot:
    """One observed instant of defensive structure.

    All coordinates are normalised: the attacking team attacks toward x=120, so
    the defending team is defending the goal at (120, 40).
    """

    event_id: str
    match_id: int
    period: int
    minute: int
    second: int
    t: float
    possession: int
    event_type: str
    play_pattern: str

    attacking_team: str
    defending_team: str

    ball: np.ndarray                 # (2,) location of the event
    defenders: np.ndarray            # (N, 2)
    defender_is_keeper: np.ndarray   # (N,) bool
    attackers: np.ndarray            # (M, 2)
    visible_area: np.ndarray         # (K, 2) polygon
    attacker_is_actor: np.ndarray | None = None  # (M,) bool, the ball carrier
    pass_end: np.ndarray | None = None      # (2,) normalised, passes only
    pass_complete: bool | None = None       # None for non-pass events

    _path: MplPath | None = field(default=None, repr=False, compare=False)

    # -- censoring ---------------------------------------------------------
    @property
    def path(self) -> MplPath:
        if self._path is None:
            self._path = MplPath(self.visible_area)
        return self._path

    def is_visible(self, points: np.ndarray) -> np.ndarray:
        """Boolean mask: which points lie inside the observed camera polygon."""
        pts = np.atleast_2d(np.asarray(points, dtype=float))
        if self.visible_area.size == 0:
            return np.zeros(len(pts), dtype=bool)
        return self.path.contains_points(pts)

    def visible_fraction(self, grid: np.ndarray) -> float:
        return float(self.is_visible(grid).mean())

    # -- convenience -------------------------------------------------------
    @property
    def outfield_defenders(self) -> np.ndarray:
        return self.defenders[~self.defender_is_keeper]

    @property
    def n_defenders(self) -> int:
        return len(self.defenders)

    def distance_to_goal(self, points: np.ndarray) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(points, dtype=float))
        return np.linalg.norm(pts - DEFENDING_GOAL, axis=1)


def snapshot_from_event(
    ev: dict, frame: dict, match_id: int, team_names: dict[int, str]
) -> Snapshot | None:
    """Build a normalised Snapshot from one event and its 360 frame.

    Returns None if the event has no usable location or no defenders visible.
    """
    loc = ev.get("location")
    if loc is None:
        return None
    poss_team = ev.get("possession_team")
    if poss_team is None:
        return None

    # Is this event's coordinate frame aligned with the attacking direction?
    event_is_attacker = ev["team"]["id"] == poss_team["id"]

    ff = frame.get("freeze_frame", [])
    if not ff:
        return None

    locs = np.array([p["location"] for p in ff], dtype=float)
    is_teammate = np.array([bool(p["teammate"]) for p in ff])
    is_keeper = np.array([bool(p["keeper"]) for p in ff])
    is_actor = np.array([bool(p.get("actor", False)) for p in ff])

    # `teammate` is relative to the actor. Defenders are the team out of possession.
    defender_mask = ~is_teammate if event_is_attacker else is_teammate

    ball = np.array(loc[:2], dtype=float)
    defenders = locs[defender_mask]
    attackers = locs[~defender_mask]
    va = np.array(frame.get("visible_area", []), dtype=float).reshape(-1, 2)

    # Normalise so the attacking team always attacks toward x=120.
    if not event_is_attacker:
        ball = _flip(ball.reshape(1, 2))[0]
        defenders = _flip(defenders)
        attackers = _flip(attackers)
        va = _flip(va)

    if len(defenders) == 0:
        return None

    defending_id = (
        ev["team"]["id"] if not event_is_attacker else _other_team(ev, team_names)
    )

    pass_end = None
    pass_complete = None
    if ev["type"]["name"] == "Pass":
        pe = ev.get("pass", {}).get("end_location")
        if pe is not None:
            pass_end = np.array(pe[:2], dtype=float)
            if not event_is_attacker:
                pass_end = _flip(pass_end.reshape(1, 2))[0]
        # StatsBomb omits `outcome` on completed passes.
        pass_complete = "outcome" not in ev.get("pass", {})

    return Snapshot(
        event_id=ev["id"],
        match_id=match_id,
        period=ev.get("period", 1),
        minute=ev.get("minute", 0),
        second=ev.get("second", 0),
        t=event_time_seconds(ev),
        possession=ev.get("possession", -1),
        event_type=ev["type"]["name"],
        play_pattern=ev.get("play_pattern", {}).get("name", "Unknown"),
        attacking_team=poss_team["name"],
        defending_team=team_names.get(defending_id, "Unknown"),
        ball=ball,
        defenders=defenders,
        defender_is_keeper=is_keeper[defender_mask],
        attackers=attackers,
        attacker_is_actor=is_actor[~defender_mask],
        visible_area=va,
        pass_end=pass_end,
        pass_complete=pass_complete,
    )


def _other_team(ev: dict, team_names: dict[int, str]) -> int:
    poss_id = ev["possession_team"]["id"]
    for tid in team_names:
        if tid != poss_id:
            return tid
    return -1


def build_snapshots(sb, match_id: int, event_types: set[str] | None = None) -> list[Snapshot]:
    """All normalised snapshots for a match that have 360 coverage.

    `event_types` filters to specific event types (e.g. {"Pass", "Carry"}).
    """
    events = sb.events(match_id)
    frames = sb.frames_by_event(match_id)
    team_names = {
        e["team"]["id"]: e["team"]["name"] for e in events if e.get("team")
    }

    out = []
    for ev in events:
        if event_types and ev["type"]["name"] not in event_types:
            continue
        frame = frames.get(ev["id"])
        if frame is None:
            continue
        snap = snapshot_from_event(ev, frame, match_id, team_names)
        if snap is not None:
            out.append(snap)
    out.sort(key=lambda s: s.t)
    return out
