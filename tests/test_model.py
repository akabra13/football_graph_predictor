"""Behavioural checks on the geometry and the outcome-independence guarantee."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.model.frames import Snapshot  # noqa: E402
from pitchgraph.model.resistance import (  # noqa: E402
    lane_pressure,
    pass_success,
    reception_pressure,
    shot_probability,
)
from pitchgraph.model.vulnerability import FEATURE_NAMES, _back_line, features  # noqa: E402

FULL_PITCH = np.array([[0.0, 0.0], [120.0, 0.0], [120.0, 80.0], [0.0, 80.0], [0.0, 0.0]])


def _snap(defenders, attackers=None, ball=(60.0, 40.0), keepers=None):
    defenders = np.asarray(defenders, dtype=float)
    attackers = np.zeros((0, 2)) if attackers is None else np.asarray(attackers, float)
    keeper_mask = (np.zeros(len(defenders), bool) if keepers is None
                   else np.asarray(keepers, bool))
    return Snapshot(
        event_id="x", match_id=1, period=1, minute=0, second=0, t=0.0,
        possession=1, event_type="Pass", play_pattern="Regular Play",
        attacking_team="A", defending_team="D",
        ball=np.array(ball, dtype=float),
        defenders=defenders, defender_is_keeper=keeper_mask,
        attackers=attackers, visible_area=FULL_PITCH,
    )


def test_defender_on_the_lane_creates_more_pressure_than_one_far_away():
    start = np.array([[60.0, 40.0]])
    end = np.array([[100.0, 40.0]])
    on_lane = lane_pressure(start, end, np.array([[80.0, 40.0]]))
    off_lane = lane_pressure(start, end, np.array([[80.0, 75.0]]))
    assert on_lane[0] > 0.9 and off_lane[0] < 0.01


def test_defender_behind_the_passer_does_not_block_the_lane():
    """Only the span of the segment counts, not the infinite line through it."""
    start = np.array([[60.0, 40.0]])
    end = np.array([[100.0, 40.0]])
    behind = lane_pressure(start, end, np.array([[20.0, 40.0]]))
    assert behind[0] < 0.01


def test_pass_success_decreases_with_pressure_and_length():
    assert pass_success(0.0, 0.0, 10.0) > pass_success(2.0, 0.0, 10.0)
    assert pass_success(0.0, 0.0, 10.0) > pass_success(0.0, 0.9, 10.0)
    assert pass_success(0.0, 0.0, 10.0) > pass_success(0.0, 0.0, 60.0)
    assert 0.0 < pass_success(0.0, 0.0, 10.0) < 1.0


def test_shot_probability_falls_with_distance_and_angle():
    central_close = shot_probability(np.array([[114.0, 40.0]]))[0]
    central_far = shot_probability(np.array([[80.0, 40.0]]))[0]
    wide_close = shot_probability(np.array([[114.0, 5.0]]))[0]
    assert central_close > central_far
    assert central_close > wide_close
    # Calibrated against real xG: a good chance is tenths, never near-certain.
    assert 0.05 < central_close < 0.6


def test_back_line_picks_the_deepest_defenders_and_ignores_the_keeper():
    d = np.array([[70.0, 40.0], [100.0, 20.0], [102.0, 60.0], [101.0, 40.0],
                  [99.0, 10.0], [118.0, 40.0]])
    keepers = np.array([False] * 5 + [True])
    back = _back_line(d, keepers, k=4)
    assert len(back) == 4
    assert 118.0 not in back[:, 0], "keeper must not be treated as a defender line"
    assert back[:, 0].min() >= 99.0


def test_a_wider_gap_in_the_back_line_registers_as_a_bigger_lateral_seam():
    tight = _snap([[100.0, 30.0], [100.0, 38.0], [100.0, 46.0], [100.0, 54.0]])
    split = _snap([[100.0, 10.0], [100.0, 18.0], [100.0, 62.0], [100.0, 70.0]])
    i = FEATURE_NAMES.index("max_lateral_gap")
    assert features(split)[i] > features(tight)[i]


def test_a_higher_line_leaves_more_space_behind():
    high = _snap([[90.0, 30.0], [90.0, 40.0], [90.0, 50.0], [90.0, 60.0]])
    deep = _snap([[112.0, 30.0], [112.0, 40.0], [112.0, 50.0], [112.0, 60.0]])
    i = FEATURE_NAMES.index("space_behind")
    assert features(high)[i] > features(deep)[i]


def test_features_are_outcome_independent():
    """The core methodological guarantee.

    Vulnerability must be defined by geometry alone. If any outcome information
    leaked into these features, validating them against outcomes would be
    circular. A Snapshot carries no outcome field other than pass_complete, so
    changing it must not move a single feature.
    """
    s = _snap([[100.0, 30.0], [100.0, 40.0], [105.0, 50.0], [98.0, 60.0]],
              attackers=[[95.0, 35.0], [88.0, 55.0]])
    before = features(s)
    s.pass_complete = not bool(s.pass_complete)
    s.pass_end = np.array([119.0, 40.0])
    assert np.allclose(before, features(s), equal_nan=True)
