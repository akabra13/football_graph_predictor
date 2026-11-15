"""Pre-registered test of the denial planner against real matches.
See docs/denial_test.md for the design and the pass bar.

    python scripts/validate_denial.py            # every eligible league season in the lake
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

from pitchgraph.chains import denial  # noqa: E402
from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.denial_test import evaluate, league_of, match_rows, model_drops  # noqa: E402
from pitchgraph.chains.grid import TACTICAL  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import eligible_seasons  # noqa: E402

MIN_TEAMS = 8            # teams with 10+ matches, so a league baseline exists
MIN_LINK_SHARE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.01   # pooled share of moves a link needs
PASS_SPEARMAN = 0.5

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    seasons = eligible_seasons(lake)
    t0 = time.time()
    Y, U, M, S, leagues, used = [], [], [], [], [], []
    for row in seasons.iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        n_teams = sum(store.team(t).n_matches >= 10 for t in store.teams)
        if n_teams < MIN_TEAMS:
            continue
        y, u, m, s = match_rows(store)
        if len(y) == 0:
            continue
        Y.append(y); U.append(u); S.append(s)
        M.append(np.array([f"{row['key']}_{x}" for x in m]))
        leagues.append(league_of(store)); used.append(f"{row['competition']} {row['season']}")
        print(f"{used[-1]}: {n_teams} teams, {len(y)} team-matches [{time.time() - t0:.0f}s]", flush=True)

    y, U, M, S = np.concatenate(Y), np.concatenate(U), np.concatenate(M), np.concatenate(S)
    share = S.mean(0)
    np.fill_diagonal(share, 0.0)
    links = [(int(a), int(b)) for a, b in zip(*np.where(share >= MIN_LINK_SHARE))]
    X = np.column_stack([U[:, a, b] for a, b in links])
    drops = np.mean([model_drops(lg, links) for lg in leagues], axis=0)
    mid = drops.mean(1)
    usage = np.array([share[a, b] for a, b in links])

    res = evaluate(y, X, M, mid, usage)
    inside = [bool(lo <= b <= hi) for b, (lo, hi) in zip(res["beta"], drops)]
    res.update(
        seasons=used, team_matches=int(len(y)), matches=int(len(np.unique(M))),
        links=[{"from": denial.region_name(a), "to": denial.region_name(b), "usage": float(usage[i]),
                "model_adapt": float(drops[i, 0]), "model_no_adapt": float(drops[i, 1]),
                "observed": res["beta"][i], "observed_ci": res["beta_ci"][i], "inside_range": inside[i]}
               for i, (a, b) in enumerate(links)],
        share_inside_range=float(np.mean(inside)),
        passes_bar=bool(res["spearman_model"] >= PASS_SPEARMAN and res["spearman_model_ci"][0] > 0
                        and res["spearman_model"] > res["spearman_usage"]))
    print(f"\n{len(used)} seasons, {res['team_matches']} team-matches, {len(links)} links")
    print(f"rank agreement with planner: {res['spearman_model']:.3f} (90% CI {res['spearman_model_ci']})")
    print(f"rank agreement with usage:   {res['spearman_usage']:.3f} (90% CI {res['spearman_usage_ci']})")
    print(f"difference CI {res['spearman_diff_ci']}; inside planner range: {res['share_inside_range']:.0%}")
    print("PASSES BAR" if res["passes_bar"] else "fails bar")
    for k in sorted(res["links"], key=lambda r: -r["model_no_adapt"]):
        print(f"  {k['from']:32s} -> {k['to']:32s} model {k['model_adapt']:.3f}-{k['model_no_adapt']:.3f}"
              f"  observed {k['observed']:+.3f} ({k['observed_ci'][0]:+.3f}..{k['observed_ci'][1]:+.3f})")
    Path("denial_test_results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
