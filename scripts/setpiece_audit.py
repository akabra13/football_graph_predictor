"""Pre-registered set-piece audit: which set-piece calls hold? (docs/set_pieces.md)

    python scripts/setpiece_audit.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.grid import TACTICAL  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import eligible_seasons  # noqa: E402
from pitchgraph.prematch.audit import season_table  # noqa: E402
from pitchgraph.prematch.pooled import asof_arrays, pooled_skill  # noqa: E402
from pitchgraph.prematch.setpieces import FEATURES, LABELS, setpiece_table  # noqa: E402

MIN_TEAMS, USABLE = 8, 0.05

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    t0 = time.time()
    parts, used, means = [], [], []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        units = season_table(store)
        if units.height == 0:
            continue
        # the pooled replay's team-matches, with the set-piece features attached
        table = units.select("match_id", "team_id", "opp_id").join(
            setpiece_table(ev).drop("opp_id"), on=["match_id", "team_id"], how="inner").sort("match_id", "team_id")
        p = asof_arrays(table, dates, FEATURES)
        parts.append(p)
        means.append(table.select(FEATURES))
        used.append(f"{row['competition']} {row['season']}")
        print(f"{used[-1]}: {int(p['scored'].sum())} scored team-matches [{time.time() - t0:.0f}s]", flush=True)

    allrows = pl.concat(means)
    res = {"seasons": used, "scored_team_matches": int(sum(p["scored"].sum() for p in parts)),
           "features": {f: pooled_skill(parts, FEATURES.index(f)) for f in FEATURES},
           "per_match_mean": {f: float(allrows[f].drop_nans().mean()) for f in FEATURES}}
    res["into_plans"] = [f for f in FEATURES if res["features"][f].get("holds") and res["features"][f]["skill"] >= USABLE]
    print(f"\n{len(used)} seasons, {res['scored_team_matches']} scored team-matches")
    print(f"{'call':32s} {'mean':>6s}  {'skill (90% CI)':26s} {'team only':10s} {'opponent adds (90% CI)':28s} closer")
    for f in sorted(FEATURES, key=lambda f: -res["features"][f]["skill"]):
        r = res["features"][f]
        verdict = "into plans" if f in res["into_plans"] else "holds, too weak" if r["holds"] else "DOES NOT HOLD"
        print(f"{LABELS[f]:32s} {res['per_match_mean'][f]:6.2f}  {r['skill']:+.3f} ({r['skill_ci'][0]:+.3f}.."
              f"{r['skill_ci'][1]:+.3f})   {r['skill_team_only']:+.3f}     {r['opponent_adds']:+.3f} "
              f"({r['opponent_adds_ci'][0]:+.3f}..{r['opponent_adds_ci'][1]:+.3f})   {r['closer_than_league']:.0%}  {verdict}")
    Path("setpiece_audit.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
