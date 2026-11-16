"""Pre-registered test of the strategy rules' premises (docs/strategy.md).

For every team-match in the pooled replay: when a rule fires, did the real
value land on the called side of the league mean?

    python scripts/strategy_premises.py
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
from pitchgraph.prematch.pooled import asof_arrays, premise_rows  # noqa: E402
from pitchgraph.prematch.strategy import RULES, THRESHOLD  # noqa: E402

MIN_TEAMS, MIN_FIRES, PASS_SHARE, N_BOOT = 8, 100, 0.60, 500

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    matches = lake.matches()
    dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
    feats = list(FEATURES)
    t0 = time.time()
    parts = []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        table = season_table(store)
        if table.height:
            parts.append(asof_arrays(table, dates, feats))
            print(f"{row['competition']} {row['season']} [{time.time() - t0:.0f}s]", flush=True)

    rng = np.random.default_rng(0)
    res = {"threshold_sd": THRESHOLD, "units": int(sum(p["scored"].sum() for p in parts)), "rules": {}}
    for rule, who, feature, direction, _ in RULES:
        fired, held, keys = [], [], []
        for i, p in enumerate(parts):
            f, h, m = premise_rows(p, feats.index(feature), who, direction, THRESHOLD)
            fired.append(f); held.append(h); keys.append(np.array([f"{i}_{x}" for x in m]))
        fired, held, keys = (np.concatenate(v) for v in (fired, held, keys))
        n = int(fired.sum())
        out = {"who": who, "feature": feature, "direction": direction, "fires": n,
               "fire_rate": float(fired.mean()) if len(fired) else 0.0}
        if n:
            uniq, inv = np.unique(keys, return_inverse=True)
            hit_m = np.bincount(inv, weights=(fired & held).astype(float), minlength=len(uniq))
            n_m = np.bincount(inv, weights=fired.astype(float), minlength=len(uniq))
            boots = []
            for _ in range(N_BOOT):
                w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
                if (w * n_m).sum() > 0:
                    boots.append((w * hit_m).sum() / (w * n_m).sum())
            share = float(held[fired].mean())
            lo, hi = float(np.percentile(boots, 5)), float(np.percentile(boots, 95))
            out.update(held_share=share, ci=[lo, hi],
                       not_fired_share=float(held[~fired].mean()) if (~fired).any() else None,
                       judged=bool(n >= MIN_FIRES), holds=bool(n >= MIN_FIRES and share >= PASS_SHARE and lo > 0.5))
        res["rules"][rule] = out
    judged = [r for r, o in res["rules"].items() if o.get("judged")]
    res["judged"], res["held"] = judged, [r for r in judged if res["rules"][r]["holds"]]
    res["passes_bar"] = bool(judged and len(res["held"]) == len(judged))

    print(f"\n{res['units']} team-matches; a rule fires at {THRESHOLD} SD from the league mean")
    print(f"{'rule':16s} {'fires':>6s} {'rate':>6s}  {'situation occurred (90% CI)':30s} when not fired")
    for rule, o in res["rules"].items():
        if not o["fires"]:
            print(f"{rule:16s} {0:6d}")
            continue
        print(f"{rule:16s} {o['fires']:6d} {o['fire_rate']:6.0%}  {o['held_share']:.0%} ({o['ci'][0]:.0%}..{o['ci'][1]:.0%})"
              f"{'':12s} {o['not_fired_share']:.0%}   "
              f"{'holds' if o['holds'] else 'too rare to judge' if not o['judged'] else 'DOES NOT HOLD'}")
    print(f"\n{len(res['held'])} of {len(judged)} judged rules hold -> {'PASSES BAR' if res['passes_bar'] else 'fails bar'}")
    Path("strategy_premises.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
