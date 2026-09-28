"""Stream StatsBomb Open Data into a Parquet lake under the configured data root.

Raw JSON is never saved anywhere: each match is downloaded into memory,
flattened into compact tables, and discarded. Output is one Parquet file per
competition-season per table, which keeps the file count low (Google Drive is
slow with thousands of small files) and makes the ingest resumable at
competition-season granularity via `manifest.json`.

Tables (all keyed by match_id):
  matches  one row per match: teams, score, date, stage, 360 availability
  events   one row per event: core columns plus `extra`, the event's
           type-specific payload as JSON, so no information is lost
  frames   one row per player per 360 freeze-frame
  areas    one row per 360 freeze-frame: the camera's visible_area polygon
  lineups  one row per player per match

Coordinates are stored exactly as StatsBomb provides them: in the frame of the
EVENT team, which always attacks toward x=120. Normalising to the possession
team happens downstream (`data/frames.py`), because the flip depends on the
analysis being done.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import polars as pl

from pitchgraph.config import lake_dir
from pitchgraph.data.statsbomb import StatsBomb

TABLES = ("matches", "events", "frames", "areas", "lineups")

# Top-level event keys that become columns; everything else goes to `extra`.
CORE_KEYS = {
    "id", "index", "period", "timestamp", "minute", "second", "type",
    "possession", "possession_team", "play_pattern", "team", "player",
    "position", "location", "duration", "under_pressure", "counterpress",
    "related_events", "tactics", "off_camera", "out",
}

_local = threading.local()


def _client() -> StatsBomb:
    """One loader per thread: requests sessions are not guaranteed thread-safe."""
    if not hasattr(_local, "sb"):
        _local.sb = StatsBomb(memory_items=0)
    return _local.sb


def _name(d, key="name"):
    return d.get(key) if isinstance(d, dict) else None


def _period_seconds(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _typed_fields(ev: dict) -> dict:
    """Pull the commonly-queried fields out of the type-specific payload."""
    out = {"end_x": None, "end_y": None, "outcome": None, "sub_type": None,
           "recipient_id": None, "xg": None, "body_part": None, "height": None}
    for key in ("pass", "carry", "shot", "dribble", "duel", "interception",
                "goalkeeper", "clearance", "ball_receipt", "50_50"):
        p = ev.get(key)
        if not isinstance(p, dict):
            continue
        end = p.get("end_location")
        if end:
            out["end_x"], out["end_y"] = float(end[0]), float(end[1])
        out["outcome"] = out["outcome"] or _name(p.get("outcome"))
        out["sub_type"] = out["sub_type"] or _name(p.get("type"))
        out["body_part"] = out["body_part"] or _name(p.get("body_part"))
        out["height"] = out["height"] or _name(p.get("height"))
        if key == "pass" and p.get("recipient"):
            out["recipient_id"] = p["recipient"]["id"]
        if key == "shot":
            out["xg"] = p.get("statsbomb_xg")
    return out


def flatten_events(events: list[dict], match_id: int, frame_ids: set) -> pl.DataFrame:
    rows = []
    for ev in events:
        loc = ev.get("location") or [None, None]
        extra = {k: v for k, v in ev.items() if k not in CORE_KEYS}
        rows.append({
            "match_id": match_id,
            "event_id": ev["id"],
            "idx": ev.get("index"),
            "period": ev.get("period"),
            "period_seconds": _period_seconds(ev["timestamp"]),
            "minute": ev.get("minute"),
            "second": ev.get("second"),
            "type": _name(ev.get("type")),
            "team_id": (ev.get("team") or {}).get("id"),
            "team": _name(ev.get("team")),
            "player_id": (ev.get("player") or {}).get("id"),
            "player": _name(ev.get("player")),
            "position": _name(ev.get("position")),
            "possession": ev.get("possession"),
            "possession_team_id": (ev.get("possession_team") or {}).get("id"),
            "play_pattern": _name(ev.get("play_pattern")),
            "x": float(loc[0]) if loc[0] is not None else None,
            "y": float(loc[1]) if len(loc) > 1 and loc[1] is not None else None,
            **_typed_fields(ev),
            "duration": ev.get("duration"),
            "under_pressure": bool(ev.get("under_pressure", False)),
            "counterpress": bool(ev.get("counterpress", False)),
            "has_360": ev["id"] in frame_ids,
            "related": json.dumps(ev.get("related_events", [])),
            "extra": json.dumps(extra, ensure_ascii=False),
        })
    return pl.DataFrame(rows, infer_schema_length=None)


def flatten_frames(frames: list[dict], match_id: int):
    players, areas = [], []
    for fr in frames:
        eid = fr["event_uuid"]
        areas.append({"match_id": match_id, "event_id": eid,
                      "visible_area": json.dumps(fr.get("visible_area", []))})
        for i, p in enumerate(fr.get("freeze_frame", [])):
            players.append({
                "match_id": match_id, "event_id": eid, "n": i,
                "teammate": bool(p["teammate"]), "actor": bool(p.get("actor", False)),
                "keeper": bool(p.get("keeper", False)),
                "x": float(p["location"][0]), "y": float(p["location"][1]),
            })
    return pl.DataFrame(players), pl.DataFrame(areas)


def flatten_lineups(lineups: list[dict], match_id: int) -> pl.DataFrame:
    rows = []
    for team in lineups:
        for p in team.get("lineup", []):
            rows.append({
                "match_id": match_id, "team_id": team["team_id"],
                "team": team["team_name"], "player_id": p["player_id"],
                "player": p["player_name"], "nickname": p.get("player_nickname"),
                "jersey": p.get("jersey_number"),
                "country": _name(p.get("country")),
                "positions": json.dumps(p.get("positions", []), ensure_ascii=False),
            })
    return pl.DataFrame(rows)


def match_row(m: dict, comp: dict) -> dict:
    return {
        "match_id": m["match_id"],
        "competition_id": comp["competition_id"],
        "season_id": comp["season_id"],
        "competition": comp["competition_name"],
        "season": comp["season_name"],
        "gender": comp.get("competition_gender"),
        "match_date": m.get("match_date"),
        "kick_off": m.get("kick_off"),
        "stage": _name(m.get("competition_stage")),
        "home_team_id": m["home_team"]["home_team_id"],
        "home_team": m["home_team"]["home_team_name"],
        "away_team_id": m["away_team"]["away_team_id"],
        "away_team": m["away_team"]["away_team_name"],
        "home_score": m.get("home_score"),
        "away_score": m.get("away_score"),
        "has_360": m.get("match_status_360") == "available",
    }


def ingest_match(m: dict, comp: dict) -> dict[str, pl.DataFrame]:
    """Download one match into memory and flatten it. Nothing touches disk."""
    sb = _client()
    mid = m["match_id"]
    frames = sb.frames(mid) if m.get("match_status_360") == "available" else []
    ids = {f["event_uuid"] for f in frames}
    out = {
        "matches": pl.DataFrame([match_row(m, comp)]),
        "events": flatten_events(sb.events(mid), mid, ids),
        "lineups": flatten_lineups(sb.lineups(mid), mid),
    }
    if frames:
        out["frames"], out["areas"] = flatten_frames(frames, mid)
    return out


def _season_key(comp: dict) -> str:
    return f"{comp['competition_id']}_{comp['season_id']}"


def _write_atomic(df: pl.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp, compression="zstd")
    os.replace(tmp, path)


def _load_manifest(lake: Path) -> dict:
    f = lake / "manifest.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _save_manifest(lake: Path, manifest: dict):
    f = lake / "manifest.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def ingest_season(comp: dict, lake: Path, workers: int = 8, log=print) -> dict:
    """Ingest one competition-season and write its five tables."""
    matches = StatsBomb(memory_items=0).matches(comp["competition_id"], comp["season_id"])
    parts: dict[str, list] = {t: [] for t in TABLES}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, res in enumerate(pool.map(lambda m: ingest_match(m, comp), matches), 1):
            for t, df in res.items():
                parts[t].append(df)
            if done % 50 == 0:
                log(f"    {done}/{len(matches)} matches")

    key = _season_key(comp)
    stats = {"competition": comp["competition_name"], "season": comp["season_name"],
             "matches": len(matches), "seconds": round(time.time() - t0, 1)}
    for t in TABLES:
        if parts[t]:
            df = pl.concat(parts[t], how="diagonal_relaxed")
            _write_atomic(df, lake / t / f"{key}.parquet")
            stats[t] = df.height
    return stats


def ingest_all(lake: Path | None = None, only: list[str] | None = None,
               workers: int = 8, log=print) -> dict:
    """Ingest every competition-season not already in the manifest.

    `only` restricts to competition-season keys like "2_27" (Premier League
    2015/16). Safe to re-run: completed seasons are skipped.
    """
    lake = lake or lake_dir()
    lake.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(lake)
    comps = StatsBomb(memory_items=0).competitions()
    _write_atomic(pl.DataFrame(comps, infer_schema_length=None)
                  .select(["competition_id", "season_id", "competition_name",
                           "season_name", "competition_gender",
                           "competition_international", "match_available_360"]),
                  lake / "competitions.parquet")
    for comp in comps:
        key = _season_key(comp)
        if only and key not in only:
            continue
        if manifest.get(key, {}).get("done"):
            continue
        log(f"{comp['competition_name']} {comp['season_name']} ({key})")
        stats = ingest_season(comp, lake, workers=workers, log=log)
        stats["done"] = True
        manifest[key] = stats
        _save_manifest(lake, manifest)
        log(f"    -> {stats}")
    return manifest
