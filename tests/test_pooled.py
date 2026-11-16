"""Pooled replay: the fast calls equal the replay's own, and use no later matches."""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.prematch.pooled import asof_arrays, pooled_skill, team_shares  # noqa: E402
from pitchgraph.prematch.replay import asof_call  # noqa: E402


def _table(seed=0, n_teams=8, rounds=3, team_effect=1.0):
    rng = np.random.default_rng(seed)
    eff = rng.normal(size=n_teams) * team_effect
    rows, dates, mid = [], {}, 0
    for _ in range(rounds):
        for a in range(n_teams):
            for b in range(a + 1, n_teams):
                mid += 1
                dates[mid] = f"2020-{1 + mid // 28:02d}-{1 + mid % 28:02d}"
                for t, o in ((a, b), (b, a)):
                    rows.append({"match_id": mid, "team_id": t, "opp_id": o,
                                 "f": eff[t] + rng.normal(), "g": float("nan") if mid % 9 == 0 else rng.normal()})
    return pl.DataFrame(rows), dates


def test_fast_calls_equal_the_replays_calls():
    table, dates = _table()
    p = asof_arrays(table, dates, ["f", "g"])
    rows = np.flatnonzero(p["scored"])[::7]
    assert len(rows) > 5
    for r in rows:
        mid, team, opp = (int(table[c][int(r)]) for c in ("match_id", "team_id", "opp_id"))
        prior = {m for m, d in dates.items() if d < dates[mid]}
        for k, f in enumerate(["f", "g"]):
            want = asof_call(table, f, team, opp, prior)
            assert abs(p["call"][r, k] - want["predicted"]) < 1e-9
            assert abs(p["league"][r, k] - want["league"]) < 1e-9


def test_calls_ignore_this_match_and_later_ones():
    table, dates = _table()
    base = asof_arrays(table, dates, ["f"])
    r = int(np.flatnonzero(base["scored"])[3])
    d = dates[int(table["match_id"][r])]
    later = [m for m, dd in dates.items() if dd >= d]
    changed = table.with_columns(f=pl.when(pl.col("match_id").is_in(later)).then(pl.col("f") + 50)
                                 .otherwise(pl.col("f")))
    after = asof_arrays(changed, dates, ["f"])
    assert base["call"][r, 0] == after["call"][r, 0]


def test_scored_rows_are_the_later_half_with_enough_history():
    table, dates = _table()
    p = asof_arrays(table, dates, ["f"])
    for t in range(8):
        idx = np.flatnonzero(p["team"] == t)
        assert 0 < p["scored"][idx].sum() <= len(idx) - len(idx) // 2


def test_pooled_skill_holds_with_a_team_effect_and_not_without():
    with_effect = pooled_skill([asof_arrays(*_table(team_effect=1.5), ["f"])], 0, n_boot=80)
    assert with_effect["holds"] and with_effect["skill"] > 0.2
    t, d = _table(seed=4, team_effect=0.0)
    none = pooled_skill([asof_arrays(t, d, ["f"])], 0, n_boot=80)
    assert not none["holds"]
    shares = team_shares([asof_arrays(*_table(team_effect=1.5), ["f"])], [0], min_games=5)
    assert len(shares) == 8 and np.median(shares) > 0.5


def test_premises_fire_on_strong_teams_and_mostly_hold():
    from pitchgraph.prematch.pooled import premise_rows

    table, dates = _table(team_effect=2.0)
    p = asof_arrays(table, dates, ["f"])
    for who in ("we", "they"):
        fired, held, m = premise_rows(p, 0, who, +1, 0.5)
        assert len(fired) == len(held) == len(m) and fired.any()
        assert held[fired].mean() > 0.7 > held[~fired].mean()     # called high -> usually was high
    # "they" reads the opponent's row: a fired premise there means the OPPONENT is the strong side
    fired, _, _ = premise_rows(p, 0, "they", +1, 0.5)
    rows = np.flatnonzero(p["scored"])[fired]
    assert (p["call"][[np.flatnonzero((p["match"] == p["match"][r]) & (p["team"] == p["opp"][r]))[0]
                       for r in rows], 0] > p["league"][rows, 0]).all()


def test_lineups_starters_missing_regulars_and_weights():
    from pitchgraph.prematch.lineups import missing_regulars, overlap_weight, starters

    rows = []
    for m in range(1, 8):
        for p in range(13):
            start = p < 11 if m < 7 else (p < 10 or p == 12)       # in match 7, player 10 is dropped for 12
            rows.append({"match_id": m, "team_id": 1, "player_id": p,
                         "positions": '[{"start_reason": "Starting XI"}]' if start
                         else ('[{"start_reason": "Substitution - On"}]' if p == 11 else "[]")})
    xi = starters(pl.DataFrame(rows))
    assert len(xi[(1, 1)]) == 11 and 11 not in xi[(1, 1)] and 12 in xi[(7, 1)]
    assert overlap_weight(xi[(1, 1)], xi[(2, 1)]) == 1.0
    assert abs(overlap_weight(xi[(1, 1)], xi[(7, 1)]) - (10 / 11) ** 4) < 1e-12
    assert overlap_weight(None, xi[(1, 1)]) == 1.0
    gone = missing_regulars(xi, 1, 7, set(range(1, 7)), {10: "Ten"})
    assert [g["name"] for g in gone] == ["Ten"] and gone[0]["started"] == 6
    assert missing_regulars(xi, 1, 2, {1}, {}) == []               # too few earlier matches to call anyone a regular


def test_lineup_weighted_call_follows_the_matching_lineup():
    from pitchgraph.prematch.pooled import skill_difference

    # one team alternates between two XIs with very different values; weighting should track today's XI
    rng = np.random.default_rng(0)
    rows, dates, xi, mid = [], {}, {}, 0
    a, b = frozenset(range(11)), frozenset(range(100, 111))
    for rnd in range(40):
        mid += 1
        dates[mid] = f"2020-{1 + mid // 28:02d}-{1 + mid % 28:02d}"
        use_a = rnd % 2 == 0
        rows.append({"match_id": mid, "team_id": 1, "opp_id": 2, "f": (2.0 if use_a else -2.0) + rng.normal() * .3})
        rows.append({"match_id": mid, "team_id": 2, "opp_id": 1, "f": rng.normal() * .3})
        xi[(mid, 1)], xi[(mid, 2)] = (a if use_a else b), frozenset(range(200, 211))
    p = asof_arrays(pl.DataFrame(rows), dates, ["f"], xi=xi)
    d = skill_difference([p], 0, n_boot=60)
    assert d["helped"] and d["skill_lineup"] > d["skill_plain"] + 0.3
    # with identical line-ups every week, weighting changes nothing
    same = {k: a for k in xi}
    p2 = asof_arrays(pl.DataFrame(rows), dates, ["f"], xi=same)
    assert np.allclose(p2["call"][p2["scored"]], p2["call_xi"][p2["scored"]])
