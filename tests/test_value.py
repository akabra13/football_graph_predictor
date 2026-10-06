"""Possession context and the Markov value model, on hand-solvable data."""
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.data.possessions import add_possession_context  # noqa: E402
from pitchgraph.value.markov import MarkovValue  # noqa: E402


def _ev(idx, typ, x, y=40.0, end_x=None, outcome=None, xg=None, sub_type=None,
        team=1, poss=1, pattern="Regular Play", t=None):
    return {"match_id": 1, "event_id": f"e{poss}-{idx}", "idx": idx, "period": 1,
            "period_seconds": float(t if t is not None else idx),
            "type": typ, "team_id": team, "possession": poss,
            "possession_team_id": 1, "play_pattern": pattern, "x": x, "y": y,
            "end_x": end_x, "end_y": y if end_x is not None else None,
            "outcome": outcome, "xg": xg, "sub_type": sub_type}


def _frame(rows):
    return pl.DataFrame(rows, infer_schema_length=None).lazy()


def test_xg_after_counts_only_later_shots_by_the_possession_team():
    ev = _frame([
        _ev(1, "Pass", 30, end_x=70),
        _ev(2, "Shot", 100, xg=0.2, outcome="Saved"),
        _ev(3, "Pressure", 20, team=2),            # the defending team's action
        _ev(4, "Shot", 110, xg=0.3, outcome="Goal"),
    ])
    out = add_possession_context(ev).sort("idx").collect()
    assert out["xg_after"].to_list() == pytest.approx([0.5, 0.5, 0.3, 0.3])
    assert out["goal_after"].to_list() == [True, True, True, True]
    assert out["in_possession"].to_list() == [True, True, False, True]


def test_restart_marks_the_delivery_not_the_whole_possession():
    ev = _frame([
        _ev(1, "Pass", 110, end_x=112, sub_type="Corner", pattern="From Corner"),
        _ev(2, "Pass", 112, end_x=100, pattern="From Corner"),
    ])
    out = add_possession_context(ev).sort("idx").collect()
    assert out["restart"].to_list() == ["Corner", None]


def test_transition_only_early_in_possessions_won_in_open_play():
    ev = _frame([
        _ev(1, "Ball Recovery", 50, t=0),
        _ev(2, "Pass", 50, end_x=80, t=4),
        _ev(3, "Pass", 80, end_x=90, t=25),
    ])
    out = add_possession_context(ev).sort("idx").collect()
    assert out["transition"].to_list() == [True, True, False]


def _two_zone_data():
    # nx=2, ny=1: zone 0 is x<60, zone 1 is x>=60.
    rows = [
        _ev(1, "Pass", 30, end_x=90), _ev(2, "Pass", 30, end_x=90),
        _ev(3, "Pass", 30, end_x=90, outcome="Incomplete"),
        _ev(4, "Pass", 30, end_x=90, outcome="Incomplete"),
        _ev(5, "Shot", 100, xg=0.4, outcome="Saved"),
        _ev(6, "Pass", 100, end_x=110, outcome="Incomplete"),
    ]
    return _frame(rows)


def test_chain_solves_to_the_hand_computed_values():
    # zone 1: P(shoot)=1/2, xG 0.4, P(move)=0  ->  V1 = 0.2
    # zone 0: P(move to 1)=1/2, P(shoot)=0     ->  V0 = 0.5 * 0.2 = 0.1
    m = MarkovValue(nx=2, ny=1, prior_turnovers=0.0).fit(_two_zone_data())
    assert m.values == pytest.approx([0.1, 0.2])


def test_action_values_are_change_in_scoring_probability():
    m = MarkovValue(nx=2, ny=1, prior_turnovers=0.0).fit(_two_zone_data())
    out = m.add_action_values(_two_zone_data()).sort("idx").collect()
    by = {r["idx"]: r["value"] for r in out.iter_rows(named=True)}
    assert by[1] == pytest.approx(0.1)     # completed move 0 -> 1
    assert by[3] == pytest.approx(-0.1)    # lost it in zone 0
    assert by[5] == pytest.approx(0.2)     # shot worth 0.4 from a zone worth 0.2
    assert by[6] == pytest.approx(-0.2)    # lost it in zone 1


def test_prior_keeps_degenerate_zones_solvable():
    # A zone whose only action is a carry that stays inside it made the raw
    # system singular (found on a 5-match sample). The prior must fix that.
    ev = _frame([_ev(1, "Carry", 30, end_x=32), _ev(2, "Shot", 100, xg=0.3)])
    m = MarkovValue(nx=2, ny=1).fit(ev)
    assert np.all(np.isfinite(m.values))
    with pytest.raises(np.linalg.LinAlgError):
        MarkovValue(nx=2, ny=1, prior_turnovers=0.0).fit(ev)


def test_set_piece_deliveries_and_penalties_are_excluded_from_open_play():
    ev = _frame([
        _ev(1, "Pass", 119, y=1, end_x=110, sub_type="Corner"),
        _ev(2, "Shot", 108, xg=0.76, sub_type="Penalty"),
    ])
    m = MarkovValue(nx=2, ny=1).fit(ev)
    assert m.values == pytest.approx([0.0, 0.0])
