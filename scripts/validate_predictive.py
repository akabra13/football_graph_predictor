"""Does structurally-defined threat predict what actually happened next?

Note on method: vulnerability is DEFINED geometrically, never from outcomes.
Outcomes are used here only to check the geometric definition, which is the
secondary-check role the plan allows. If threat were fitted to outcomes this
test would be circular and worthless.
"""
import sys
sys.path.insert(0, "src")
import numpy as np
from sklearn.metrics import roc_auc_score

from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots, event_time_seconds
from pitchgraph.model.routes import RouteSolver
from pitchgraph.model.availability import AvailabilitySolver

sb = StatsBomb()
X, y, meta = [], [], []

for mid in [m["match_id"] for m in sb.matches(43, 106)][:10]:
    events = sb.events(mid)
    # Shots by (possession, team) and their times.
    shots = [(e["possession"], e["team"]["id"], event_time_seconds(e),
              e.get("shot", {}).get("statsbomb_xg", 0.0))
             for e in events if e["type"]["name"] == "Shot"]
    ev_by_id = {e["id"]: e for e in events}

    for s in build_snapshots(sb, mid, {"Pass", "Carry"}):
        av = AvailabilitySolver(s)
        b = av.best(2)
        if b is None:
            continue
        rs = RouteSolver(s)
        r = rs.best_route(1)
        if r.observability < 0.6:
            continue
        ev = ev_by_id[s.event_id]
        tid = ev["possession_team"]["id"]
        # Did the attacking team shoot within 10s, in this same possession?
        nxt = [(t, xg) for (p, team, t, xg) in shots
               if p == s.possession and team == tid and 0 <= t - s.t <= 10]
        X.append([b.threat, r.threat, s.ball[0], av.n_options, s.n_defenders])
        y.append(1 if nxt else 0)
        meta.append(max([xg for _, xg in nxt], default=0.0))

X = np.array(X); y = np.array(y); xg = np.array(meta)
print("snapshots: %d   shot within 10s: %.1f%%\n" % (len(y), 100 * y.mean()))

names = ["available threat", "structural threat", "ball x (baseline)",
         "n options", "n defenders"]
print("AUC for predicting a shot in the next 10s:")
for i, nm in enumerate(names):
    print("   %-20s %.3f" % (nm, roc_auc_score(y, X[:, i])))

print("\navailable threat decile -> observed shot rate:")
d = np.quantile(X[:, 0], np.linspace(0, 1, 11))
for k in range(10):
    m = (X[:, 0] >= d[k]) & (X[:, 0] <= d[k + 1])
    if m.sum() > 20:
        print("   decile %2d  threat %.4f  ->  shot rate %.3f  mean xG %.4f"
              % (k + 1, X[m, 0].mean(), y[m].mean(), xg[m].mean()))

# Does it add anything beyond simply knowing where the ball is?
from sklearn.linear_model import LogisticRegression
base = LogisticRegression(max_iter=1000).fit(X[:, [2]], y)
full = LogisticRegression(max_iter=1000).fit(X[:, [2, 0]], y)
print("\nincremental value over ball position alone:")
print("   ball x only            AUC %.3f" % roc_auc_score(y, base.predict_proba(X[:, [2]])[:, 1]))
print("   ball x + avail threat  AUC %.3f" % roc_auc_score(y, full.predict_proba(X[:, [2, 0]])[:, 1]))
