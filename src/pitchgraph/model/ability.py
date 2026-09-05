"""Attacking ability profiles: what a team is equipped to do.

These describe the team IN possession, and are built from that team's own
actions. The vulnerability features in `vulnerability.py` describe the team OUT
of possession, built from the defending shape. Keeping the two sides on separate
data is what makes the interaction test in
`scripts/validate_interaction.py` meaningful rather than circular.

Note on the plan's ability/opportunity confound: a raw count of through-balls
measures a team's passer as much as its runners. The densest and most direct
signal available is `behind_rate` - how often the ball is actually played beyond
the last defensive line - which uses the 360 back line rather than the sparse
`through_ball` flag (about 5 per match, too few to profile a team on).

StatsBomb's `through_ball` and `switch` flags are kept as secondary, sparser
measures.
"""

from __future__ import annotations

import numpy as np

from .vulnerability import _back_line

PROFILE_NAMES = [
    "behind_rate",     # passes played beyond the last defensive line
    "directness",      # mean forward progress per pass (yards)
    "switch_rate",     # cross-field switches per 100 passes
    "cross_rate",      # crosses per 100 passes
    "long_rate",       # passes over 30 yards per 100 passes
    "offside_rate",    # pass-offsides per 100 passes: evidence of runs in behind
]


def team_profile(snapshots, events_by_id: dict, team: str) -> np.ndarray:
    """Ability profile for `team` from its own attacking snapshots.

    `snapshots` should already be restricted to matches you want included; this
    function filters to those where `team` was the one attacking.
    """
    behind = n_pass = 0
    progress = []
    switches = crosses = longs = offsides = 0

    for s in snapshots:
        if s.attacking_team != team or s.pass_end is None:
            continue
        ev = events_by_id.get(s.event_id)
        if ev is None:
            continue
        p = ev.get("pass", {})
        n_pass += 1

        # Was the ball played beyond the last line of outfield defenders?
        back = _back_line(s.defenders, s.defender_is_keeper)
        if len(back):
            if s.pass_end[0] > back[:, 0].max():
                behind += 1
        progress.append(float(s.pass_end[0] - s.ball[0]))

        switches += bool(p.get("switch"))
        crosses += bool(p.get("cross"))
        longs += float(p.get("length", 0.0)) > 30.0
        offsides += p.get("outcome", {}).get("name") == "Pass Offside"

    if n_pass < 50:
        return np.full(len(PROFILE_NAMES), np.nan)

    return np.array([
        100.0 * behind / n_pass,
        float(np.mean(progress)),
        100.0 * switches / n_pass,
        100.0 * crosses / n_pass,
        100.0 * longs / n_pass,
        100.0 * offsides / n_pass,
    ])


def match_stats(snapshots, events_by_id: dict, team: str) -> np.ndarray:
    """Sufficient statistics for `team` from one match, as raw counts.

    Kept separate from the rate calculation so that leave-one-match-out profiles
    are a subtraction rather than a full recomputation. The naive version was
    O(teams x matches x all snapshots) and did not finish on a full tournament.
    """
    behind = n_pass = switches = crosses = longs = offsides = 0
    progress = 0.0
    for s in snapshots:
        if s.attacking_team != team or s.pass_end is None:
            continue
        ev = events_by_id.get(s.event_id)
        if ev is None:
            continue
        p = ev.get("pass", {})
        n_pass += 1
        back = _back_line(s.defenders, s.defender_is_keeper)
        if len(back) and s.pass_end[0] > back[:, 0].max():
            behind += 1
        progress += float(s.pass_end[0] - s.ball[0])
        switches += bool(p.get("switch"))
        crosses += bool(p.get("cross"))
        longs += float(p.get("length", 0.0)) > 30.0
        offsides += p.get("outcome", {}).get("name") == "Pass Offside"
    return np.array([n_pass, behind, progress, switches, crosses, longs, offsides],
                    dtype=float)


def stats_to_profile(st: np.ndarray, min_passes: int = 50) -> np.ndarray:
    """Convert summed sufficient statistics into rates."""
    n = st[0]
    if n < min_passes:
        return np.full(len(PROFILE_NAMES), np.nan)
    return np.array([
        100.0 * st[1] / n,   # behind_rate
        st[2] / n,           # directness
        100.0 * st[3] / n,   # switch_rate
        100.0 * st[4] / n,   # cross_rate
        100.0 * st[5] / n,   # long_rate
        100.0 * st[6] / n,   # offside_rate
    ])


def profiles_leave_one_out(by_match: dict, events_by_id: dict, teams) -> dict:
    """{(team, held_out_match): profile} computed without the held-out match.

    Estimating ability on the same match being tested would leak that match's
    outcomes into the predictor, which is the circularity the plan warns about.
    """
    per = {(t, m): match_stats(snaps, events_by_id, t)
           for m, snaps in by_match.items() for t in teams}
    totals = {t: sum(per[(t, m)] for m in by_match) for t in teams}
    return {(t, m): stats_to_profile(totals[t] - per[(t, m)])
            for t in teams for m in by_match}
