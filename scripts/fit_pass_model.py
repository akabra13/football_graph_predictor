"""Calibrate lane and reception geometry against real pass outcomes.

The resistance graph's edge costs were originally hand-invented constants. That
is exactly the kind of undefendable parameter this project set out to avoid, so
we fit them: every attempted pass with a 360 frame is a labelled trial of
"did the ball survive this lane against this defensive configuration".
"""
import sys
sys.path.insert(0, "src")
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots

sb = StatsBomb()
matches = [m["match_id"] for m in sb.matches(43, 106)][:24]

starts, ends, comp, dfs = [], [], [], []
for mid in matches:
    for s in build_snapshots(sb, mid, {"Pass"}):
        if s.pass_end is None or s.pass_complete is None or len(s.defenders) < 4:
            continue
        starts.append(s.ball); ends.append(s.pass_end)
        comp.append(s.pass_complete); dfs.append(s.defenders)

starts = np.array(starts); ends = np.array(ends); y = np.array(comp).astype(int)
print("labelled passes with 360: %d  (completion rate %.3f)" % (len(y), y.mean()))


def features(starts, ends, dfs, lane_sigma, recv_sigma):
    """Lane pressure and reception pressure under a given geometry."""
    lane, recv = np.zeros(len(starts)), np.zeros(len(starts))
    for i, (a, b, D) in enumerate(zip(starts, ends, dfs)):
        seg = b - a
        L2 = max(seg @ seg, 1e-9)
        t = np.clip(((D - a) @ seg) / L2, 0, 1)
        closest = a + t[:, None] * seg
        perp = np.linalg.norm(D - closest, axis=1)
        lane[i] = np.exp(-0.5 * (perp / lane_sigma) ** 2).sum()
        recv[i] = np.exp(-0.5 * (np.linalg.norm(D - b, axis=1).min() / recv_sigma) ** 2)
    return lane, recv


length = np.linalg.norm(ends - starts, axis=1)
best = None
for ls in [0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5]:
    for rs in [2.0, 2.5, 3.0, 3.5, 4.0]:
        lane, recv = features(starts, ends, dfs, ls, rs)
        X = np.column_stack([lane, recv, length, length ** 2 / 100])
        m = LogisticRegression(max_iter=2000).fit(X, y)
        p = m.predict_proba(X)[:, 1]
        auc = roc_auc_score(y, p)
        if best is None or auc > best[0]:
            best = (auc, ls, rs, m, brier_score_loss(y, p))

auc, ls, rs, model, brier = best
print("\nbest geometry: lane_sigma=%.1f  reception_sigma=%.1f" % (ls, rs))
print("  AUC %.3f | Brier %.4f  (baseline Brier %.4f)"
      % (auc, brier, brier_score_loss(y, np.full(len(y), y.mean()))))
print("  coefs lane=%.4f recv=%.4f len=%.4f len2=%.4f  intercept=%.4f"
      % (*model.coef_[0], model.intercept_[0]))

# Sanity: completion by number of defenders close to the lane.
lane, recv = features(starts, ends, dfs, ls, rs)
print("\nobserved completion by lane pressure:")
for lo, hi in [(0, .25), (.25, .75), (.75, 1.5), (1.5, 3), (3, 99)]:
    m_ = (lane >= lo) & (lane < hi)
    if m_.sum() > 20:
        print("  lane %.2f-%.2f  n=%5d  completion %.3f" % (lo, hi, m_.sum(), y[m_].mean()))
