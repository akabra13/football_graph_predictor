"""Build the Parquet lake from StatsBomb Open Data.

Needs PITCHGRAPH_DATA pointing at the data root (Google Drive in Colab, or a
USB drive). Refuses to run otherwise, so nothing is ever written to the laptop.

    python scripts/ingest.py                 # everything, resumable
    python scripts/ingest.py --only 43_106   # one competition-season
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.config import lake_dir  # noqa: E402
from pitchgraph.data.ingest import ingest_all  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="competition-season keys, e.g. 43_106")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    lake = lake_dir()
    print(f"lake: {lake}")
    manifest = ingest_all(lake, only=args.only, workers=args.workers)
    done = [v for v in manifest.values() if v.get("done")]
    print(f"\n{len(done)} competition-seasons, {sum(v['matches'] for v in done)} matches, "
          f"{sum(v.get('events', 0) for v in done):,} events in the lake")
