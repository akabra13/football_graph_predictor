"""Validate the possession value model.

    python scripts/validate_value.py                   # full lake (Colab/Drive)
    python scripts/validate_value.py --stream 60       # in-memory sample, stores nothing
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.value import evaluate  # noqa: E402
from pitchgraph.value.markov import MarkovValue  # noqa: E402

SAMPLE = ["2_27", "11_27", "12_27", "9_27", "7_27", "37_90", "49_107", "182_281"]

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", type=int, help="matches per season to stream into memory")
    args = ap.parse_args()
    pl.Config.set_tbl_rows(40); pl.Config.set_tbl_width_chars(140)

    t0 = time.time()
    lake = Lake.stream(SAMPLE, max_matches=args.stream) if args.stream else Lake.open()
    acts = evaluate.prepare(lake.events())
    print("actions: %d from %d matches (%.0fs)" % (acts.height, acts["match_id"].n_unique(), time.time() - t0))

    full = MarkovValue().fit(acts.lazy())
    print("monotone toward goal: %.0f%% of adjacent columns" % (100 * evaluate.monotone_share(full)))
    g = full.grid()
    print("value by x-band: " + "  ".join("%.3f" % v for v in g.mean(axis=1)[::2]))

    print("\n== held out by competition ==")
    ho = evaluate.holdout(acts)
    print(ho.select("held_out", "gender", "model", "n",
                    pl.col("skill").round(4), pl.col("corr").round(3), pl.col("calib").round(2)))
    print(ho.group_by("model").agg(pl.col("skill").mean().round(4), pl.col("corr").mean().round(3), pl.col("calib").mean().round(2)).sort("skill"))

    print("\n== data efficiency ==")
    print(evaluate.data_efficiency(acts).select(
        "train_matches", "model", pl.col("skill").round(4), pl.col("corr").round(3), pl.col("calib").round(2)))
