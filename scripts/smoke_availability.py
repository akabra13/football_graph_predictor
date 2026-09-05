import sys
sys.path.insert(0, "src")
import numpy as np
from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots
from pitchgraph.model.routes import RouteSolver
from pitchgraph.model.availability import AvailabilitySolver

sb = StatsBomb()
snaps = build_snapshots(sb, 3869685, {"Pass", "Carry"})

rows = []
for x in snaps:
    av = AvailabilitySolver(x)
    b = av.best(max_hops=2)
    if b is None:
        continue
    rs = RouteSolver(x)
    r = rs.best_route(max_hops=1)
    if r.observability < 0.6:
        continue
    rows.append((x.ball[0], r.threat, b.threat, x.n_defenders, av.n_options, b.hops))

a = np.array(rows)
print("snapshots compared: %d\n" % len(a))
print("STRUCTURAL threat (zone grid, depth 1):")
print("   p50 %.4f  p90 %.4f  max %.4f" % (*np.percentile(a[:, 1], [50, 90]), a[:, 1].max()))
print("AVAILABLE threat (real team-mates, depth 2):")
print("   p50 %.4f  p90 %.4f  max %.4f" % (*np.percentile(a[:, 2], [50, 90]), a[:, 2].max()))
print()
print("mean options (visible team-mates): %.1f" % a[:, 4].mean())
print()
print("monotonicity, controlling for ball position (x=80-100 band):")
band = a[(a[:, 0] > 80) & (a[:, 0] < 100)]
for name, col in (("structural", 1), ("available", 2)):
    lo = band[band[:, 3] <= 8][:, col]
    hi = band[band[:, 3] >= 11][:, col]
    print("   %-11s <=8 defenders %.4f  vs  >=11 defenders %.4f   (n=%d/%d)"
          % (name, lo.mean(), hi.mean(), len(lo), len(hi)))
print()
print("by ball third (available threat):")
for lo, hi in [(0, 40), (40, 80), (80, 120)]:
    m = (a[:, 0] >= lo) & (a[:, 0] < hi)
    print("   x %3d-%3d  n=%4d  mean %.4f" % (lo, hi, m.sum(), a[m, 2].mean()))
