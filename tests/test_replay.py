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


def test_calls_are_made_from_earlier_matches_and_scored():
    from pitchgraph.prematch.replay import CALLS

    ev, matches = _league()
    rep = replay(ev, matches, team_id=1, start_fraction=0.5, kappa=10.0)
    g = rep["games"][0]
    for who in ("we", "they"):
        # the toy league has no giveaways, so that one call has nothing to go on and is left out
        assert set(g["calls"][who]) == {f for f, _, _ in CALLS} - {"own_third_turnover_share"}
    poss = g["calls"]["we"]["possession"]
    assert 0 < poss["predicted"] < 1 and poss["actual"] is not None
    assert isinstance(poss["closer_than_league"], bool)
    s = rep["summary"]
    assert s["calls_total"] > 0 and 0 <= s["calls_closer"] <= s["calls_total"]
    # changing this match's own events cannot change what was called for it
    later = ev.with_columns(x=pl.when(pl.col("match_id") == g["match_id"]).then(pl.lit(60.0)).otherwise(pl.col("x")))
    again = replay(later, matches, team_id=1, start_fraction=0.5, kappa=10.0)["games"][0]
    assert again["calls"]["we"]["possession"]["predicted"] == poss["predicted"]


def test_strategy_lines_rest_on_calls_and_are_checked():
    from pitchgraph.prematch.strategy import MAX_LINES, RULES, THRESHOLD, departure, lines

    call = {"predicted": 0.30, "league": 0.50, "league_sd": 0.10, "actual": 0.35}
    assert abs(departure(call, -1) - 2.0) < 1e-9 and departure(call, +1) < 0
    calls = {"we": {"possession": call}, "they": {}}
    out = lines(calls, {"our_pressers": [{"name": "A"}]}, "Opp FC", {"possession": "{:.0%}"})
    assert [s["rule"] for s in out] == ["without_ball"] and out[0]["premise_held"] is True
    assert "30%" in out[0]["text"] and "50%" in out[0]["text"]
    weak = {"we": {"possession": {**call, "predicted": 0.48}}, "they": {}}
    assert lines(weak, {}, "Opp FC", {"possession": "{:.0%}"}) == []          # under the threshold: no line
    assert THRESHOLD == 0.5 and len({r[0] for r in RULES}) == len(RULES)

    ev, matches = _league()
    rep = replay(ev, matches, team_id=1, start_fraction=0.5, kappa=10.0)
    assert all(len(g["strategy"]) <= MAX_LINES for g in rep["games"])
    s = rep["summary"]
    assert s["strategy_premises_held"] <= s["strategy_lines"]


def test_lineups_restrict_named_players_to_starters_and_flag_missing_regulars():
    ev, matches = _league()
    rows = []
    for m in matches.iter_rows(named=True):
        for t in (m["home_team_id"], m["away_team_id"]):
            for k in range(12):
                pid = t * 10 + k if k < 6 else t * 100 + k
                # team 1's player 12 (a regular carrier) is left out of its last three matches
                dropped = t == 1 and pid == 12 and m["match_id"] >= 19
                rows.append({"match_id": m["match_id"], "team_id": t, "player_id": pid, "player": f"Full{pid}",
                             "positions": "[]" if (k == 11 or dropped) else '[{"start_reason": "Starting XI"}]'})
    rep = replay(ev, matches, team_id=1, start_fraction=0.5, kappa=10.0, lineup_table=pl.DataFrame(rows))
    last = rep["games"][-1]
    lu = last["plan"]["lineup"]
    assert lu["known"] and [r["player_id"] for r in lu["us_missing"]] == [12] and lu["them_missing"] == []
    named = [p["player_id"] for k in ("our_carriers", "our_pressers", "our_defenders")
             for p in last["plan"]["players"][k]]
    assert named and 12 not in named                       # he is not starting, so he is not named
    first = rep["games"][0]["plan"]
    assert first["lineup"]["us_missing"] == [] and 12 in [p["player_id"] for p in first["players"]["our_carriers"]]
    assert first["players"]["our_carriers"][0]["name"].startswith("Full")     # full name when there is no nickname

    from pitchgraph.prematch.report import render_html
    html = render_html(rep, "T1", "Test League", "2020")
    assert "T1 without Full12" in html and "both sides start their regulars" in html


def test_replay_carries_result_calls_from_our_side():
    ev, matches = _league()
    out = replay(ev, matches, team_id=1, start_fraction=0.5, kappa=10.0)
    rows = [g["result_call"] for g in out["games"] if g.get("result_call")]
    assert rows and out["summary"]["result_calls"]["n"] == len(rows)
    for g in out["games"]:
        rc = g.get("result_call")
        if rc:
            assert abs(sum(rc["chances"]) - 1) < 1e-9
            won = g["score"][0] > g["score"][1]
            assert rc["result"] == (0 if won else 2) and rc["points"] == (3 if won else 0)
