"""Assemble an opposition report for one team from a prepared League."""

from __future__ import annotations

import numpy as np

from pitchgraph.analysis.reliability import split_half_agreement
from pitchgraph.analysis.scout import League

HEADLINES = 5


def build(league: League, team: str, meta: dict, n_boot: int = 200) -> dict:
    ids = [t for t, name in league.teams.items() if name == team]
    if not ids:
        raise KeyError(f"{team!r} is not in this competition-season")
    tid = ids[0]
    claims = league.claims(tid, n_boot=n_boot)
    strong = [c for c in claims if c.est.confidence == "High" and np.isfinite(c.est.value)]
    headlines = sorted(strong, key=lambda c: -c.extremeness)[:HEADLINES]
    has_360 = bool(league.ev.filter(league.ev["team_id"] == tid)["has_360"].any())
    return {
        "meta": {**meta, "team": team,
                 "matches": league.matches_of(tid)["match_id"].n_unique(),
                 "teams": len(league.teams),
                 "tier": "events + 360" if has_360 else "events",
                 "agreement": split_half_agreement([c.est for c in claims])},
        "claims": claims,
        "headlines": headlines,
        "details": league.details(tid),
    }
