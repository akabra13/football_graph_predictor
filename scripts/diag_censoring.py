"""Censoring check from the plan: is threat an artefact of what the camera saw?"""
import sys
sys.path.insert(0, "src")
import numpy as np
from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots
from pitchgraph.model.routes import RouteSolver
from pitchgraph.model.availability import AvailabilitySolver

sb = StatsBomb()
rows = []
for mid in [m["match_id"] for m in sb.matches(43, 106)][:6]:
    for x in build_snapshots(sb, mid, {"Pass", "Carry"}):
        av = AvailabilitySolver(x)
        b = av.best(2)
        if b is None:
            continue
        rs = RouteSolver(x)
        r = rs.best_route(1)
        if r.observability < 0.6:
            continue
        rows.append((x.ball[0], r.threat, b.threat, x.n_defenders,
                     av.n_options, len(x.attackers) + x.n_defenders))
a = np.array(rows)
print("n = %d snapshots across 6 matches\n" % len(a))

def corr(i, j):
    return np.corrcoef(a[:, i], a[:, j])[0, 1]

print("correlations with AVAILABLE threat:")
print("   visible team-mates (options) : %+.3f   <-- the censoring artefact" % corr(4, 2))
print("   visible defenders            : %+.3f" % corr(3, 2))
print("   total players visible        : %+.3f" % corr(5, 2))
print("   ball x                       : %+.3f" % corr(0, 2))
print()
print("correlations with STRUCTURAL threat:")
print("   visible team-mates           : %+.3f" % corr(4, 1))
print("   visible defenders            : %+.3f" % corr(3, 1))
print()
print("available threat by number of visible team-mates:")
for n in range(2, 11):
    m = a[:, 4] == n
    if m.sum() > 25:
        print("   %2d options  n=%5d  mean threat %.4f" % (n, m.sum(), a[m, 2].mean()))
print()
print("defender effect AFTER conditioning on options (x=80-100 band):")
band = a[(a[:, 0] > 80) & (a[:, 0] < 100)]
for n in (5, 6, 7, 8):
    s = band[band[:, 4] == n]
    if len(s) < 40:
        continue
    lo = s[s[:, 3] <= 8][:, 2]
    hi = s[s[:, 3] >= 10][:, 2]
    if len(lo) > 8 and len(hi) > 8:
        print("   %d options: <=8 def %.4f (n=%d) vs >=10 def %.4f (n=%d)"
              % (n, lo.mean(), len(lo), hi.mean(), len(hi)))
