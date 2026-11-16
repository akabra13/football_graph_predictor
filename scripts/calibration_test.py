"""Pre-registered: does stretching the threat calls fix the too-cautious chances?
Design and bars: docs/result_calls.md ("fixing the too-cautious chances").

    python scripts/calibration_test.py
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
from pitchgraph.prematch.pooled import asof_arrays  # noqa: E402
from pitchgraph.prematch.result import FEATS, GRID, compare, is_lockbox, result_calls, result_table, scored_rps  # noqa: E402

MIN_TEAMS, MIN_LOCKBOX, MAX_GAP = 8, 300, 0.05


def show(cal):
    for c in cal:
        print(f"    {c['from']:.0%}-{c['to']:.0%}: n {c['n']:5d}  given {c['predicted']:.1%}  happened {c['happened']:.1%}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    groups = {"tuning": [], "lockbox": []}
    names = {"tuning": [], "lockbox": []}
    for row in eligible_seasons(lake).iter_rows(named=True):
        here = (pl.col("competition_id") == row["competition_id"]) & (pl.col("season_id") == row["season_id"])
        ev = lake.events().filter(here)
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        table = result_table(ev, matches.filter(here))
        if table.height == 0:
            continue
        which = "lockbox" if is_lockbox(f"{row['competition_id']}_{row['season_id']}") else "tuning"
        groups[which].append((table, asof_arrays(table, dates, FEATS)))
        names[which].append(f"{row['competition']} {row['season']}")

    def calls(which, s):
        return [result_calls(t, dates, stretch=s, arrays=a) for t, a in groups[which]]

    for which in groups:
        print(f"{which}: {', '.join(names[which])}")
    curve = {s: float(scored_rps(calls("tuning", s))[0].mean()) for s in GRID}
    best = min(GRID, key=lambda s: curve[s])
    print("\ntuning seasons, RPS by stretch:")
    for s in GRID:
        print(f"  s = {s:.1f}: {curve[s]:.5f}{'  <- chosen' if s == best else ''}")

    res = {"tuning": names["tuning"], "lockbox": names["lockbox"], "tuning_curve": curve, "chosen": best}
    r = compare(calls("lockbox", 1.0), calls("lockbox", best))
    res["lockbox_result"] = r
    enough = r["n"] >= MIN_LOCKBOX and best > 1.0
    res["sharper"] = bool(enough and r["gain_ci"][0] > 0)
    res["calibrated"] = bool(enough and r["worst_gap_stretched"] <= MAX_GAP)
    res["adopt"] = res["sharper"]
    print(f"\nlockbox: {r['n']} matches, s = {best:.1f}")
    print(f"  RPS {r['rps_plain']:.4f} -> {r['rps_stretched']:.4f}; gain {r['gain']:+.4f} "
          f"({r['gain_ci'][0]:+.4f}..{r['gain_ci'][1]:+.4f})")
    print(f"  calibration without the stretch (worst gap {r['worst_gap_plain']:.1%}):")
    show(r["calibration_plain"])
    print(f"  calibration with it (worst gap {r['worst_gap_stretched']:.1%}):")
    show(r["calibration_stretched"])
    print(f"-> sharper: {'PASS' if res['sharper'] else 'fail'}; calibrated: {'PASS' if res['calibrated'] else 'fail'}; "
          f"{'ADOPT s = %.1f' % best if res['adopt'] else 'keep s = 1'}")
    Path("calibration_test.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
