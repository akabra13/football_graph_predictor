"""Pre-registered test of the set-piece rules' premises (docs/set_pieces.md).

    python scripts/setpiece_premises.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.grid import TACTICAL  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import eligible_seasons  # noqa: E402
from pitchgraph.prematch.audit import season_table  # noqa: E402
from pitchgraph.prematch.pooled import asof_arrays, premise_test  # noqa: E402
from pitchgraph.prematch.setpieces import FEATURES, setpiece_table  # noqa: E402
from pitchgraph.prematch.strategy import SP_RULES, THRESHOLD  # noqa: E402

MIN_TEAMS = 8

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    parts = []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        units = season_table(store)
        if units.height == 0:
            continue
        table = units.select("match_id", "team_id", "opp_id").join(
            setpiece_table(ev).drop("opp_id"), on=["match_id", "team_id"], how="inner").sort("match_id", "team_id")
        parts.append(asof_arrays(table, dates, FEATURES))
        print(f"{row['competition']} {row['season']}", flush=True)

    rules = premise_test(parts, FEATURES, SP_RULES, THRESHOLD)
    res = {"threshold_sd": THRESHOLD, "units": int(sum(p["scored"].sum() for p in parts)), "rules": rules,
           "into_plans": [r for r, o in rules.items() if o["holds"]]}
    print(f"\n{res['units']} team-matches; a rule fires at {THRESHOLD} SD above the league mean")
    print(f"{'rule':20s} {'fires':>6s} {'rate':>6s}  situation occurred (90% CI)   when not fired")
    for rule, o in rules.items():
        if not o["fires"]:
            print(f"{rule:20s} {0:6d}")
            continue
        print(f"{rule:20s} {o['fires']:6d} {o['fire_rate']:6.0%}  {o['held_share']:.0%} ({o['ci'][0]:.0%}..{o['ci'][1]:.0%})"
              f"{'':14s} {o['not_fired_share']:.0%}   "
              f"{'holds' if o['holds'] else 'too rare to judge' if not o['judged'] else 'DOES NOT HOLD'}")
    print(f"\ninto plans: {', '.join(res['into_plans']) or 'none'}")
    Path("setpiece_premises.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
