"""Pre-registered team-specific planner test (docs/denial_test.md).

Does a team whose own chain depends more on a link lose more threat when
that link is suppressed in a match?

    python scripts/validate_team_denial.py
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
from pitchgraph.chains.denial_test import gamma_test, match_rows  # noqa: E402
from pitchgraph.chains.grid import TACTICAL  # noqa: E402
from pitchgraph.chains.validate import prepare  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import eligible_seasons  # noqa: E402

MIN_TEAMS = 8
MIN_LINK_SHARE = 0.0025
# region index = third * 5 + lane; final third is 10..14 (left flank .. right flank)
PRIMARY = [(11, 12), (13, 12)]                 # half-space -> centre, final third
SECONDARY = PRIMARY + [(10, 11), (14, 13)]     # + flank -> half-space, final third

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    t0 = time.time()
    Y, U, M, S, E = [], [], [], [], []
    for row in eligible_seasons(lake).iter_rows(named=True):
        ev = lake.events().filter((pl.col("competition_id") == row["competition_id"])
                                  & (pl.col("season_id") == row["season_id"]))
        store = CountStore.from_events(ev, TACTICAL)
        if sum(store.team(t).n_matches >= 10 for t in store.teams) < MIN_TEAMS:
            continue
        _, _, kappa, _ = prepare(store)
        y, u, m, s, e = match_rows(store, excess_links=SECONDARY, kappa=kappa)
        if len(y) == 0:
            continue
        Y.append(y); U.append(u); S.append(s); E.append(e)
        M.append(np.array([f"{row['key']}_{x}" for x in m]))
        print(f"{row['competition']} {row['season']}: kappa={kappa}, {len(y)} team-matches "
              f"[{time.time() - t0:.0f}s]", flush=True)

    y, U, M, S, E = (np.concatenate(v) for v in (Y, U, M, S, E))
    share = S.mean(0)
    np.fill_diagonal(share, 0.0)
    links = [(int(a), int(b)) for a, b in zip(*np.where(share >= MIN_LINK_SHARE))]
    X = np.column_stack([U[:, a, b] for a, b in links])

    def z(tested):
        return sum(U[:, a, b] * E[:, SECONDARY.index((a, b))] for a, b in tested)

    res = {"team_matches": int(len(y)), "links": len(links),
           "excess_sd": {f"{a}->{b}": float(E[:, i].std()) for i, (a, b) in enumerate(SECONDARY)},
           "primary": gamma_test(y, X, z(PRIMARY), M),
           "secondary": gamma_test(y, X, z(SECONDARY), M)}
    print(json.dumps(res, indent=1))
    Path("team_denial_results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
