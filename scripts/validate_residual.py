"""Isolate the DEFENSIVE signal by removing positional expectation.

Raw threat is dominated by where the ball is, so it merely re-expresses field
position. The quantity of interest is threat ABOVE what the ball's position
alone would predict: "this defence is unusually open given where the ball is".
This is the baseline requirement from the plan applied to the measure itself.
"""
import sys
sys.path.insert(0, "src")
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict

from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots, event_time_seconds
from pitchgraph.model.routes import RouteSolver
from pitchgraph.model.availability import AvailabilitySolver
from pitchgraph.model.resistance import lane_pressure, reception_pressure

sb = StatsBomb()
rows, y = [], []
for mid in [m["match_id"] for m in sb.matches(43, 106)][:14]:
    events = sb.events(mid)
    shots = [(e["possession"], e["team"]["id"], event_time_seconds(e))
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
        # Direct defensive-structure features, independent of the route model.
        D = s.defenders
        goal_dir = np.array([[120.0, 40.0]])
        lane_to_goal = lane_pressure(s.ball.reshape(1, 2), goal_dir, D)[0]
        ahead = (D[:, 0] > s.ball[0]).sum()          # defenders goal-side of ball
        nearest = np.linalg.norm(D - s.ball, axis=1).min()
        ev = ev_by_id[s.event_id]
        tid = ev["possession_team"]["id"]
        hit = any(p == s.possession and t_ == tid and 0 <= tt - s.t <= 10
                  for (p, t_, tt) in shots)
        rows.append([b.threat, r.threat, s.ball[0], s.ball[1],
                     lane_to_goal, ahead, nearest, av.n_options, s.n_defenders])
        y.append(int(hit))

A = np.array(rows); y = np.array(y)
pos = A[:, 2:4]
print("n=%d  shot rate %.3f\n" % (len(y), y.mean()))

def auc_cv(X):
    m = HistGradientBoostingClassifier(max_iter=200, random_state=0)
    p = cross_val_predict(m, X, y, cv=5, method="predict_proba")[:, 1]
    return roc_auc_score(y, p)

base = auc_cv(pos)
print("AUC, 5-fold cross-validated:")
print("   ball position only                    %.4f  <- baseline to beat" % base)
print("   + available threat                    %.4f" % auc_cv(np.c_[pos, A[:, 0]]))
print("   + structural threat                   %.4f" % auc_cv(np.c_[pos, A[:, 1]]))
print("   + raw defensive features              %.4f" % auc_cv(np.c_[pos, A[:, 4:7]]))
print("   + threat AND defensive features       %.4f" % auc_cv(np.c_[pos, A[:, [0, 1, 4, 5, 6]]]))
print("   everything incl. visibility controls  %.4f" % auc_cv(A))

# Residualise threat against position, then test the residual alone.
reg = HistGradientBoostingRegressor(max_iter=200, random_state=0)
exp_threat = cross_val_predict(reg, pos, A[:, 0], cv=5)
resid = A[:, 0] - exp_threat
print("\nresidual threat (above positional expectation):")
print("   corr(residual, ball x) = %+.3f   (should be ~0 if residualising worked)"
      % np.corrcoef(resid, A[:, 2])[0, 1])
print("   AUC of residual alone                 %.4f" % roc_auc_score(y, resid))
print("   AUC position + residual               %.4f" % auc_cv(np.c_[pos, resid]))
print("\nobserved shot rate by residual quintile (within position strata):")
q = np.quantile(resid, np.linspace(0, 1, 6))
for k in range(5):
    m = (resid >= q[k]) & (resid <= q[k + 1])
    print("   Q%d  residual %+.4f  ->  shot rate %.3f  (n=%d)"
          % (k + 1, resid[m].mean(), y[m].mean(), m.sum()))
