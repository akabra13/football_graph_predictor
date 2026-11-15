"""Predictability audit: graph features on known graphs, and the scoring on known data."""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.prematch.audit import (entropy_rate, hodge_circulation, predictions, reciprocity,  # noqa: E402
                                       score, spectral_gap)


def test_hodge_separates_a_loop_from_a_one_way_street():
    loop = np.zeros((3, 3))
    loop[0, 1] = loop[1, 2] = loop[2, 0] = 5          # ball goes round and round
    line = np.zeros((3, 3))
    line[0, 1] = line[1, 2] = 5                       # ball only goes forward
    assert abs(hodge_circulation(loop) - 1.0) < 1e-9
    assert hodge_circulation(line) < 1e-9
    both = loop + line
    assert 0 < hodge_circulation(both) < 1


def test_reciprocity_and_entropy_extremes():
    back_forth = np.array([[0, 4.0], [4.0, 0]])
    one_way = np.array([[0, 4.0], [0, 0]])
    assert reciprocity(back_forth) == 1.0 and reciprocity(one_way) == 0.0
    fixed = np.array([[0, 6.0, 0], [0, 0, 6.0], [6.0, 0, 0]])      # next move always known
    spread = np.ones((3, 3)) * 2                                   # next move a three-way guess
    assert entropy_rate(fixed) < 1e-9
    assert abs(entropy_rate(spread) - np.log2(3)) < 1e-9
    assert spectral_gap(spread) > spectral_gap(np.eye(3) * 5 + 0.01)   # sticky chain mixes slowly


def _season(team_effect: float, opp_effect: float, seed=0, n_teams=10, rounds=4):
    rng = np.random.default_rng(seed)
    t_eff, o_eff = rng.normal(size=n_teams) * team_effect, rng.normal(size=n_teams) * opp_effect
    rows, mid = [], 0
    for _ in range(rounds):
        for a in range(n_teams):
            for b in range(a + 1, n_teams):
                mid += 1
                for t, o in ((a, b), (b, a)):
                    rows.append({"match_id": mid, "team_id": t, "opp_id": o,
                                 "f": t_eff[t] + o_eff[o] + rng.normal()})
    return pl.DataFrame(rows)


def test_score_finds_team_and_opponent_effects_and_their_absence():
    strong = score([predictions(_season(1.0, 0.7), "f")], n_boot=60)
    assert strong["r2_team"] > 0.2 and strong["tier"] == "lead" and strong["opponent_matters"]
    noise = score([predictions(_season(0.0, 0.0), "f")], n_boot=60)
    assert noise["tier"] == "drop" and not noise["opponent_matters"]
    team_only = score([predictions(_season(1.0, 0.0, seed=3), "f")], n_boot=60)
    assert team_only["tier"] == "lead" and team_only["gain_opponent"] < 0.02


def test_predictions_never_use_the_match_itself():
    t = _season(1.0, 0.5)
    base = predictions(t, "f")
    changed = t.with_columns(f=pl.when(pl.col("match_id") == 7).then(pl.col("f") + 100).otherwise(pl.col("f")))
    after = predictions(changed, "f")
    rows = np.flatnonzero(t["match_id"].to_numpy() == 7)
    for k in ("league", "team", "both"):
        assert np.allclose(base[k][rows], after[k][rows])     # match 7's own values do not move its predictions


def test_season_table_has_every_feature_for_every_team_match():
    from test_denial_test import _league_events

    from pitchgraph.chains.counts import CountStore
    from pitchgraph.chains.grid import TACTICAL
    from pitchgraph.prematch.audit import FEATURES, season_table

    t = season_table(CountStore.from_events(_league_events(), TACTICAL), min_matches=5)
    assert t.height == 36 and all(f in t.columns for f in FEATURES)
    lanes = t.select([c for c in t.columns if c.startswith("entry_")]).to_numpy()
    assert np.allclose(lanes.sum(1), 1.0)
    assert ((t["possession"] > 0) & (t["possession"] < 1)).all()
    assert (t["hodge_circulation"].fill_nan(0) <= 1.0 + 1e-9).all()
