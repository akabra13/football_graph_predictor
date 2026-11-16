"""Pre-registered: does league-aware shrinkage improve the result call?
Design and bars: docs/result_calls.md ("league-aware shrinkage").

    python scripts/result_model.py
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
from pitchgraph.prematch.pooled import asof_arrays, skill_difference  # noqa: E402
from pitchgraph.prematch.result import FEATS, compare, is_lockbox, result_calls, result_table, scored_rps  # noqa: E402

MIN_TEAMS, MAX_GAP = 8, 0.05


def show(cal):
    for c in cal:
        print(f"    {c['from']:.0%}-{c['to']:.0%}: n {c['n']:5d}  given {c['predicted']:.1%}  happened {c['happened']:.1%}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    kx = FEATS.index("xg")
    rows = []
    for row in eligible_seasons(lake).iter_rows(named=True):
        here = (pl.col("competition_id") == row["competition_id"]) & (pl.col("season_id") == row["season_id"])
        ev = lake.events().filter(here)
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        table = result_table(ev, matches.filter(here))
        if table.height == 0:
            continue
        a_fixed = asof_arrays(table, dates, FEATS, pseudo="fixed")
        a_eb = asof_arrays(table, dates, FEATS, pseudo="eb")
        fixed = result_calls(table, dates, stretch=1.0, arrays=a_fixed)
        eb = result_calls(table, dates, stretch=1.0, arrays=a_eb)
        name = f"{row['competition']} {row['season']}"
        k = float(np.median(a_eb["k_own"][a_eb["scored"], kx])) if a_eb["scored"].any() else float("nan")
        r0, r1 = scored_rps([fixed])[0], scored_rps([eb])[0]
        rows.append({"name": name, "lockbox": is_lockbox(f"{row['competition_id']}_{row['season_id']}"),
                     "fixed": fixed, "eb": eb, "part": {**a_fixed, "call_xi": a_eb["call"]},
                     "k": k, "n": int(len(r0)), "rps_fixed": float(r0.mean()), "rps_eb": float(r1.mean())})
        print(f"{name}: pseudo-matches for xG {k:.1f}; RPS {r0.mean():.4f} -> {r1.mean():.4f} ({len(r0)} matches)",
              flush=True)

    def both(sel):
        return compare([r["fixed"] for r in sel], [r["eb"] for r in sel])

    allr, tun, lock = both(rows), both([r for r in rows if not r["lockbox"]]), both([r for r in rows if r["lockbox"]])
    threat = skill_difference([r["part"] for r in rows], kx)
    res = {"seasons": [{k: r[k] for k in ("name", "lockbox", "k", "n", "rps_fixed", "rps_eb")} for r in rows],
           "all": allr, "tuning": tun, "lockbox": lock, "threat": threat}
    res["sharper"] = bool(allr["gain_ci"][0] > 0)
    res["consistent"] = bool(tun["gain"] > 0 and lock["gain"] > 0)
    res["threat_not_hurt"] = bool(not threat["hurt"])
    res["calibrated"] = bool(allr["worst_gap_stretched"] <= MAX_GAP)
    res["adopt"] = bool(res["sharper"] and res["consistent"] and res["threat_not_hurt"])
    print(f"\nall {allr['n']} matches: RPS {allr['rps_plain']:.4f} -> {allr['rps_stretched']:.4f}; gain {allr['gain']:+.4f} "
          f"({allr['gain_ci'][0]:+.4f}..{allr['gain_ci'][1]:+.4f})")
    for label, r in (("tuning seasons", tun), ("lockbox seasons", lock)):
        print(f"{label}: {r['n']} matches, gain {r['gain']:+.4f} ({r['gain_ci'][0]:+.4f}..{r['gain_ci'][1]:+.4f})")
    print(f"threat call skill: {threat['skill_plain']:+.3f} -> {threat['skill_lineup']:+.3f}; change {threat['difference']:+.4f} "
          f"({threat['ci'][0]:+.4f}..{threat['ci'][1]:+.4f})")
    print(f"calibration now (worst gap {allr['worst_gap_plain']:.1%}):")
    show(allr["calibration_plain"])
    print(f"calibration with league-aware shrinkage (worst gap {allr['worst_gap_stretched']:.1%}):")
    show(allr["calibration_stretched"])
    print(f"-> sharper: {'PASS' if res['sharper'] else 'fail'}; consistent: {'PASS' if res['consistent'] else 'fail'}; "
          f"threat not hurt: {'PASS' if res['threat_not_hurt'] else 'fail'}; calibrated: "
          f"{'PASS' if res['calibrated'] else 'fail'}; {'ADOPT' if res['adopt'] else 'keep the current model'}")
    Path("result_model.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
