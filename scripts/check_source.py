"""Which StatsBomb Open Data competition-seasons are new or updated since we
last ingested them?

Compares the live competitions.json (`match_updated`, `match_updated_360`)
against `lake/source_state.json` (written after each successful ingest) and
the manifest. Prints the keys to (re)ingest, space-separated; with
--write-state, records the current timestamps instead.

    python scripts/check_source.py                # -> "43_106 72_107" or ""
    python scripts/check_source.py --write-state  # after a successful ingest
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.data.statsbomb import StatsBomb  # noqa: E402


def stamp(c: dict) -> str:
    return f"{c.get('match_updated')}|{c.get('match_updated_360')}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write-state", action="store_true")
    args = ap.parse_args()
    lake = Path(os.environ["PITCHGRAPH_DATA"]) / "lake"
    comps = StatsBomb(memory_items=0).competitions()
    current = {f"{c['competition_id']}_{c['season_id']}": stamp(c) for c in comps}
    state_f = lake / "source_state.json"
    if args.write_state:
        lake.mkdir(parents=True, exist_ok=True)
        state_f.write_text(json.dumps(current, indent=1), encoding="utf-8")
        print(f"recorded {len(current)} competition-seasons")
        sys.exit(0)
    state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else None
    mf = lake / "manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    if state is None:
        # first run: anything the manifest has never completed is new; nothing counts as updated
        todo = [k for k in current if not manifest.get(k, {}).get("done")]
    else:
        todo = [k for k, s in current.items() if state.get(k) != s or not manifest.get(k, {}).get("done")]
    print(" ".join(sorted(todo)))
