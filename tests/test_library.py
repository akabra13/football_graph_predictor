"""Packaging the Library app and resolving seasons by name."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.cli import normalise_season  # noqa: E402
from pitchgraph.library.package import FILES, copy_app, standalone_html  # noqa: E402


@pytest.mark.parametrize("given,expected", [
    ("2015/16", "2015/2016"), ("15/16", "2015/2016"), ("2015-2016", "2015/2016"),
    ("2023", "2023"), ("1999/00", "1999/2000"),
])
def test_normalise_season(given, expected):
    assert normalise_season(given) == expected


SEASON = {"key": "2_27", "competition": "Premier League", "season": "2015/2016", "gender": "male",
          "teams": {"217": {"id": 217, "name": "Leicester </script> City", "matches": 38,
                            "small_sample": False}}, "matchups": {}}


def test_standalone_report_inlines_everything_and_escapes_script_breaks():
    html = standalone_html(SEASON, "#team-2_27-217")
    assert "<title>Leicester &lt;/script&gt; City Scouting Report</title>" in html
    assert 'src="app.js"' not in html and 'href="app.css"' not in html
    data = re.search(r"window\.PG_DATA=(.*?);window\.PG_START", html, re.S).group(1)
    assert "</script>" not in data
    assert json.loads(data.replace("<\/", "</"))["teams"]["217"]["matches"] == 38
    assert 'window.PG_START="#team-2_27-217"' in html


def test_copy_app_writes_the_three_app_files(tmp_path):
    copy_app(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(FILES)
