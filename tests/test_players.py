"""Player flow graphs on hand-checkable data."""
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.chains.players import OTHERS, PlayerChain, build, removal_effects  # noqa: E402


def two_player_chain() -> PlayerChain:
    """A passes to B half the time (else loses it); B shoots half the time
    (xG 0.2, else loses it). Every possession starts with A.

        V_B = 0.5 * 0.2 = 0.1,   V_A = 0.5 * V_B = 0.05
    Columns: to A, to B, to others, shoot, lose.
    """
    P = np.array([[0, .5, 0, 0, .5],
                  [0, 0, 0, .5, .5],
                  [0, 0, 0, 0, 1.0]])
    return PlayerChain([1, 2, OTHERS], P, np.array([0, .2, 0]), np.array([1.0, 0, 0]))


def test_player_chain_threat_matches_the_hand_solution():
    assert two_player_chain().threat == pytest.approx(0.05)


def test_removing_the_only_finisher_removes_all_threat():
    c = two_player_chain()
    assert c.without(2, adapt=False).threat == pytest.approx(0.0)
    assert c.without(2, adapt=True).threat == pytest.approx(0.0)   # A has nobody else


def test_removing_the_only_starter_spreads_possessions_over_the_rest():
    c = two_player_chain()
    out = c.without(1, adapt=False)
    # Nobody else ever started a possession, so they are spread evenly over
    # B and "others": threat = 0.5 * V_B + 0.5 * 0 = 0.05.
    assert out.threat == pytest.approx(0.05)
    assert out.start.sum() == pytest.approx(1.0)


def test_removal_effects_rank_the_finisher_first():
    rows = removal_effects(two_player_chain())
    assert rows[0]["player_id"] == 2 and rows[0]["drop_no_adapt"] == pytest.approx(1.0)


def _actions():
    rows = []
    for m in range(4):
        for p in range(10):
            poss = m * 100 + p
            rows += [
                {"match_id": m, "possession": poss, "idx": 1, "team_id": 7, "player_id": 1,
                 "recipient_id": 2, "kind": "move", "type": "Pass", "xg": None},
                {"match_id": m, "possession": poss, "idx": 2, "team_id": 7, "player_id": 2,
                 "recipient_id": None, "kind": "shot" if p % 2 else "turnover",
                 "type": "Shot" if p % 2 else "Pass", "xg": 0.2 if p % 2 else None},
            ]
    return pl.DataFrame(rows, infer_schema_length=None)


def test_build_counts_passes_shots_and_starts():
    c = build(_actions(), 7, min_actions=5)
    assert set(c.players[:2]) == {1, 2} and c.players[-1] == OTHERS
    a, b = c.players.index(1), c.players.index(2)
    assert c.start[a] == pytest.approx(1.0)
    # Player 1 always passes to 2; shrinkage pulls the row only slightly.
    assert c.P[a, b] > 0.6 and c.P.sum(1) == pytest.approx(np.ones(c.k))
