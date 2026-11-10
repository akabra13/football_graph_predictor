"""Render post specs (posts/*.json) to PNGs, plus a captions file for review.

    python scripts/build_posts.py --out out/posts            # every spec
    python scripts/build_posts.py --out out/posts 02_seven   # ids starting with a prefix

POST_HANDLE sets the handle in the credit line; PITCHGRAPH_LOGO points at
the StatsBomb logo (the posts workflow downloads it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pitchgraph.figures import render  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--specs", default=str(ROOT / "posts"))
    ap.add_argument("only", nargs="*")
    args = ap.parse_args()

    captions = []
    for f in sorted(Path(args.specs).glob("*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        if args.only and not any(spec["id"].startswith(p) for p in args.only):
            continue
        path = render(spec, args.out)
        captions.append(f"## {spec['id']}\n\n{spec.get('caption', '')}\n")
        print(f"rendered {path}")
    (Path(args.out) / "captions.md").write_text("\n".join(captions), encoding="utf-8")
