"""Do the geometric vulnerability features beat a positional baseline?"""
import sys
sys.path.insert(0, "src")
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict, GroupKFold

from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots, event_time_seconds
from pitchgraph.model.vulnerability import FEATURE_NAMES, features

sb = StatsBomb()
F, y, groups, pos = [], [], [], []
for gi, mid in enumerate([m["match_id"] for m in sb.matches(43, 106)][:20]):
    events = sb.events(mid)
    shots = {(e["possession"], e["team"]["id"]): [] for e in events}
    for e in events:
        if e["type"]["name"] == "Shot":
            shots.setdefault((e["possession"], e["team"]["id"]), []).append(
                event_time_seconds(e))
    ev_by_id = {e["id"]: e for e in events}
    for s in build_snapshots(sb, mid, {"Pass", "Carry"}):
        if len(s.defenders) < 5:
            continue
        f = features(s)
        if not np.isfinite(f).all():
            continue
        tid = ev_by_id[s.event_id]["possession_team"]["id"]
        ts = shots.get((s.possession, tid), [])
        F.append(f); pos.append(s.ball)
        y.append(int(any(0 <= t - s.t <= 10 for t in ts)))
        groups.append(gi)

F = np.array(F); y = np.array(y); pos = np.array(pos); groups = np.array(groups)
print("n=%d over %d matches  shot rate %.3f\n" % (len(y), len(set(groups)), y.mean()))

def auc(X):
    """Grouped CV by match, so no match appears in both train and test."""
    m = HistGradientBoostingClassifier(max_iter=250, random_state=0)
    p = cross_val_predict(m, X, y, cv=GroupKFold(n_splits=5), groups=groups,
                          method="predict_proba")[:, 1]
    return roc_auc_score(y, p)

base = auc(pos)
full = auc(np.c_[pos, F])
print("grouped 5-fold CV (split by match):")
print("   ball position only          %.4f" % base)
print("   position + geometry         %.4f   (%+.4f)" % (full, full - base))
print("   geometry only               %.4f" % auc(F))

# Which individual features add most on top of position?
print("\nmarginal AUC gain of each feature over position alone:")
gains = []
for i, n in enumerate(FEATURE_NAMES):
    gains.append((auc(np.c_[pos, F[:, i]]) - base, n))
for g, n in sorted(gains, reverse=True):
    print("   %-20s %+.4f" % (n, g))
