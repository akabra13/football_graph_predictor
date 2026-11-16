"""Pre-registered: do line-up-weighted calls beat the plain calls? (docs/strategy.md)

    python scripts/lineup_test.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.grid import TACTICAL  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import eligible_seasons  # noqa: E402
from pitchgraph.prematch.audit import FEATURES, season_table  # noqa: E402
from pitchgraph.prematch.lineups import starters  # noqa: E402
from pitchgraph.prematch.pooled import asof_arrays, skill_difference  # noqa: E402
from pitchgraph.prematch.replay import CALLS  # noqa: E402

MIN_TEAMS, NEED_HELPED = 8, 5

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    feats = list(FEATURES)
    t0 = time.time()
    parts, shared = [], []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        table = season_table(store)
        if table.height == 0:
            continue
        ids = table["match_id"].unique().to_list()
        xi = starters(lake.scan("lineups").filter(pl.col("match_id").is_in(ids)).collect())
        sizes = [len(v) for v in xi.values()]
        parts.append(asof_arrays(table, dates, feats, xi=xi))
        # how much line-ups change: shared starters between a team's consecutive matches
        by_team: dict = {}
        for (m, t), s in sorted(xi.items(), key=lambda kv: (str(dates[kv[0][0]]), kv[0][0])):
            if t in by_team:
                shared.append(len(by_team[t] & s))
            by_team[t] = s
        print(f"{row['competition']} {row['season']}: {len(xi)} line-ups, median size "
              f"{int(np.median(sizes)) if sizes else 0} [{time.time() - t0:.0f}s]", flush=True)

    primary = [f for f, _, _ in CALLS]
    res = {"units": int(sum(p["scored"].sum() for p in parts)),
           "shared_starters_consecutive": {"mean": float(np.mean(shared)), "p10": float(np.percentile(shared, 10)),
                                           "median": float(np.median(shared))},
           "features": {f: skill_difference(parts, feats.index(f)) for f in feats}}
    helped = [f for f in primary if res["features"][f]["helped"]]
    hurt = [f for f in primary if res["features"][f]["hurt"]]
    res.update(primary=primary, helped=helped, hurt=hurt,
               switch_to_lineup_calls=bool(len(helped) >= NEED_HELPED and not hurt))
    print(f"\n{res['units']} team-matches; shared starters between consecutive matches: "
          f"mean {res['shared_starters_consecutive']['mean']:.1f}, median "
          f"{res['shared_starters_consecutive']['median']:.0f}, 10th percentile "
          f"{res['shared_starters_consecutive']['p10']:.0f}")
    print(f"{'feature':34s} {'plain':>7s} {'line-up':>8s}  difference (90% CI)")
    for f in sorted(feats, key=lambda f: -res["features"][f]["difference"]):
        r = res["features"][f]
        print(f"{'* ' if f in primary else '  '}{f:32s} {r['skill_plain']:+.3f}  {r['skill_lineup']:+.3f}   "
              f"{r['difference']:+.4f} ({r['ci'][0]:+.4f}..{r['ci'][1]:+.4f})"
              f"{'  helped' if r['helped'] else '  HURT' if r['hurt'] else ''}")
    print(f"\nprimary calls helped: {len(helped)} of {len(primary)}, hurt: {len(hurt)} -> "
          f"{'SWITCH to line-up calls' if res['switch_to_lineup_calls'] else 'keep the plain calls'}")
    Path("lineup_test.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
