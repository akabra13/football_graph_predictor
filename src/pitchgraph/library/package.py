"""Package the Library app: as a folder beside the JSON, or as one report file.

The same app renders both. A folder (index.html + app.js + app.css next to
index.json and seasons/) is the full Library. A standalone report inlines the
CSS, the JS and one season's JSON into a single HTML file that opens on one
team or matchup, so it can be shared or opened straight from Drive.
"""

from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

APP = Path(__file__).parent / "app"
FILES = ("index.html", "app.js", "app.css")


def copy_app(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copyfile(APP / f, out / f)


def _inline_json(obj) -> str:
    # "</" must not appear inside a <script> element.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str).replace("</", "<\\/")


def standalone_html(season: dict, start: str) -> str:
    html = (APP / "index.html").read_text(encoding="utf-8")
    css = (APP / "app.css").read_text(encoding="utf-8")
    js = (APP / "app.js").read_text(encoding="utf-8")
    team = season["teams"].get(start.split("-")[2]) if start.startswith("#team-") else None
    title = f"{team['name']} Scouting Report" if team else "PitchGraph Report"
    html = html.replace("<title>PitchGraph Library</title>", f"<title>{escape(title)}</title>")
    html = html.replace('<link rel="stylesheet" href="app.css">', f"<style>{css}</style>")
    data = f"<script>window.PG_DATA={_inline_json(season)};window.PG_START={json.dumps(start)};</script>"
    return html.replace('<script src="app.js"></script>', f"{data}<script>{js}</script>")
