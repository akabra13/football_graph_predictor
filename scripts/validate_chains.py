"""Validate team flow graphs: style re-identification and the matchup experiment.

    python scripts/validate_chains.py                        # every complete league in the lake
    python scripts/validate_chains.py --stream 2_27 37_90    # stream seasons into memory
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from pitchgraph.chains import validate  # noqa: E402
from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402

COMPLETE = list(validate.COMPLETE_LEAGUES)


def run(events: pl.LazyFrame, label: str) -> dict:
    t0 = time.time()
    store = CountStore.from_events(events)
    league, teams, kappa, scores = validate.prepare(store)
    reid = validate.reidentification(store, league, teams, kappa)
    mu = validate.matchup_experiment(store, kappa)
    summary = validate.summarise_matchup(mu)
    out = {"season": label, "teams": len(teams), "kappa": kappa,
           "reid_top1": reid["top1"], "reid_top3": reid["top3"], "chance": reid["chance_top1"],
           **summary, "seconds": round(time.time() - t0)}
    print(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", nargs="*", help="competition-season keys to stream into memory")
    args = ap.parse_args()
    keys = args.stream if args.stream else COMPLETE
    lake = None if args.stream else Lake.open()
    for key in keys:
        cid, sid = (int(x) for x in key.split("_"))
        src = Lake.stream([key]) if args.stream else lake
        ev = src.events().filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid))
        run(ev, key)
