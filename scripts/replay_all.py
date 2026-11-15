"""Pre-registered pooled replay: the replay's calls for every team, scored together.
Design and bar: docs/predictability_audit.md ("Pooled replay").

    python scripts/replay_all.py
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
from pitchgraph.prematch.pooled import asof_arrays, pooled_skill, team_shares  # noqa: E402
from pitchgraph.prematch.replay import CALLS  # noqa: E402

MIN_TEAMS = 8
PASS_COUNT = 7

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    t0 = time.time()
    parts, used = [], []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        table = season_table(store)
        if table.height == 0:
            continue
        p = asof_arrays(table, dates, list(FEATURES))
        parts.append(p)
        used.append(f"{row['competition']} {row['season']}")
        print(f"{used[-1]}: {int(p['scored'].sum())} scored team-matches [{time.time() - t0:.0f}s]", flush=True)

    feats = list(FEATURES)
    res = {"seasons": used, "scored_team_matches": int(sum(p["scored"].sum() for p in parts)),
           "features": {f: pooled_skill(parts, feats.index(f)) for f in feats}}
    primary = [f for f, _, _ in CALLS]
    held = [f for f in primary if res["features"][f].get("holds")]
    shares = team_shares(parts, [feats.index(f) for f in primary])
    res.update(primary=primary, primary_held=held, passes_bar=bool(len(held) >= PASS_COUNT),
               teams=len(shares), team_share_median=float(np.median(shares)),
               team_share_quartiles=[float(np.percentile(shares, 25)), float(np.percentile(shares, 75))],
               teams_above_half=float(np.mean(np.array(shares) > 0.5)),
               team_share_min=float(np.min(shares)), team_share_max=float(np.max(shares)))

    print(f"\n{len(used)} seasons, {res['scored_team_matches']} scored team-matches")
    print(f"{'feature':34s} {'skill (90% CI)':26s} {'team only':10s} {'opponent adds (90% CI)':28s} closer")
    for f in sorted(feats, key=lambda f: -res["features"][f]["skill"]):
        r = res["features"][f]
        print(f"{'* ' if f in primary else '  '}{f:32s} {r['skill']:+.3f} ({r['skill_ci'][0]:+.3f}..{r['skill_ci'][1]:+.3f})   "
              f"{r['skill_team_only']:+.3f}     {r['opponent_adds']:+.3f} ({r['opponent_adds_ci'][0]:+.3f}.."
              f"{r['opponent_adds_ci'][1]:+.3f})   {r['closer_than_league']:.0%}{'' if r['holds'] else '  DOES NOT HOLD'}")
    print(f"\nprimary calls holding: {len(held)} of {len(primary)} -> {'PASSES BAR' if res['passes_bar'] else 'fails bar'}")
    print(f"per team ({res['teams']} teams): median share of calls closer than league {res['team_share_median']:.0%} "
          f"(quartiles {res['team_share_quartiles'][0]:.0%}-{res['team_share_quartiles'][1]:.0%}, "
          f"min {res['team_share_min']:.0%}, max {res['team_share_max']:.0%}); "
          f"{res['teams_above_half']:.0%} of teams above half")
    Path("replay_all_results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
