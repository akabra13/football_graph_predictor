"""Validate PitchGraph's chain models and build the Library on Drive.

Needs PITCHGRAPH_DATA pointing at a lake with data already ingested
(scripts/ingest.py). Writes library/validation.json, one JSON file per
competition-season under library/seasons/, the style map in
library/index.json, and the app files -- all resumable: a re-run skips
seasons already built.

    python scripts/build_library.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from pitchgraph.chains import validate  # noqa: E402
from pitchgraph.config import require_data_root  # noqa: E402
from pitchgraph.data.lake import Lake  # noqa: E402
from pitchgraph.library.build import build_all  # noqa: E402
from pitchgraph.library.package import copy_app  # noqa: E402


def season(lake: Lake, key: str):
    cid, sid = (int(x) for x in key.split("_"))
    events = lake.events().filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid))
    ids = lake.matches().filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid))["match_id"]
    lineups = lake.scan("lineups").filter(pl.col("match_id").is_in(ids)).collect()
    return events, lineups


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lake = Lake.open()
    library = require_data_root() / "library"
    library.mkdir(parents=True, exist_ok=True)
    print(f"lake matches: {lake.matches().height} | library: {library}")

    print("\n== validation suite ==")
    results = validate.run_suite(
        [(label, *season(lake, key)) for key, label in validate.COMPLETE_LEAGUES.items()]
    )
    (library / "validation.json").write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps({k: results[k] for k in ("missed", "scope") if k in results}, indent=1))

    print("\n== library build ==")
    index = build_all(lake, library)
    copy_app(library)
    print(len(index["seasons"]), "competition-seasons,",
          sum(len(s["teams"]) for s in index["seasons"].values()), "team pages")
