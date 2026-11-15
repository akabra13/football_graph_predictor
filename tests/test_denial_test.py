"""The planner-vs-matches test: its pieces on data where the answer is known."""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.chains import denial  # noqa: E402
from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.denial_test import (evaluate, fit_slopes, league_of, match_rows,  # noqa: E402
                                           model_drops, region_links, spearman)
from pitchgraph.chains.grid import TACTICAL  # noqa: E402


def test_region_links_sums_zone_moves_into_regions():
    regions = denial.zone_regions(TACTICAL)
    moves = np.ones((TACTICAL.n, TACTICAL.n))
    R = region_links(moves, regions)
    assert R.shape == (15, 15) and R.sum() == moves.sum()
    assert R[0, 0] == (regions == 0).sum() ** 2


def test_joint_slopes_recover_known_link_values():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(4000, 3))
    X[:, 1] += 0.6 * X[:, 0]                      # correlated usage, as in real matches
    true = np.array([0.30, 0.10, 0.0])
    y = X @ true + rng.normal(scale=0.5, size=4000)
    assert np.allclose(fit_slopes(y, X), true, atol=0.03)


def test_evaluate_prefers_the_right_ranking():
    rng = np.random.default_rng(1)
    true = np.array([0.4, 0.3, 0.2, 0.1, 0.0])
    X = rng.normal(size=(3000, 5))
    y = X @ true + rng.normal(scale=0.5, size=3000)
    match_ids = np.repeat(np.arange(1500), 2)
    res = evaluate(y, X, match_ids, model_mid=true, usage=true[::-1], n_boot=50)
    assert res["spearman_model"] > 0.9 and res["spearman_usage"] < -0.9
    assert res["spearman_model_ci"][0] > 0 and res["spearman_diff_ci"][0] > 0
    assert spearman(np.array([1, 2, 3]), np.array([3, 2, 1])) == -1.0


def _league_events(n_teams=4, rounds=3, seed=0):
    """A small round-robin: each possession walks up the pitch and may shoot."""
    rng = np.random.default_rng(seed)
    rows, mid = [], 0
    for _ in range(rounds):
        for a in range(n_teams):
            for b in range(a + 1, n_teams):
                mid += 1
                for team, opp in ((a, b), (b, a)):
                    for poss in range(25):
                        y0 = float(rng.choice([9.0, 24.0, 40.0, 56.0, 71.0]))
                        base = dict(match_id=mid, team_id=team, possession_team_id=team,
                                    possession=poss * 2 + (team > opp), home_team_id=a, away_team_id=b,
                                    period=1, play_pattern="Regular Play", outcome=None, xg=None,
                                    sub_type=None)
                        y1 = float(rng.choice([9.0, 24.0, 40.0, 56.0, 71.0]))
                        rows += [
                            {**base, "idx": 1, "type": "Pass", "x": 30.0, "y": y0, "end_x": 70.0, "end_y": y1},
                            {**base, "idx": 2, "type": "Pass", "x": 70.0, "y": y1, "end_x": 105.0, "end_y": 40.0},
                            {**base, "idx": 3, "type": "Shot", "x": 105.0, "y": 40.0, "end_x": None,
                             "end_y": None, "xg": float(rng.uniform(0.02, 0.3))},
                        ]
    return pl.DataFrame(rows, infer_schema_length=None).lazy()


def test_match_rows_and_model_drops_on_a_small_league():
    store = CountStore.from_events(_league_events(), TACTICAL)
    y, U, M, S = match_rows(store, min_matches=5)
    assert len(y) == 36 and U.shape == (36, 15, 15) and S.shape == (36, 15, 15)
    assert abs(float(np.mean(y))) < 0.25               # centred on what strength predicts
    assert U.min() >= -1.0 and U.max() <= 3.0
    drops = model_drops(league_of(store), [(7, 12), (5, 12)])
    assert drops.shape == (2, 2) and (drops[:, 0] <= drops[:, 1] + 1e-12).all()
    assert drops[0, 1] > 0                             # the centre route into the box carries threat
