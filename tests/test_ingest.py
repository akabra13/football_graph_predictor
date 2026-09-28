"""Ingest behaviour on synthetic data: lossless, resumable, writes only to the lake."""
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.data import ingest  # noqa: E402

COMP = {"competition_id": 1, "season_id": 2, "competition_name": "Test League",
        "season_name": "2099", "competition_gender": "male",
        "competition_international": False, "match_available_360": None}


def _match(mid, with_360=False):
    return {"match_id": mid, "match_date": "2099-01-01", "kick_off": "15:00",
            "competition_stage": {"name": "Regular Season"},
            "home_team": {"home_team_id": 10, "home_team_name": "Atlético"},
            "away_team": {"away_team_id": 20, "away_team_name": "Köln"},
            "home_score": 1, "away_score": 0,
            "match_status_360": "available" if with_360 else "unscheduled"}


def _events(mid):
    return [
        {"id": f"{mid}-a", "index": 1, "period": 1, "timestamp": "00:01:02.500",
         "minute": 1, "second": 2, "type": {"name": "Pass"}, "possession": 2,
         "possession_team": {"id": 10}, "play_pattern": {"name": "Regular Play"},
         "team": {"id": 10, "name": "Atlético"},
         "player": {"id": 7, "name": "José Sanmartín"},
         "position": {"name": "Center Back"}, "location": [30.0, 40.0],
         "pass": {"recipient": {"id": 8}, "end_location": [50.0, 30.0],
                  "type": {"name": "Recovery"}, "switch": True}},
        {"id": f"{mid}-b", "index": 2, "period": 1, "timestamp": "00:01:04.000",
         "minute": 1, "second": 4, "type": {"name": "Shot"}, "possession": 2,
         "possession_team": {"id": 10}, "play_pattern": {"name": "Regular Play"},
         "team": {"id": 10, "name": "Atlético"}, "player": {"id": 8, "name": "B"},
         "location": [110.0, 40.0],
         "shot": {"statsbomb_xg": 0.31, "end_location": [120.0, 38.0, 1.0],
                  "outcome": {"name": "Goal"}}},
        {"id": f"{mid}-c", "index": 3, "period": 1, "timestamp": "00:00:00.000",
         "minute": 0, "second": 0, "type": {"name": "Half Start"},
         "team": {"id": 20, "name": "Köln"}},
    ]


class FakeSB:
    calls = []

    def __init__(self, *a, **k):
        pass

    def competitions(self):
        return [COMP]

    def matches(self, cid, sid):
        FakeSB.calls.append(("matches", cid, sid))
        return [_match(100, with_360=True), _match(101)]

    def events(self, mid):
        return _events(mid)

    def lineups(self, mid):
        return [{"team_id": 10, "team_name": "Atlético", "lineup": [
            {"player_id": 7, "player_name": "José Sanmartín", "jersey_number": 4,
             "country": {"name": "Spain"}, "positions": []}]}]

    def frames(self, mid):
        return [{"event_uuid": f"{mid}-a", "visible_area": [0, 0, 120, 0, 120, 80, 0, 0],
                 "freeze_frame": [
                     {"teammate": True, "actor": True, "keeper": False, "location": [30, 40]},
                     {"teammate": False, "actor": False, "keeper": True, "location": [118, 40]}]}]


def _patch(monkeypatch):
    monkeypatch.setattr(ingest, "StatsBomb", FakeSB)
    if hasattr(ingest._local, "sb"):
        del ingest._local.sb
    FakeSB.calls = []


def test_flatten_events_extracts_typed_fields_and_keeps_payload():
    df = ingest.flatten_events(_events(1), 1, {"1-a"})
    assert df.height == 3
    p = df.filter(pl.col("type") == "Pass").row(0, named=True)
    assert (p["end_x"], p["end_y"], p["recipient_id"], p["sub_type"]) == (50.0, 30.0, 8, "Recovery")
    assert p["period_seconds"] == 62.5 and p["has_360"] is True
    assert json.loads(p["extra"])["pass"]["switch"] is True
    s = df.filter(pl.col("type") == "Shot").row(0, named=True)
    assert s["xg"] == 0.31 and s["outcome"] == "Goal" and s["has_360"] is False
    # Events without a location or player must not break the flattening.
    h = df.filter(pl.col("type") == "Half Start").row(0, named=True)
    assert h["x"] is None and h["player_id"] is None


def test_ingest_writes_only_inside_the_lake_and_is_lossless(tmp_path, monkeypatch):
    _patch(monkeypatch)
    lake = tmp_path / "lake"
    ingest.ingest_all(lake=lake, workers=2, log=lambda *_: None)

    written = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert written == {"lake"}

    ev = pl.read_parquet(lake / "events" / "1_2.parquet")
    assert ev.height == 6                              # 3 events x 2 matches
    assert "José Sanmartín" in ev["player"].to_list()   # UTF-8 survives
    fr = pl.read_parquet(lake / "frames" / "1_2.parquet")
    assert fr.height == 2 and set(fr["match_id"]) == {100}
    m = pl.read_parquet(lake / "matches" / "1_2.parquet")
    assert m.filter(pl.col("match_id") == 100)["has_360"].item() is True
    manifest = json.loads((lake / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["1_2"]["done"] and manifest["1_2"]["events"] == 6


def test_ingest_is_resumable(tmp_path, monkeypatch):
    _patch(monkeypatch)
    lake = tmp_path / "lake"
    ingest.ingest_all(lake=lake, workers=1, log=lambda *_: None)
    first = len(FakeSB.calls)
    ingest.ingest_all(lake=lake, workers=1, log=lambda *_: None)
    assert len(FakeSB.calls) == first, "completed seasons must be skipped"
