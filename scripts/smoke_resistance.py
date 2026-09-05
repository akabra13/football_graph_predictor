import sys
sys.path.insert(0, "src")
import time
import numpy as np
from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots
from pitchgraph.model.resistance import ResistanceGraph

sb = StatsBomb()
snaps = build_snapshots(sb, 3869685, {"Pass", "Carry"})
print("snapshots:", len(snaps))

s = [x for x in snaps if x.ball[0] > 70][5]
rg = ResistanceGraph(s)
cost, path, prob = rg.best_route()
print("%s attacking, ball (%.0f,%.0f), %d defenders visible"
      % (s.attacking_team, s.ball[0], s.ball[1], s.n_defenders))
print("  corridor observability %.2f | P(goal via best route) %.5f"
      % (rg.corridor_observability(), prob))
print("  route:", rg.route_points(path).round(0).tolist())

t0 = time.time()
rows = []
for x in snaps[::5]:
    r = ResistanceGraph(x)
    c, p_, pr = r.best_route()
    if np.isfinite(c) and r.corridor_observability() > 0.6:
        rows.append((x.ball[0], pr, x.n_defenders, len(p_)))
rows = np.array(rows)
el = time.time() - t0
print("\n%d usable snapshots (corridor obs > 0.6), %.0f ms each" % (len(rows), 1000 * el / len(rows)))
print("P(goal) p50 %.5f  p90 %.5f  p99 %.5f" % tuple(np.percentile(rows[:, 1], [50, 90, 99])))
print("route length (hops incl. shot): mean %.1f" % rows[:, 3].mean())
print("  share of routes that are a direct shot: %.0f%%" % (100 * (rows[:, 3] <= 2).mean()))

print("\nmonotonicity checks:")
far = rows[rows[:, 0] < 60][:, 1]
near = rows[rows[:, 0] > 90][:, 1]
print("  ball own half %.5f  vs  attacking third %.5f" % (far.mean(), near.mean()))
# Control for ball position before comparing defender counts.
band = rows[(rows[:, 0] > 80) & (rows[:, 0] < 100)]
lo = band[band[:, 2] <= 8][:, 1]
hi = band[band[:, 2] >= 11][:, 1]
print("  within x=80-100 band: <=8 defenders %.5f  vs  >=11 defenders %.5f"
      % (lo.mean(), hi.mean()))
print("  (n=%d vs %d)" % (len(lo), len(hi)))
