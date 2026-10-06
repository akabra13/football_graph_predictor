"""One interface over the data, wherever it lives.

    Lake.open()                     the Parquet lake under PITCHGRAPH_DATA (Drive)
    Lake.stream(["2_27"], 50)       a sample streamed into memory, never written

Analysis code only ever sees a `Lake`, so the same code runs on the full dataset
in Colab and on a small in-memory sample on a laptop that stores no data.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import polars as pl

from pitchgraph.config import lake_dir
from pitchgraph.data import ingest
from pitchgraph.data.statsbomb import StatsBomb

TABLES = ingest.TABLES


class Lake:
    def __init__(self, tables: dict[str, pl.LazyFrame]):
        self._t = tables

    # -- construction -------------------------------------------------------
    @classmethod
    def open(cls, root: Path | None = None) -> "Lake":
        root = root or lake_dir()
        tables = {}
        for t in TABLES:
            if list((root / t).glob("*.parquet")):
                tables[t] = pl.scan_parquet(root / t / "*.parquet")
        if "events" not in tables:
            raise FileNotFoundError(f"no events in {root}; run the ingest first")
        return cls(tables)

    @classmethod
    def stream(cls, seasons: list[str], max_matches: int | None = None,
               with_frames: bool = False, workers: int = 8,
               keep_payload: bool = False) -> "Lake":
        """Stream competition-seasons (keys like "2_27") into memory only.

        The raw `extra` JSON payload is dropped unless `keep_payload`, since it
        is most of the memory and few analyses need it.
        """
        sb = StatsBomb(memory_items=0)
        comps = {f"{c['competition_id']}_{c['season_id']}": c for c in sb.competitions()}
        jobs = []
        for key in seasons:
            comp = comps[key]
            ms = sb.matches(comp["competition_id"], comp["season_id"])
            ms = sorted(ms, key=lambda m: (m.get("match_date") or "", m["match_id"]))
            jobs += [(m, comp) for m in (ms[:max_matches] if max_matches else ms)]
        parts: dict[str, list] = {t: [] for t in TABLES}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for res in pool.map(lambda j: ingest.ingest_match(j[0], j[1], with_frames), jobs):
                if not keep_payload:
                    res["events"] = res["events"].drop("extra")
                for t, df in res.items():
                    parts[t].append(df)
        return cls({t: pl.concat(v, how="diagonal_relaxed").lazy()
                    for t, v in parts.items() if v})

    @classmethod
    def from_frames(cls, **tables: pl.DataFrame) -> "Lake":
        """Build from DataFrames directly (tests)."""
        return cls({k: v.lazy() for k, v in tables.items()})

    # -- access ---------------------------------------------------------------
    def scan(self, table: str) -> pl.LazyFrame:
        if table not in self._t:
            raise KeyError(f"table {table!r} not available in this lake")
        return self._t[table]

    def has(self, table: str) -> bool:
        return table in self._t

    def events(self) -> pl.LazyFrame:
        """Events joined with match context (competition, season, gender, date)."""
        m = self.scan("matches").select(
            "match_id", "competition_id", "season_id", "competition", "season",
            "gender", "match_date", "home_team_id", "away_team_id")
        return self.scan("events").join(m, on="match_id", how="left")

    def matches(self) -> pl.DataFrame:
        return self.scan("matches").collect()
