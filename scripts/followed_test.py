"""Pre-registered: does doing what an instruction says go with a better outcome? (docs/followed.md)

    python scripts/followed_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.grid import TACTICAL  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import eligible_seasons  # noqa: E402
from pitchgraph.prematch import followed  # noqa: E402
from pitchgraph.prematch.audit import FEATURES, season_table  # noqa: E402
from pitchgraph.prematch.pooled import asof_arrays, pooled_skill  # noqa: E402
from pitchgraph.prematch.strategy import GAME_RULES, GAME_THRESHOLD  # noqa: E402

MIN_TEAMS = 8

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    feats = list(FEATURES) + list(followed.FEATURES)
    parts, minutes = [], []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        units = season_table(store)
        if units.height == 0:
            continue
        table = units.join(followed.level_table(ev).drop("opp_id"), on=["match_id", "team_id"],
                           how="inner").sort("match_id", "team_id")
        p = asof_arrays(table, dates, feats)
        p["weight"] = table["level_minutes"].to_numpy().astype(float)
        parts.append(p)
        minutes.append(p["weight"][p["scored"]])
        print(f"{row['competition']} {row['season']}: {int(p['scored'].sum())} team-matches", flush=True)

    minutes = np.concatenate(minutes)
    res = {"units": int(len(minutes)), "level_minutes_median": float(np.median(minutes)),
           "share_with_20_level_minutes": float((minutes >= followed.MIN_LEVEL_MINUTES).mean()),
           "outcome_call": pooled_skill(parts, feats.index(followed.OUTCOME)),
           "rules": followed.evaluate(parts, feats, GAME_RULES, GAME_THRESHOLD)}
    oc = res["outcome_call"]
    print(f"\n{res['units']} team-matches; median level minutes {res['level_minutes_median']:.0f}; "
          f"{res['share_with_20_level_minutes']:.0%} have at least 20")
    print(f"call for level-score xG difference per 90: skill {oc['skill']:+.3f} ({oc['skill_ci'][0]:+.3f}..{oc['skill_ci'][1]:+.3f})")
    print("\nxG difference per 90 level minutes, against its call: teams that did it minus teams that did not")
    print(f"{'rule':18s} {'fired':>5s} {'did it':>7s}  {'when fired (90% CI)':26s} {'when not fired (90% CI)':26s} extra when asked (90% CI)")
    for name, r in res["rules"].items():
        f, n, x = r["gap_when_fired_ci"], r["gap_when_not_fired_ci"], r["extra_when_asked_ci"]
        print(f"{name:18s} {r['fired']:5d} {r['did_it_when_fired']:7.0%}  "
              f"{r['gap_when_fired']:+.2f} ({f[0]:+.2f}..{f[1]:+.2f})      "
              f"{r['gap_when_not_fired']:+.2f} ({n[0]:+.2f}..{n[1]:+.2f})      "
              f"{r['extra_when_asked']:+.2f} ({x[0]:+.2f}..{x[1]:+.2f})  {r['verdict']}")
    Path("followed_test.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
