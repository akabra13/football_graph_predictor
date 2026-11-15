"""Game-by-game pre-match replay for one team (second half of a season).

Streams the season from StatsBomb Open Data into memory; nothing is saved
except the report.

    python scripts/season_replay.py "Leicester City" 2015/16 --competition "Premier League" --out out/replay
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from pitchgraph.cli import resolve  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import player_names  # noqa: E402
from pitchgraph.prematch.replay import replay  # noqa: E402
from pitchgraph.prematch.report import render_html  # noqa: E402

COLS = ["match_id", "team_id", "possession_team_id", "possession", "home_team_id", "away_team_id", "period",
        "play_pattern", "idx", "type", "sub_type", "outcome", "xg", "x", "y", "end_x", "end_y",
        "player_id", "player", "recipient_id"]

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("team")
    ap.add_argument("season")
    ap.add_argument("--competition")
    ap.add_argument("--start", type=float, default=0.5, help="fraction of the season already played")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    hit = resolve(args.team, args.season, args.competition)
    lake = Lake.stream([hit["key"]])
    cid, sid = (int(x) for x in hit["key"].split("_"))
    matches = lake.matches().filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid))
    ev = lake.events().select(COLS).collect()
    rep = replay(ev, matches, hit["team_id"], player_names(lake), start_fraction=args.start)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", f"{hit['team']}_{hit['season']}".lower()).strip("_")
    (out / f"{slug}.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / f"{slug}.html").write_text(render_html(rep, hit["team"], hit["competition"], hit["season"]),
                                      encoding="utf-8")
    print(json.dumps(rep["summary"], indent=1))
    for g in rep["games"]:
        o = g.get("outcome")
        if o:
            print(f"{g['date']} {g['opponent']:24s} {g['score'][0]}-{g['score'][1]}  "
                  f"they: {'hit ' if o['they']['top_hit']['matchup'] else 'miss'} tv {o['they']['tv']['matchup']:.2f}/"
                  f"{o['they']['tv']['own']:.2f}  lever {o['lever']['vs_usual']:+.0%}  "
                  f"threat {o['their_threat']['vs_expected']:+.0%}")
