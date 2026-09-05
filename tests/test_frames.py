"""Invariants that were expensive to discover and are easy to silently break."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.model.frames import (  # noqa: E402
    DEFENDING_GOAL,
    PITCH_LENGTH,
    PITCH_WIDTH,
    Snapshot,
    _flip,
    snapshot_from_event,
)


def test_flip_is_an_involution():
    pts = np.array([[10.0, 20.0], [100.0, 70.0], [60.0, 40.0]])
    assert np.allclose(_flip(_flip(pts)), pts)


def test_flip_maps_own_goal_to_defending_goal():
    # A keeper on their own line at x=0 belongs at x=120 once mirrored.
    assert np.allclose(_flip(np.array([[0.0, 40.0]])), [[PITCH_LENGTH, PITCH_WIDTH - 40.0]])


def _event(team_id, poss_id, ff, loc=(60.0, 40.0)):
    return {
        "id": "e1",
        "period": 1,
        "timestamp": "00:10:00.000",
        "minute": 10,
        "second": 0,
        "possession": 3,
        "type": {"name": "Pass"},
        "play_pattern": {"name": "Regular Play"},
        "team": {"id": team_id, "name": "T%d" % team_id},
        "possession_team": {"id": poss_id, "name": "T%d" % poss_id},
        "location": list(loc),
        "pass": {"end_location": [70.0, 40.0]},
    }


ATTACK_FF = [
    {"teammate": True, "actor": True, "keeper": False, "location": [60.0, 40.0]},
    {"teammate": True, "actor": False, "keeper": False, "location": [70.0, 30.0]},
    {"teammate": False, "actor": False, "keeper": False, "location": [95.0, 40.0]},
    {"teammate": False, "actor": False, "keeper": True, "location": [118.0, 40.0]},
]
FRAME = {"freeze_frame": ATTACK_FF,
         "visible_area": [0.0, 0.0, 120.0, 0.0, 120.0, 80.0, 0.0, 80.0, 0.0, 0.0]}
NAMES = {1: "Attack", 2: "Defend"}


def test_defending_keeper_is_near_x120_when_event_is_by_attacker():
    s = snapshot_from_event(_event(1, 1, ATTACK_FF), FRAME, 1, NAMES)
    keeper = s.defenders[s.defender_is_keeper]
    assert keeper[0][0] > 100, "defending keeper must sit near the goal at x=120"
    assert s.attacking_team == "T1"


def test_defending_keeper_is_near_x120_when_event_is_by_defender():
    """The 19% case: StatsBomb frames are relative to the EVENT team.

    A Pressure or Clearance is made by the team out of possession, so its
    coordinates are mirrored with respect to the attack. Without normalisation
    this snapshot would place the defending keeper at x~2 instead of x~118.
    """
    # Same physical situation, but recorded from the defending team's frame:
    # every location mirrored, and the teammate flags inverted.
    mirrored = []
    for p in ATTACK_FF:
        q = dict(p)
        q["location"] = [PITCH_LENGTH - p["location"][0], PITCH_WIDTH - p["location"][1]]
        q["teammate"] = not p["teammate"]
        mirrored.append(q)
    frame = {"freeze_frame": mirrored, "visible_area": FRAME["visible_area"]}
    ev = _event(team_id=2, poss_id=1, ff=mirrored, loc=(60.0, 40.0))

    s = snapshot_from_event(ev, frame, 1, NAMES)
    keeper = s.defenders[s.defender_is_keeper]
    assert keeper[0][0] > 100, "normalisation must survive defender-team events"
    assert s.attacking_team == "T1"


def test_attacker_and_defender_counts_are_not_swapped():
    s = snapshot_from_event(_event(1, 1, ATTACK_FF), FRAME, 1, NAMES)
    assert len(s.defenders) == 2 and len(s.attackers) == 2


def test_pass_completion_flag_reads_absence_of_outcome():
    ev = _event(1, 1, ATTACK_FF)
    assert snapshot_from_event(ev, FRAME, 1, NAMES).pass_complete is True
    ev["pass"]["outcome"] = {"name": "Incomplete"}
    assert snapshot_from_event(ev, FRAME, 1, NAMES).pass_complete is False


def test_points_outside_the_camera_polygon_are_not_visible():
    """Censoring must mean 'unobserved', so it has to actually mask."""
    frame = {"freeze_frame": ATTACK_FF,
             "visible_area": [50.0, 30.0, 90.0, 30.0, 90.0, 50.0, 50.0, 50.0, 50.0, 30.0]}
    s = snapshot_from_event(_event(1, 1, ATTACK_FF), frame, 1, NAMES)
    inside = s.is_visible(np.array([[70.0, 40.0]]))
    outside = s.is_visible(np.array([[10.0, 10.0], [110.0, 75.0]]))
    assert inside.all() and not outside.any()
