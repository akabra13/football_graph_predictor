import sys
sys.path.insert(0, "src")
import numpy as np
from pitchgraph.io.loader import StatsBomb
from pitchgraph.model.frames import build_snapshots
from pitchgraph.model.resistance import ResistanceGraph, ZoneGrid

sb = StatsBomb()
snaps = build_snapshots(sb, 3869685, {"Pass", "Carry"})
s = [x for x in snaps if x.ball[0] > 70][5]
rg = ResistanceGraph(s)
grid = rg.grid

print("ball at (%.0f,%.0f)  observability %.2f" % (s.ball[0], s.ball[1], rg.observability))
print("visible_area polygon:")
print(s.visible_area.round(1))
print()
# Which x-bands are observed?
obs = rg.observed.reshape(grid.nx, grid.ny)
print("observed zones per 10-yard x-band (of %d rows each):" % grid.ny)
for i in range(grid.nx):
    xc = (i + 0.5) * grid.dx
    print("  x=%5.0f : %d/%d  %s" % (xc, obs[i].sum(), grid.ny, "#" * int(obs[i].sum())))
print()
# Across the match: how observable is the attacking third when attacking?
att = [x for x in snaps if x.ball[0] > 80]
o = []
for x in att[:200]:
    r = ResistanceGraph(x)
    ob = r.observed.reshape(grid.nx, grid.ny)
    o.append((r.observability, ob[9:, :].mean()))   # x>90 band = near goal
o = np.array(o)
print("ball in attacking third (n=%d):" % len(o))
print("  whole-pitch observability : mean %.2f" % o[:, 0].mean())
print("  near-goal band (x>90)     : mean %.2f" % o[:, 1].mean())
