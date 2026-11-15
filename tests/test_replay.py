"""Season replay: plans use only earlier matches, and calls are scored."""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.prematch.replay import mirror_lane, mirror_region, replay, tv  # noqa: E402

LANE_Y = [9.0, 24.0, 40.0, 56.0, 71.0]


def _league(n_teams=4, rounds=4, seed=0):
    """Round-robin where team 0 always attacks down its left flank."""
    rng = np.random.default_rng(seed)
    rows, matches, mid = [], [], 0
    for rnd in range(rounds):
        for a in range(n_teams):
            for b in range(a + 1, n_teams):
                mid += 1
                matches.append(dict(match_id=mid, match_date=f"2020-01-{mid:02d}", home_team_id=a,
                                    away_team_id=b, home_team=f"T{a}", away_team=f"T{b}",
                                    home_score=1, away_score=0))
                for team, opp in ((a, b), (b, a)):
                    for poss in range(25):
                        lane = 0 if team == 0 else int(rng.integers(0, 5))
                        base = dict(match_id=mid, team_id=team, possession_team_id=team,
                                    possession=poss * 2 + (team > opp), home_team_id=a, away_team_id=b,
                                    period=1, play_pattern="Regular Play", outcome=None, xg=None,
                                    sub_type=None, player_id=team * 10 + poss % 3,
                                    player=f"P{team * 10 + poss % 3}", recipient_id=team * 10 + (poss + 1) % 3)
                        y = LANE_Y[lane]
                        rows += [
                            {**base, "idx": 1, "type": "Pass", "x": 50.0, "y": y, "end_x": 90.0, "end_y": y},
                            {**base, "idx": 2, "type": "Pass", "x": 90.0, "y": y, "end_x": 90.0, "end_y": 24.0},
                            {**base, "idx": 3, "type": "Pass", "x": 90.0, "y": 24.0, "end_x": 105.0, "end_y": 40.0},
                            {**base, "idx": 4, "type": "Shot", "x": 105.0, "y": 40.0, "end_x": None,
                             "end_y": None, "xg": float(rng.uniform(0.02, 0.3)), "recipient_id": None},
                        ]
                    # one defensive action by the other side, in its own frame
                    rows.append(dict(match_id=mid, team_id=opp, possession_team_id=team, possession=999,
                                     home_team_id=a, away_team_id=b, period=1, play_pattern="Regular Play",
                                     outcome=None, xg=None, sub_type=None, player_id=opp * 10 + 5,
                                     player=f"P{opp * 10 + 5}", recipient_id=None, idx=5, type="Pressure",
                                     x=25.0, y=56.0, end_x=None, end_y=None))
    return pl.DataFrame(rows, infer_schema_length=None), pl.DataFrame(matches)


def test_mirrors_and_tv():
    assert mirror_lane(0) == 4 and mirror_region(11) == 3      # their left half-space, final third
    assert tv([1, 0], [0, 1]) == 1.0 and tv([0.5, 0.5], [0.5, 0.5]) == 0.0


def test_replay_plans_from_earlier_matches_only_and_scores_them():
    ev, matches = _league()
    out = replay(ev, matches, team_id=1, start_fraction=0.5, kappa=10.0)   # light shrinkage: tiny league
    games = out["games"]
    assert len(games) == 6                                     # second half of 12 fixtures
    for g in games:
        p = g["plan"]
        assert p is not None and p["prior_matches"]["us"] >= 5
        # nothing from this match or later can be in the plan
        assert p["prior_matches"]["us"] <= sum(1 for m in matches.iter_rows(named=True)
                                               if m["match_date"] < g["date"])
        assert abs(sum(p["they_attack"]["matchup"]) - 1) < 1e-9
        o = g["outcome"]
        assert set(o["they"]["tv"]) == {"matchup", "own", "league"}
        assert o["their_threat"]["expected"] > 0

    # against team 0, which only ever attacks down its left, the plan says so and is right
    vs0 = [g for g in games if g["opponent_id"] == 0]
    assert vs0 and all(int(np.argmax(g["plan"]["they_attack"]["own"])) == 0 for g in vs0)
    assert all(g["outcome"]["they"]["top_hit"]["own"] for g in vs0)
    # player links come from the squads involved
    pl_ = vs0[0]["plan"]["players"]
    assert all(p["player_id"] // 10 == 0 for p in pl_["their_passers"])
    assert all(p["player_id"] // 10 == 1 for p in pl_["our_defenders"] + pl_["our_carriers"])
    assert out["summary"]["games"] == 6


def test_report_renders_every_game():
    from pitchgraph.prematch.report import render_html

    ev, matches = _league()
    rep = replay(ev, matches, team_id=1, start_fraction=0.5, kappa=10.0)
    html = render_html(rep, "T1", "Test League", "2020")
    assert html.count('class="card"') == 2 + len(rep["games"])      # caveats, scorecard, one per game
    assert "Scorecard" in html and "StatsBomb" in html and "<script" not in html
