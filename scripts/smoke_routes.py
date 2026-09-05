import sys
sys.path.insert(0, "src")
import time
import numpy as np
from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots
from pitchgraph.model.routes import RouteSolver

sb = StatsBomb()
snaps = build_snapshots(sb, 3869685, {"Pass", "Carry"})

for hops in (1, 2, 3, 4):
    t0 = time.time()
    rows = []
    for x in snaps[::4]:
        rs = RouteSolver(x)
        r = rs.best_route(max_hops=hops)
        if r.threat > 0 and r.observability > 0.6:
            rows.append((x.ball[0], r.threat, x.n_defenders, r.hops))
    a = np.array(rows)
    el = (time.time() - t0) / max(len(a), 1)
    band = a[(a[:, 0] > 80) & (a[:, 0] < 100)]
    lo = band[band[:, 2] <= 8][:, 1]
    hi = band[band[:, 2] >= 11][:, 1]
    print("max_hops=%d  n=%d  %.1f ms/snap" % (hops, len(a), 1000 * el))
    print("   P(goal)  p50 %.4f  p90 %.4f  p99 %.4f  max %.4f"
          % (*np.percentile(a[:, 1], [50, 90, 99]), a[:, 1].max()))
    print("   own half %.4f vs attacking third %.4f"
          % (a[a[:, 0] < 60][:, 1].mean(), a[a[:, 0] > 90][:, 1].mean()))
    print("   x80-100 band: <=8 def %.4f  vs  >=11 def %.4f   (n=%d/%d)"
          % (lo.mean(), hi.mean(), len(lo), len(hi)))
