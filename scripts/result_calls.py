"""Pre-registered: do the threat and result calls hold? (docs/result_calls.md)

    python scripts/result_calls.py
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
from pitchgraph.prematch.pooled import pooled_skill  # noqa: E402
from pitchgraph.prematch.result import FEATS, MODELS, evaluate, result_calls, result_table  # noqa: E402

MIN_TEAMS = 8

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    t0 = time.time()
    seasons, used = [], []
    for row in eligible_seasons(lake).iter_rows(named=True):
        here = (pl.col("competition_id") == row["competition_id"]) & (pl.col("season_id") == row["season_id"])
        ev = lake.events().filter(here)
        # same competition-seasons as the pooled replay
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        table = result_table(ev, matches.filter(here))
        if table.height == 0:
            continue
        s = result_calls(table, dates)
        seasons.append(s)
        used.append(f"{row['competition']} {row['season']}")
        n = sum(m["scored"] for m in s["matches"].values())
        print(f"{used[-1]}: {n} scored matches [{time.time() - t0:.0f}s]", flush=True)

    parts = [s["arrays"] for s in seasons]
    res = {"seasons": used, "threat": {f: pooled_skill(parts, FEATS.index(f)) for f in ("xg", "goals")},
           "result": evaluate(seasons)}
    res["threat_call_holds"] = bool(res["threat"]["xg"].get("holds"))
    t = res["threat"]
    print(f"\n{len(used)} seasons")
    for f in ("xg", "goals"):
        r = t[f]
        print(f"threat call ({f}): n {r['n']}, skill {r['skill']:+.3f} ({r['skill_ci'][0]:+.3f}..{r['skill_ci'][1]:+.3f}), "
              f"team only {r['skill_team_only']:+.3f}, opponent adds {r['opponent_adds']:+.3f}, "
              f"closer than league {r['closer_than_league']:.0%}")
    print(f"-> threat call {'HOLDS' if res['threat_call_holds'] else 'does not hold'}")
    r = res["result"]
    print(f"\nresult call: {r['n']} matches; home/draw/away happened "
          + " / ".join(f"{v:.0%}" for v in r["outcome_shares"]))
    print(f"{'model':8s} {'RPS':>7s}  gain over base (90% CI)        relative  top pick right  chances given h/d/a")
    for n in MODELS:
        m = r["models"][n]
        print(f"{n:8s} {m['rps']:.4f}  {m['gain_over_base']:+.4f} ({m['gain_ci'][0]:+.4f}..{m['gain_ci'][1]:+.4f})"
              f"   {m['relative_gain']:+.1%}    {m['top_pick_right']:.0%}             "
              + " / ".join(f"{v:.0%}" for v in m["mean_chances"]))
    g = r["xg_over_goals"]
    print(f"xG-fed over goals-fed: {g['gain']:+.4f} ({g['ci'][0]:+.4f}..{g['ci'][1]:+.4f})")
    print("calibration of the xG-fed chances (all three outcomes pooled):")
    for c in r["calibration"]:
        print(f"  {c['from']:.0%}-{c['to']:.0%}: n {c['n']:5d}  predicted {c['predicted']:.1%}  happened {c['happened']:.1%}")
    print(f"worst gap in a bin of 100+: {r['calibration_worst_gap']:.1%}")
    print(f"-> result call {'HOLDS' if r['result_call_holds'] else 'does not hold'}")
    Path("result_calls.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
