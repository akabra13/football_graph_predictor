"""Set-piece table: counts come from the right events and empty ratios are skipped."""
import math
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.prematch.setpieces import FEATURES, setpiece_table  # noqa: E402


def _ev(rows):
    base = dict(match_id=1, period=1, sub_type=None, play_pattern="Regular Play", xg=None, x=50.0)
    return pl.DataFrame([{**base, **r} for r in rows], infer_schema_length=None)


def test_counts_and_ratios():
    ev = _ev([
        dict(team_id=1, type="Pass", sub_type="Corner", play_pattern="From Corner", x=120.0),
        dict(team_id=1, type="Pass", sub_type="Corner", play_pattern="From Corner", x=120.0),
        dict(team_id=1, type="Shot", play_pattern="From Corner", xg=0.2, x=110.0),
        dict(team_id=1, type="Shot", play_pattern="Regular Play", xg=0.3, x=105.0),
        dict(team_id=1, type="Pass", sub_type="Free Kick", play_pattern="From Free Kick", x=90.0),
        dict(team_id=1, type="Pass", sub_type="Free Kick", play_pattern="From Free Kick", x=30.0),
        dict(team_id=1, type="Shot", sub_type="Penalty", play_pattern="Other", xg=0.76, x=108.0),
        dict(team_id=1, type="Shot", play_pattern="From Corner", xg=0.5, x=110.0, period=5),
        dict(team_id=2, type="Pass", x=40.0),
    ])
    t = setpiece_table(ev)
    assert t.columns == ["match_id", "team_id", "opp_id", *FEATURES]
    a = t.filter(pl.col("team_id") == 1).row(0, named=True)
    assert a["opp_id"] == 2 and a["corners"] == 2 and a["att_free_kicks"] == 1
    assert a["sp_shots"] == 1 and abs(a["sp_xg"] - 0.2) < 1e-9
    assert abs(a["sp_xg_share"] - 0.4) < 1e-9 and abs(a["shots_per_corner"] - 0.5) < 1e-9
    b = t.filter(pl.col("team_id") == 2).row(0, named=True)
    assert b["corners"] == 0 and math.isnan(b["sp_xg_share"]) and math.isnan(b["shots_per_corner"])
