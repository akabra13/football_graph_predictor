"""Render data-backed flow-map posts (posts/flow/*.json).

Each spec names a team, season and competition. The season is streamed from
StatsBomb Open Data into memory (nothing is saved), analysed once, and the
team's flow graph and denial plan are drawn.

    python scripts/build_flow_posts.py --out out/posts
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from pitchgraph.cli import resolve  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.figures.flow import flow_data, flow_map  # noqa: E402
from pitchgraph.library.build import build_season, fit_value_model, player_names  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--specs", default=str(ROOT / "posts" / "flow"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    by_key = defaultdict(list)
    for f in sorted(Path(args.specs).glob("*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        hit = resolve(spec["team"], spec["season"], spec.get("competition"))
        by_key[hit["key"]].append((spec, hit))

    captions = []
    for key, items in by_key.items():
        lake = Lake.stream([key])
        cid, sid = (int(x) for x in key.split("_"))
        m = lake.matches().filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid)).row(0, named=True)
        row = {"key": key, "competition_id": cid, "season_id": sid, "competition": m["competition"],
               "season": m["season"], "gender": m["gender"]}
        _, season = build_season(lake, row, fit_value_model(lake), player_names(lake))
        for spec, hit in items:
            tid = hit["team_id"]
            if tid not in season.attack:
                print(f"skip {spec['id']}: {hit['team']} has too few matches in {key}")
                continue
            usage = season.counts.team(tid, "attack").total()[0][:, : season.grid.n]
            data = flow_data(season.attack[tid], season.league, usage)
            fill = {"team": spec.get("display", hit["team"]), "season_short": spec["season"],
                    **{k: data["links"][0][k] for k in ("from_label", "to_label", "lo", "hi")}}
            path = flow_map(data, out / f"{spec['id']}.png", spec["title"].format(**fill),
                            spec.get("subtitle", ""), spec.get("note", ""))
            (out / f"{spec['id']}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
            captions.append(f"## {spec['id']}\n\n{spec['caption'].format(**fill)}\n")
            print(f"rendered {path}  kappa={season.kappa}  teams={len(season.eligible)}")
            for k in data["links"]:
                print(f"   {k['from_label']} -> {k['to_label']}: {k['lo']:.3f}-{k['hi']:.3f} "
                      f"(league {k['league_lo']:.3f}-{k['league_hi']:.3f}) unusual={k['unusual']}")
    with open(out / "captions.md", "a", encoding="utf-8") as fh:
        fh.write("\n".join(captions))
