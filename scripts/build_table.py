"""Build and cache the snapshot-level analysis table.

Rebuilding 64 matches of snapshots takes minutes, so the table is cached to
data/cache/table.npz and every validation script reads it. Caching also means
each experiment runs against exactly the same rows.
"""
import sys
sys.path.insert(0, "src")
import numpy as np

from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots, event_time_seconds
from pitchgraph.model.vulnerability import FEATURE_NAMES, features
from pitchgraph.model.ability import PROFILE_NAMES, profiles_leave_one_out

OUT = "data/cache/table.npz"
COMP, SEASON = 43, 106
SHOT_WINDOW = 10.0


def main():
    sb = StatsBomb()
    match_ids = [m["match_id"] for m in sb.matches(COMP, SEASON)]

    by_match, events_by_id, shot_index = {}, {}, {}
    for i, mid in enumerate(match_ids, 1):
        evs = sb.events(mid)
        for e in evs:
            events_by_id[e["id"]] = e
        shot_index[mid] = [
            (e["possession"], e["team"]["id"], event_time_seconds(e))
            for e in evs if e["type"]["name"] == "Shot"
        ]
        by_match[mid] = build_snapshots(sb, mid, {"Pass", "Carry"})
        if i % 16 == 0:
            print("  built %d/%d matches" % (i, len(match_ids)))

    teams = sorted({s.attacking_team for v in by_match.values() for s in v})
    prof = profiles_leave_one_out(by_match, events_by_id, teams)
    team_idx = {t: i for i, t in enumerate(teams)}

    rows, atk, dfd, mid_col = [], [], [], []
    for mid, snaps in by_match.items():
        shots = shot_index[mid]
        for s in snaps:
            if len(s.defenders) < 5:
                continue
            f = features(s)
            p = prof.get((s.attacking_team, mid))
            if p is None or not np.isfinite(f).all() or not np.isfinite(p).all():
                continue
            tid = events_by_id[s.event_id]["possession_team"]["id"]
            hit = any(pp == s.possession and tt == tid and 0 <= t - s.t <= SHOT_WINDOW
                      for (pp, tt, t) in shots)
            rows.append(np.concatenate([[int(hit)], s.ball, f, p]))
            atk.append(team_idx[s.attacking_team])
            dfd.append(team_idx.get(s.defending_team, -1))
            mid_col.append(mid)

    A = np.array(rows)
    np.savez_compressed(
        OUT,
        y=A[:, 0], ball=A[:, 1:3],
        F=A[:, 3:3 + len(FEATURE_NAMES)],
        P=A[:, 3 + len(FEATURE_NAMES):],
        attacking=np.array(atk), defending=np.array(dfd),
        match=np.array(mid_col), teams=np.array(teams),
        feature_names=np.array(FEATURE_NAMES),
        profile_names=np.array(PROFILE_NAMES),
    )
    print("saved %s: %d rows, %d teams, shot rate %.3f"
          % (OUT, len(A), len(teams), A[:, 0].mean()))


if __name__ == "__main__":
    main()
