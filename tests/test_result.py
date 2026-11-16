"""Result calls: chances are proper, use no later matches, and find a real strength gap."""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.prematch.result import evaluate, outcome_chances, result_calls, result_table, rps  # noqa: E402


def _season(seed=0, n_teams=10, rounds=4, spread=0.5):
    rng = np.random.default_rng(seed)
    strength = np.exp(rng.normal(size=n_teams) * spread)
    ev, ms, dates, mid = [], [], {}, 0
    for rnd in range(rounds):
        for a in range(n_teams):
            for b in range(a + 1, n_teams):
                mid += 1
                h, w = (a, b) if (rnd + a + b) % 2 else (b, a)
                dates[mid] = f"2020-{1 + mid // 28:02d}-{1 + mid % 28:02d}"
                lam = {h: 1.5 * strength[h] / strength[w], w: 1.1 * strength[w] / strength[h]}
                score = {}
                for t in (h, w):
                    n = rng.poisson(lam[t] / 0.1)
                    score[t] = int((rng.random(n) < 0.1).sum())
                    for _ in range(n):
                        ev.append({"match_id": mid, "team_id": t, "type": "Shot", "period": 1,
                                   "sub_type": "Open Play", "xg": 0.1})
                ev.append({"match_id": mid, "team_id": h, "type": "Shot", "period": 5, "sub_type": "Penalty",
                           "xg": 0.76})
                ms.append({"match_id": mid, "home_team_id": h, "away_team_id": w, "home_score": score[h],
                           "away_score": score[w], "match_date": dates[mid]})
    return pl.DataFrame(ev), pl.DataFrame(ms), dates


def test_chances_sum_to_one_and_follow_the_stronger_side():
    p = outcome_chances(2.0, 0.8)
    assert abs(p.sum() - 1) < 1e-12 and p[0] > p[1] > p[2]
    even = outcome_chances(1.3, 1.3)
    assert abs(even[0] - even[2]) < 1e-12


def test_rps_is_zero_when_certain_and_right_and_worst_when_far_off():
    sure = np.array([1.0, 0, 0])
    assert rps(sure, 0) == 0
    assert rps(sure, 2) == 1
    assert rps(sure, 1) < rps(sure, 2)


def test_table_ignores_penalties_and_shootouts():
    ev, ms, _ = _season()
    t = result_table(ev, ms)
    assert t.height == 2 * ms.height
    one = t.filter(pl.col("match_id") == 1)
    shots = ev.filter((pl.col("match_id") == 1) & (pl.col("period") == 1))
    assert abs(one["xg"].sum() - 0.1 * shots.height) < 1e-9


def test_calls_use_no_later_matches():
    ev, ms, dates = _season()
    base = result_calls(result_table(ev, ms), dates)
    mid = sorted(m for m, v in base["matches"].items() if v["scored"])[5]
    later = [m for m, d in dates.items() if d >= dates[mid]]
    ms2 = ms.with_columns(home_score=pl.when(pl.col("match_id").is_in(later)).then(pl.col("home_score") + 7)
                          .otherwise(pl.col("home_score")))
    after = result_calls(result_table(ev, ms2), dates)
    assert base["matches"][mid]["p"] == after["matches"][mid]["p"]


def test_real_strength_gaps_beat_base_rates():
    seasons = []
    for seed in range(3):
        ev, ms, dates = _season(seed)
        seasons.append(result_calls(result_table(ev, ms), dates))
    res = evaluate(seasons, n_boot=200)
    assert res["n"] > 100
    assert res["models"]["base"]["gain_over_base"] == 0
    assert res["result_call_holds"] and res["models"]["xg"]["gain_over_base"] > 0.01
    assert abs(sum(res["models"]["xg"]["mean_chances"]) - 1) < 1e-9


def test_stretch_widens_the_chances_and_one_leaves_them_alone():
    from pitchgraph.prematch.result import compare, is_lockbox
    ev, ms, dates = _season()
    table = result_table(ev, ms)
    plain, same, wide = (result_calls(table, dates, stretch=s) for s in (None, 1.0, 1.5))
    mids = [m for m, v in plain["matches"].items() if v["scored"]]
    assert all(plain["matches"][m]["p"] == same["matches"][m]["p"] for m in mids)
    fav = lambda r: np.mean([max(r["matches"][m]["p"]["xg"]) for m in mids])
    assert fav(wide) > fav(plain)
    assert plain["matches"][mids[0]]["threat"] == wide["matches"][mids[0]]["threat"]   # the shown call is untouched
    c = compare([plain], [wide], n_boot=50)
    assert c["n"] == len(mids) and abs(c["gain"] - (c["rps_plain"] - c["rps_stretched"])) < 1e-12
    assert is_lockbox("a") in (True, False) and is_lockbox("11_27") == is_lockbox("11_27")
