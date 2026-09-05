"""Fetch and cache StatsBomb Open Data.

Two things this module exists to get right:

1. Every read is explicitly UTF-8. The repo's JSON is UTF-8 and Python on Windows
   defaults to cp1252, which raises UnicodeDecodeError on the first accented name.
2. Files are cached to disk. A single match's 360 file is ~9MB; re-downloading
   during iteration is slow enough to change how you work.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Competition/season pairs that carry 360 freeze-frames, verified against
# competitions.json. Everything in this project depends on 360, so these are
# the only seasons that are usable.
SEASONS_WITH_360 = {
    ("FIFA World Cup", "2022"): (43, 106),
    ("UEFA Euro", "2024"): (55, 282),
    ("UEFA Euro", "2020"): (55, 43),
    ("La Liga", "2020/2021"): (11, 90),
    ("Ligue 1", "2022/2023"): (7, 235),
    ("Ligue 1", "2021/2022"): (7, 108),
    ("1. Bundesliga", "2023/2024"): (9, 281),
    ("Major League Soccer", "2023"): (44, 107),
    ("African Cup of Nations", "2023"): (1267, 107),
    ("Women's World Cup", "2023"): (72, 107),
    ("UEFA Women's Euro", "2025"): (53, 315),
    ("UEFA Women's Euro", "2022"): (53, 106),
}

WORLD_CUP_2022 = (43, 106)

DEFAULT_CACHE = Path(__file__).resolve().parents[3] / "data" / "cache"


class StatsBomb:
    """Reader for StatsBomb Open Data with a local disk cache."""

    def __init__(self, cache_dir: Path | str | None = None, timeout: int = 120):
        self.cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._session = requests.Session()

    def _get(self, rel: str) -> Any:
        """Fetch `rel` (e.g. 'events/3869685.json'), caching the raw bytes."""
        dest = self.cache / rel
        if dest.exists():
            return json.loads(dest.read_text(encoding="utf-8"))

        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"{BASE}/{rel}"
        for attempt in range(3):
            try:
                r = self._session.get(url, timeout=self.timeout)
                if r.status_code == 404:
                    raise FileNotFoundError(f"not in open data: {rel}")
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

        # Decode explicitly rather than trusting requests' charset guess.
        text = r.content.decode("utf-8")
        dest.write_text(text, encoding="utf-8")
        return json.loads(text)

    def competitions(self) -> list[dict]:
        return self._get("competitions.json")

    def matches(self, competition_id: int, season_id: int) -> list[dict]:
        return self._get(f"matches/{competition_id}/{season_id}.json")

    def events(self, match_id: int) -> list[dict]:
        return self._get(f"events/{match_id}.json")

    def lineups(self, match_id: int) -> list[dict]:
        return self._get(f"lineups/{match_id}.json")

    def frames(self, match_id: int) -> list[dict]:
        """360 freeze-frames. Returns [] for matches without 360 coverage."""
        try:
            return self._get(f"three-sixty/{match_id}.json")
        except FileNotFoundError:
            return []

    def has_360(self, match_id: int) -> bool:
        return bool(self.frames(match_id))

    def frames_by_event(self, match_id: int) -> dict[str, dict]:
        """Freeze-frames keyed by the event uuid they belong to."""
        return {f["event_uuid"]: f for f in self.frames(match_id)}

    def seasons_with_360(self) -> list[dict]:
        """Competition-seasons flagged as having 360 data, read from the source."""
        return [c for c in self.competitions() if c.get("match_available_360")]
