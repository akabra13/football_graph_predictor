"""Following an instruction: level-score measures and the fired-versus-not comparison."""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.prematch.followed import FEATURES, evaluate, level_table  # noqa: E402


def _ev(rows):
    base = dict(match_id=1, home_team_id=1, away_team_id=2, period=1, sub_type=None, outcome=None, xg=None,
                x=50.0, y=40.0, end_x=None, end_y=None)
    return pl.DataFrame([{**base, "idx": i, **r} for i, r in enumerate(rows)], infer_schema_length=None)


def test_only_level_minutes_count():
    rows = [dict(team_id=1, type="Pass", period_seconds=0.0, end_x=95.0, end_y=40.0)]            # long pass
    rows += [dict(team_id=2, type="Pass", period_seconds=60.0 * i, end_x=55.0, end_y=40.0) for i in range(1, 30)]
    rows += [dict(team_id=1, type="Pressure", period_seconds=1750.0, x=90.0),
             dict(team_id=1, type="Shot", period_seconds=1800.0, outcome="Goal", xg=0.5, x=110.0),   # 1-0 at 30'
             dict(team_id=2, type="Shot", period_seconds=1900.0, xg=0.9, x=110.0),                   # after: ignored
             dict(team_id=1, type="Pressure", period_seconds=2000.0, x=90.0),                        # ignored
             dict(team_id=1, type="Pass", period_seconds=2100.0, end_x=99.0, end_y=40.0)]            # ignored
    t = level_table(_ev(rows))
    assert t.columns == ["match_id", "team_id", "opp_id", "level_minutes", *FEATURES]
    a = t.filter(pl.col("team_id") == 1).row(0, named=True)
    assert abs(a["level_minutes"] - 30.0) < 1e-9
    assert abs(a["lv_press"] - 1 / 29) < 1e-9 and a["lv_long"] == 1.0
    assert abs(a["lv_xgd90"] - 0.5 / 30 * 90) < 1e-9                  # the goal itself was struck while level
    b = t.filter(pl.col("team_id") == 2).row(0, named=True)
    assert abs(b["lv_xgd90"] + 0.5 / 30 * 90) < 1e-9


def _part(seed, effect):
    """A season of `asof_arrays`-shaped arrays where doing it is worth `effect` only when the rule fired."""
    rng = np.random.default_rng(seed)
    m = 600
    match = np.repeat(np.arange(m), 2)
    team = np.tile([0, 1], m) + 2 * np.repeat(np.arange(m), 2)
    opp = team[np.arange(2 * m) ^ 1]
    n = 2 * m
    feats = ["own_third_turnover_share", "lv_press", "lv_xgd90"]
    own = np.zeros((n, 3))
    call = np.zeros((n, 3))
    call[:, 0] = rng.normal(size=n)                    # the rule's premise, read from the opponent's row
    own[:, 0] = call[:, 0]                             # all of it is the opponent's own habit
    actual = rng.normal(size=(n, 3))
    fired = call[opp_index(match, team, opp), 0] >= 0.4
    did = actual[:, 1] > 0
    actual[:, 2] = rng.normal(size=n) + 0.3 * did + effect * (fired & did)
    return {"match": match, "team": team, "opp": opp, "scored": np.ones(n, bool), "call": call, "own": own,
            "league": np.zeros((n, 3)), "league_sd": np.ones((n, 3)), "actual": actual,
            "weight": np.full(n, 45.0)}, feats


def opp_index(match, team, opp):
    where = {(m, t): i for i, (m, t) in enumerate(zip(match, team))}
    return np.array([where[(m, o)] for m, o in zip(match, opp)])


RULE = [("press_them", "they", "own_third_turnover_share", +1, "")]


def test_finds_an_effect_that_exists_only_when_asked():
    p, feats = _part(0, effect=0.8)
    r = evaluate([p], feats, RULE, 0.4, n_boot=200)["press_them"]
    assert r["verdict"] == "supported" and 0.4 < r["extra_when_asked"] < 1.2
    assert 0.1 < r["gap_when_not_fired"] < 0.5         # the behaviour goes with good outcomes anyway


def test_a_general_association_alone_is_not_support():
    p, feats = _part(1, effect=0.0)
    r = evaluate([p], feats, RULE, 0.4, n_boot=200)["press_them"]
    assert r["verdict"] == "no evidence either way" and r["gap_when_fired"] > 0
