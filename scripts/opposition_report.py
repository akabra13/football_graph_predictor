"""Generate an opposition report.

    # Colab / Drive (normal): value model fit on the whole lake, report saved to
    # $PITCHGRAPH_DATA/reports/
    python scripts/opposition_report.py --competition 2_27 --team "Leicester City"

    # Stream one competition-season into memory instead of using the lake
    python scripts/opposition_report.py --competition 2_27 --team "Leicester City" --stream --out report.html
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from pitchgraph.analysis.context import prepare  # noqa: E402
from pitchgraph.analysis.scout import League  # noqa: E402
from pitchgraph.config import require_data_root  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.report import opposition, render  # noqa: E402
from pitchgraph.value.markov import MarkovValue  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Generate an opposition report.")
    ap.add_argument("--competition", required=True, help='competition-season key, e.g. "2_27"')
    ap.add_argument("--team", required=True)
    ap.add_argument("--stream", action="store_true", help="stream the season into memory")
    ap.add_argument("--out", help="output HTML path (default: $PITCHGRAPH_DATA/reports/)")
    ap.add_argument("--boot", type=int, default=200)
    args = ap.parse_args()
    cid, sid = (int(x) for x in args.competition.split("_"))

    t0 = time.time()
    lake = Lake.stream([args.competition]) if args.stream else Lake.open()
    events = lake.events()
    in_poss = events.filter(pl.col("team_id") == pl.col("possession_team_id"))
    # With the lake, the value model learns from every competition; streaming
    # uses just the one season.
    model = MarkovValue().fit(in_poss)
    season = events.filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid))
    ev = prepare(season, model)
    first = ev.row(0, named=True)
    names = {}
    if lake.has("lineups"):
        lu = lake.scan("lineups").select("player_id", "nickname").drop_nulls().unique("player_id").collect()
        names = dict(lu.iter_rows())
    league = League(ev, names=names)
    print(f"prepared {ev.height:,} events, {len(league.teams)} teams ({time.time() - t0:.0f}s)")

    rep = opposition.build(league, args.team, {
        "competition": first["competition"], "season": first["season"],
        "model": f"{model.name}, {model.nx}x{model.ny} zones"}, n_boot=args.boot)
    html = render.render(rep)

    if args.out:
        out = Path(args.out)
    else:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{args.team}_{first['season']}").strip("_")
        out = require_data_root() / "reports" / f"{slug}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html) / 1024:.0f} KB, {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
