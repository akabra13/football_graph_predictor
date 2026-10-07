"""pitchgraph: scouting reports and matchups by team name.

    pitchgraph teams --search leic
    pitchgraph report "Leicester City" 2015/16
    pitchgraph matchup "Arsenal" "Leicester City" 2015/16
    pitchgraph library                       # build everything (Colab + Drive)

Reports use the Drive lake when PITCHGRAPH_DATA is set. With --stream they
stream just the one competition-season into memory instead, which works on a
laptop that stores no data (the report itself is still written where --out
says, or to the data root).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import polars as pl


def normalise_season(s: str) -> str:
    """'2015/16', '15/16', '2015-16' -> '2015/2016'; '2023' stays '2023'."""
    m = re.fullmatch(r"(\d{2,4})\s*[/-]\s*(\d{2,4})", s.strip())
    if not m:
        return s.strip()
    a, b = m.groups()
    a = int(a) if len(a) == 4 else 2000 + int(a)
    if len(b) == 4:
        b = int(b)
    else:
        b = (a // 100) * 100 + int(b)
        if b < a:              # 1999/00 crosses into the next century
            b += 100
    return f"{a}/{b}"


def _catalogue() -> pl.DataFrame:
    """Every (competition-season, team) with its match count, from the open data
    metadata, held in memory only."""
    from concurrent.futures import ThreadPoolExecutor

    from pitchgraph.data.statsbomb import StatsBomb
    sb = StatsBomb(memory_items=0)
    comps = sb.competitions()

    def rows(c):
        out = {}
        for m in StatsBomb(memory_items=0).matches(c["competition_id"], c["season_id"]):
            for side in ("home_team", "away_team"):
                k = (m[side][f"{side}_id"], m[side][f"{side}_name"])
                out[k] = out.get(k, 0) + 1
        return [{"key": f"{c['competition_id']}_{c['season_id']}", "competition": c["competition_name"],
                 "season": c["season_name"], "gender": c.get("competition_gender"),
                 "team_id": t, "team": n, "matches": k} for (t, n), k in out.items()]

    with ThreadPoolExecutor(8) as pool:
        return pl.DataFrame([r for rs in pool.map(rows, comps) for r in rs])


def resolve(team: str, season: str, competition: str | None = None) -> dict:
    cat = _catalogue()
    season = normalise_season(season)
    hits = cat.filter((pl.col("season") == season)
                      & pl.col("team").str.to_lowercase().str.contains(re.escape(team.lower())))
    if competition:
        hits = hits.filter(pl.col("competition").str.to_lowercase().str.contains(competition.lower()))
    exact = hits.filter(pl.col("team").str.to_lowercase() == team.lower())
    hits = exact if exact.height else hits
    if hits.height == 0:
        raise SystemExit(f'No team matching "{team}" in {season}. Try: pitchgraph teams --search "{team}"')
    if hits.height > 1:
        print(f'"{team}" {season} matches more than one team or competition:')
        for r in hits.iter_rows(named=True):
            print(f"  {r['team']} - {r['competition']} ({r['matches']} matches)")
        raise SystemExit("Add --competition, or use the full team name.")
    return hits.row(0, named=True)


def _season_json(key: str, stream: bool) -> dict:
    from pitchgraph.data.lake import Lake
    from pitchgraph.library.build import build_season, fit_value_model, player_names
    t0 = time.time()
    lake = Lake.stream([key]) if stream else Lake.open()
    model = fit_value_model(lake)
    cid, sid = (int(x) for x in key.split("_"))
    m = lake.matches().filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid)).row(0, named=True)
    row = {"key": key, "competition_id": cid, "season_id": sid, "competition": m["competition"],
           "season": m["season"], "gender": m["gender"]}
    js, _ = build_season(lake, row, model, player_names(lake))
    print(f"analysed {row['competition']} {row['season']} in {time.time() - t0:.0f}s")
    return js


def _write(html: str, out: str | None, slug: str) -> Path:
    if out:
        path = Path(out)
    else:
        from pitchgraph.config import require_data_root
        path = require_data_root() / "reports" / f"{slug}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def cmd_teams(args):
    cat = _catalogue()
    if args.search:
        cat = cat.filter(pl.col("team").str.to_lowercase().str.contains(re.escape(args.search.lower())))
    cat = cat.filter(pl.col("matches") >= args.min_matches).sort("team", "competition", "season")
    if cat.height == 0:
        print("No teams found.")
        return
    for r in cat.iter_rows(named=True):
        print(f"{r['team']:<32} {r['competition']:<28} {r['season']:<10} {r['matches']:>4} matches")


def cmd_report(args):
    from pitchgraph.library.package import standalone_html
    hit = resolve(args.team, args.season, args.competition)
    js = _season_json(hit["key"], args.stream)
    if str(hit["team_id"]) not in js["teams"]:
        raise SystemExit(f"{hit['team']} has too few matches in {hit['season']} for a report.")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{hit['team']}_{hit['season']}").strip("_")
    path = _write(standalone_html(js, f"#team-{hit['key']}-{hit['team_id']}"), args.out, slug)
    print(f"wrote {path}")


def cmd_matchup(args):
    from pitchgraph.library.package import standalone_html
    a = resolve(args.attack, args.season, args.competition)
    b = resolve(args.defence, args.season, args.competition)
    if a["key"] != b["key"]:
        raise SystemExit("Both teams must be in the same competition-season.")
    js = _season_json(a["key"], args.stream)
    mu = js["matchups"].get(f"{a['team_id']}-{b['team_id']}")
    if mu is None:
        raise SystemExit("One of these teams has too few matches for a matchup.")
    names = js["lane_names"]
    print(f"\n{a['team']} attacking {b['team']} ({a['competition']} {a['season']})")
    print(f"  expected threat vs their usual: {100 * mu['threat_vs_usual']:+.0f}%")
    print("  final-third entries by lane (usual -> against them):")
    for n, u, m in zip(names, mu["lanes_own"], mu["lanes_matchup"]):
        print(f"    {n:<18} {100 * u:5.1f}% -> {100 * m:5.1f}%")
    print(f"  {b['team']} give them more of: " + "; ".join(f"{l['from_label']} -> {l['to_label']}" for l in mu["more_of"]))
    print(f"  {b['team']} take away:        " + "; ".join(f"{l['from_label']} -> {l['to_label']}" for l in mu["less_of"]))
    for h in mu["head_to_head"]:
        print(f"  met {h['date']}: {h['score'][0]}-{h['score'][1]} (xG {h['xg'][0]:.2f}-{h['xg'][1]:.2f})")
    if args.out or not args.stream:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{a['team']}_vs_{b['team']}_{a['season']}").strip("_")
        path = _write(standalone_html(js, f"#vs-{a['key']}-{a['team_id']}-{b['team_id']}"), args.out, slug)
        print(f"wrote {path}")


def cmd_library(args):
    from pitchgraph.config import require_data_root
    from pitchgraph.data.lake import Lake
    from pitchgraph.library.build import build_all
    from pitchgraph.library.package import copy_app
    out = Path(args.out) if args.out else require_data_root() / "library"
    build_all(Lake.open(), out, keys=args.keys, force=args.force)
    copy_app(out)
    print(f"library ready in {out}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="pitchgraph", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("teams", help="list teams and seasons in the open data")
    p.add_argument("--search", help="part of a team name")
    p.add_argument("--min-matches", type=int, default=1)
    p.set_defaults(fn=cmd_teams)

    for name, fn, helptext in (("report", cmd_report, "opposition report for one team"),
                               ("matchup", cmd_matchup, "one team attacking another")):
        p = sub.add_parser(name, help=helptext)
        if name == "report":
            p.add_argument("team")
        else:
            p.add_argument("attack")
            p.add_argument("defence")
        p.add_argument("season", help="e.g. 2015/16 or 2023")
        p.add_argument("--competition", help="part of the competition name, if ambiguous")
        p.add_argument("--stream", action="store_true", help="stream the season into memory instead of the lake")
        p.add_argument("--out", help="output HTML path (default: $PITCHGRAPH_DATA/reports/)")
        p.set_defaults(fn=fn)

    p = sub.add_parser("library", help="build the full library (needs the Drive lake)")
    p.add_argument("--keys", nargs="*", help="only these competition-seasons, e.g. 2_27")
    p.add_argument("--force", action="store_true", help="rebuild seasons that already exist")
    p.add_argument("--out", help="output folder (default: $PITCHGRAPH_DATA/library)")
    p.set_defaults(fn=cmd_library)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
