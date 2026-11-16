"""Starting line-ups: who starts, who is missing, and how alike two XIs are."""
from __future__ import annotations

import polars as pl

REGULAR_SHARE = 0.6     # started this share of the team's earlier matches
REGULAR_MIN = 5         # ... and at least this many of them
POWER = 4


def starters(lineups: pl.DataFrame) -> dict:
    """{(match_id, team_id): frozenset of player ids in the starting XI}.

    The lake's `positions` column is each player's list of spells; a starter
    has a spell whose start_reason is "Starting XI".
    """
    start = lineups.filter(pl.col("positions").str.contains("Starting XI"))
    out = {}
    for (mid, tid), g in start.group_by(["match_id", "team_id"]):
        out[(int(mid), int(tid))] = frozenset(int(p) for p in g["player_id"].to_list())
    return out


def overlap_weight(a: frozenset | None, b: frozenset | None, power: int = POWER) -> float:
    """(shared starters / 11) ** power; 1.0 when either line-up is unknown."""
    if not a or not b:
        return 1.0
    return (len(a & b) / 11.0) ** power


def missing_regulars(xi: dict, team_id: int, match_id: int, prior: set, names: dict) -> list[dict]:
    """Players who started most of the team's earlier matches but do not start this one."""
    today = xi.get((match_id, team_id))
    earlier = [s for (m, t), s in xi.items() if t == team_id and m in prior]
    if not today or len(earlier) < REGULAR_MIN:
        return []
    counts: dict = {}
    for s in earlier:
        for p in s:
            counts[p] = counts.get(p, 0) + 1
    out = [{"player_id": p, "name": names.get(p) or str(p), "started": c, "of": len(earlier)}
           for p, c in counts.items()
           if c >= REGULAR_MIN and c / len(earlier) >= REGULAR_SHARE and p not in today]
    return sorted(out, key=lambda r: -r["started"])
