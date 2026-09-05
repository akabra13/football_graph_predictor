"""Calibrate the terminal shot probability against real StatsBomb xG."""
import sys
sys.path.insert(0, "src")
import numpy as np
from pitchgraph.io.loader import StatsBomb

sb = StatsBomb()
matches = sb.matches(43, 106)
rows = []
for m in matches[:30]:
    for e in sb.events(m["match_id"]):
        if e["type"]["name"] != "Shot" or not e.get("location"):
            continue
        sh = e.get("shot", {})
        xg = sh.get("statsbomb_xg")
        if xg is None or sh.get("type", {}).get("name") == "Penalty":
            continue
        x, y = e["location"][0], e["location"][1]
        rows.append((x, y, xg))
a = np.array(rows)
print("open-play/FK shots with xG:", len(a))

# Distance and angle to the goal at (120,40), goal mouth 36-44.
d = np.hypot(120 - a[:, 0], a[:, 1] - 40)
lat = np.abs(a[:, 1] - 40)
xg = a[:, 2]

print("\nxG by distance band (yards):")
for lo, hi in [(0, 6), (6, 12), (12, 18), (18, 24), (24, 30), (30, 40), (40, 120)]:
    m = (d >= lo) & (d < hi)
    if m.sum() > 3:
        print("  %3d-%3d yds  n=%4d  mean xG %.4f  median %.4f"
              % (lo, hi, m.sum(), xg[m].mean(), np.median(xg[m])))

# Fit log(xG) ~ a + b*d + c*lateral  (simple, monotone, interpretable)
X = np.column_stack([np.ones_like(d), d, lat])
beta, *_ = np.linalg.lstsq(X, np.log(np.clip(xg, 1e-4, 1)), rcond=None)
pred = np.exp(X @ beta)
print("\nfit log(xG) = %.4f + %.5f*dist + %.5f*lateral" % tuple(beta))
print("corr(pred, actual) = %.3f" % np.corrcoef(pred, xg)[0, 1])
print("implied xG:  6yd central %.4f | 12yd %.4f | 18yd %.4f | 30yd %.4f | 45yd %.4f"
      % tuple(np.exp(beta[0] + beta[1] * np.array([6, 12, 18, 30, 45]))))
