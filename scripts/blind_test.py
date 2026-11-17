"""Pre-registered: the frozen version scored only on competition-seasons released
after it was frozen (docs/blind_test.md). Streams from StatsBomb Open Data.

    python scripts/blind_test.py
    python scripts/blind_test.py --rehearse 37_4     # plumbing check on a season already seen; not a result
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.grid import TACTICAL  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.data.statsbomb import StatsBomb  # noqa: E402
from pitchgraph.prematch import blind, setpieces  # noqa: E402
from pitchgraph.prematch.audit import FEATURES, season_table  # noqa: E402
from pitchgraph.prematch.pooled import asof_arrays, pooled_skill, premise_test  # noqa: E402
from pitchgraph.prematch.replay import CALLS, SP_CALLS  # noqa: E402
from pitchgraph.prematch.result import FEATS, evaluate, result_calls, result_table  # noqa: E402
from pitchgraph.prematch.strategy import GAME_RULES, GAME_THRESHOLD  # noqa: E402


def version() -> str:
    try:
        return subprocess.run(["git", "describe", "--tags", "--always"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip()
    except OSError:
        return "unknown"


def signal(found: bool):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"found={'true' if found else 'false'}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rehearse", nargs="*", default=[], help="seen keys to treat as new (plumbing check only)")
    args = ap.parse_args()
    sb = StatsBomb(memory_items=0)
    live = sb.competitions()
    names = {f"{c['competition_id']}_{c['season_id']}": f"{c['competition_name']} {c['season_name']}" for c in live}
    new = sorted(args.rehearse) if args.rehearse else blind.new_keys(live, blind.frozen_keys())
    res = {"version": version(), "rehearsal": bool(args.rehearse), "new": {k: names[k] for k in new}, "used": [], "skipped": []}
    if args.rehearse:
        print("REHEARSAL on seasons already seen: checks that the script runs, says nothing about unseen data")
    print(f"version {res['version']}; {len(live)} competition-seasons live, {len(new)} "
          f"{'rehearsed' if args.rehearse else 'released since the freeze'}")

    feats = list(FEATURES) + list(setpieces.FEATURES)
    parts, seasons = [], []
    for key in new:
        cid, sid = (int(x) for x in key.split("_"))
        if not blind.usable(sb.matches(cid, sid)):
            res["skipped"].append(names[key])
            print(f"{names[key]}: fewer than {blind.MIN_TEAMS} teams with {blind.MIN_MATCHES} matches, skipped")
            continue
        lake = Lake.stream([key])
        matches = lake.matches()
        dates = dict(zip(matches["match_id"].to_list(), matches["match_date"].to_list()))
        ev = lake.events().collect().lazy()       # same shape the pooled scripts pass
        store = CountStore.from_events(ev, TACTICAL)
        units = season_table(store)
        rtable = result_table(ev, matches)
        if units.height == 0 or rtable.height == 0:
            res["skipped"].append(names[key])
            continue
        table = units.join(setpieces.setpiece_table(ev).drop("opp_id"), on=["match_id", "team_id"],
                           how="inner").sort("match_id", "team_id")
        parts.append(asof_arrays(table, dates, feats))
        seasons.append(result_calls(rtable, dates))
        res["used"].append(names[key])
        print(f"{names[key]}: {int(parts[-1]['scored'].sum())} scored team-matches", flush=True)

    if not parts:
        res["verdict"] = {"units": 0, "judged": False, "reading": "no usable unseen data yet"}
        print(res["verdict"]["reading"])
        Path("blind_test.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        signal(False)
        sys.exit(0)

    threat = pooled_skill([s["arrays"] for s in seasons], FEATS.index("xg"))
    result = evaluate(seasons)
    instructions = blind.pooled_premises(parts, feats, GAME_RULES, GAME_THRESHOLD)
    res.update(threat=threat, result=result, instructions=instructions,
               calls={f: pooled_skill(parts, feats.index(f)) for f, _, _ in list(CALLS) + list(SP_CALLS)},
               rules=premise_test(parts, feats, GAME_RULES, GAME_THRESHOLD, reference="usual"),
               verdict=blind.verdict(threat, result, instructions))

    print(f"\nthreat call: n {threat['n']}, skill {threat['skill']:+.3f} "
          f"({threat['skill_ci'][0]:+.3f}..{threat['skill_ci'][1]:+.3f})")
    m = result["models"]["xg"]
    print(f"result call: {result['n']} matches, RPS {m['rps']:.4f}, gain over base rates {m['gain_over_base']:+.4f} "
          f"({m['gain_ci'][0]:+.4f}..{m['gain_ci'][1]:+.4f}), top pick right {m['top_pick_right']:.0%}")
    if instructions["issued"]:
        print(f"instructions: {instructions['issued']} issued, situation occurred {instructions['occurred_share']:.0%} "
              f"({instructions['ci'][0]:.0%}..{instructions['ci'][1]:.0%})")
    print("\ncalls (reported; judged only with 1,000 team-matches):")
    for f, r in res["calls"].items():
        if r.get("n"):
            print(f"  {f:34s} n {r['n']:5d}  skill {r['skill']:+.3f} ({r['skill_ci'][0]:+.3f}..{r['skill_ci'][1]:+.3f})")
    print("\nrules (reported; judged only with 100 fires):")
    for name, o in res["rules"].items():
        if o["fires"]:
            print(f"  {name:22s} fires {o['fires']:4d}  occurred {o['held_share']:.0%} ({o['ci'][0]:.0%}..{o['ci'][1]:.0%})")
    print(f"\n-> {res['verdict']['reading']}")
    Path("blind_test.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    signal(not args.rehearse)
