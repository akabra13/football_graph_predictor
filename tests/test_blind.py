"""The blind test: which seasons are unseen, the pooled instruction share and the verdict."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.prematch import blind  # noqa: E402


def test_frozen_list_is_present_and_only_new_seasons_count():
    frozen = blind.frozen_keys()
    assert len(frozen) >= 80 and "2_27" in frozen
    live = [{"competition_id": 2, "season_id": 27}, {"competition_id": 2, "season_id": 999}]
    assert blind.new_keys(live, frozen) == ["2_999"]


def test_usable_needs_a_league():
    def match(h, a):
        return {"home_team": {"home_team_id": h}, "away_team": {"away_team_id": a}}
    league = [match(h, a) for h in range(8) for a in range(8) if h != a]          # 14 matches each
    assert blind.usable(league)
    assert not blind.usable(league[:20])


def _part(seed, hold):
    """`asof_arrays`-shaped arrays: one feature, the actual lands on the called side with chance `hold`."""
    rng = np.random.default_rng(seed)
    m = 400
    match = np.repeat(np.arange(m), 2)
    team = np.tile([0, 1], m) + 2 * match
    opp = team[np.arange(2 * m) ^ 1]
    n = 2 * m
    call = rng.normal(size=(n, 1))
    side = np.where(rng.random(n) < hold, 1.0, -1.0) * np.sign(call[:, 0])
    return {"match": match, "team": team, "opp": opp, "scored": np.ones(n, bool), "call": call,
            "own": np.zeros((n, 1)), "league": np.zeros((n, 1)), "league_sd": np.ones((n, 1)),
            "actual": (side * rng.random(n))[:, None]}


RULES = [("more", "we", "f", +1, ""), ("less", "we", "f", -1, "")]


def test_pooled_share_counts_every_instruction():
    r = blind.pooled_premises([_part(0, 0.8)], ["f"], RULES, 0.4, n_boot=200)
    assert r["holds"] and 0.72 < r["occurred_share"] < 0.88
    assert 400 < r["issued"] < 700                      # both tails beyond 0.4 SD of 800 rows
    assert not blind.pooled_premises([_part(1, 0.5)], ["f"], RULES, 0.4, n_boot=200)["holds"]
    assert blind.pooled_premises([], ["f"], RULES, 0.4) == {"issued": 0}


def test_no_verdict_until_there_is_enough():
    small = blind.verdict({"n": 120, "holds": True}, {"result_call_holds": True}, {"holds": True})
    assert not small["judged"]
    ok = blind.verdict({"n": 400, "holds": True}, {"result_call_holds": True}, {"holds": True})
    assert ok["judged"] and ok["reading"] == "all three hold on unseen data"
    bad = blind.verdict({"n": 400, "holds": True}, {"result_call_holds": False}, {"holds": True})
    assert bad["reading"] == "failed on unseen data: result_call"
