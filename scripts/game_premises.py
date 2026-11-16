"""Pre-registered test of the game-specific rules' premises
(docs/strategy.md, "instructions about this game").

    python scripts/game_premises.py
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
from pitchgraph.prematch import setpieces  # noqa: E402
from pitchgraph.prematch.audit import FEATURES, season_table  # noqa: E402
from pitchgraph.prematch.pooled import asof_arrays, premise_test  # noqa: E402
from pitchgraph.prematch.strategy import GAME_RULES, GAME_THRESHOLD  # noqa: E402

MIN_TEAMS, NEED = 8, 6

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    feats = list(FEATURES) + list(setpieces.FEATURES)
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
        table = units.join(setpieces.setpiece_table(ev).drop("opp_id"), on=["match_id", "team_id"],
                           how="inner").sort("match_id", "team_id")
        parts.append(asof_arrays(table, dates, feats))
        print(f"{row['competition']} {row['season']}", flush=True)

    rules = premise_test(parts, feats, GAME_RULES, GAME_THRESHOLD, reference="usual")
    held = [r for r, o in rules.items() if o["holds"]]
    res = {"threshold_sd": GAME_THRESHOLD, "units": int(sum(p["scored"].sum() for p in parts)), "rules": rules,
           "held": held, "rebuild": bool(len(held) >= NEED)}
    print(f"\n{res['units']} team-matches; a rule fires at {GAME_THRESHOLD} SD from a normal week for the team")
    print(f"{'rule':22s} {'fires':>6s} {'rate':>6s}  situation occurred (90% CI)   when not fired")
    for rule, o in rules.items():
        if not o["fires"]:
            print(f"{rule:22s} {0:6d}")
            continue
        print(f"{rule:22s} {o['fires']:6d} {o['fire_rate']:6.0%}  {o['held_share']:.0%} ({o['ci'][0]:.0%}..{o['ci'][1]:.0%})"
              f"{'':14s} {o['not_fired_share']:.0%}   "
              f"{'holds' if o['holds'] else 'too rare to judge' if not o['judged'] else 'DOES NOT HOLD'}")
    print(f"\n{len(held)} of {len(rules)} rules hold -> {'REBUILD the plans on these' if res['rebuild'] else 'keep the league-based lines'}")
    Path("game_premises.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
