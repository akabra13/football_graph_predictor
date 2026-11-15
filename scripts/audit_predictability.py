"""Pre-registered predictability audit (docs/predictability_audit.md).

    python scripts/audit_predictability.py
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
from pitchgraph.prematch.audit import FEATURES, GRAPH_FEATURES, predictions, score, season_table  # noqa: E402

MIN_TEAMS = 8

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    t0 = time.time()
    tables, used = [], []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        t = season_table(store)
        if t.height:
            tables.append(t)
            used.append(f"{row['competition']} {row['season']}")
            print(f"{used[-1]}: {t.height} team-matches [{time.time() - t0:.0f}s]", flush=True)

    res = {"seasons": used, "team_matches": int(sum(t.height for t in tables)), "features": {}}
    for f in FEATURES:
        res["features"][f] = score([predictions(t, f) for t in tables])
    order = sorted(FEATURES, key=lambda f: -res["features"][f]["r2_team"])
    print(f"\n{len(used)} seasons, {res['team_matches']} team-matches\n")
    print(f"{'feature':34s} {'R2 team (90% CI)':26s} {'+ opponent (90% CI)':28s} tier")
    for f in order:
        r = res["features"][f]
        print(f"{f:34s} {r['r2_team']:+.3f} ({r['r2_team_ci'][0]:+.3f}..{r['r2_team_ci'][1]:+.3f})   "
              f"{r['gain_opponent']:+.3f} ({r['gain_opponent_ci'][0]:+.3f}..{r['gain_opponent_ci'][1]:+.3f})   "
              f"{r['tier']}{'  opponent matters' if r['opponent_matters'] else ''}"
              f"{'  [graph]' if f in GRAPH_FEATURES else ''}")
    Path("predictability_audit.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
