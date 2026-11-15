"""The signature image: a team's flow graph on a pitch, with the links the
denial planner would cut.

`flow_data` turns a team chain into plain numbers (testable, JSON-able);
`flow_map` draws them. Frame: the team attacks left to right and y = 0 (its
left flank) is at the top of the image.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle

from pitchgraph.chains import denial
from pitchgraph.chains.team import Chain
from pitchgraph.figures.pitch import draw_pitch
from pitchgraph.figures.style import ACCENT, ACCENT_2, DPI, GRID, INK, MUTED, SIZES, finish

REGION_X = [20.0, 60.0, 100.0]
REGION_Y = [9.0, 24.0, 40.0, 56.0, 71.0]
N_REGIONS = 15


def region_centre(r: int) -> tuple[float, float]:
    third, lane = divmod(r, 5)
    return REGION_X[third], REGION_Y[lane]


def region_flow(chain: Chain) -> np.ndarray:
    """Expected moves per possession between the 15 regions (thirds x lanes)."""
    regions = denial.zone_regions(chain.grid)
    F = chain.visits()[:, None] * chain.move
    R = np.zeros((N_REGIONS, N_REGIONS))
    np.add.at(R, (regions[:, None].repeat(chain.n, 1), regions[None, :].repeat(chain.n, 0)), F)
    return R


def flow_data(chain: Chain, league: Chain, usage: np.ndarray, top_flows: int = 12,
              top_links: int = 3) -> dict:
    """Numbers behind the image: zone shading (visit share vs league), the
    strongest region-to-region flows, and the planner's links to cut.

    Links prefer the planner's UNUSUAL dependencies (matter for this team
    and clearly more than for an average side); the biggest levers fill
    the list when there are fewer than `top_links` of those.
    """
    v, lv = chain.visits(), league.visits()
    share, lshare = v / v.sum(), lv / lv.sum()
    R = region_flow(chain)
    np.fill_diagonal(R, 0.0)
    order = np.argsort(-R, axis=None)[:top_flows]
    flows = [{"from": int(a), "to": int(b), "flow": float(R[a, b])}
             for a, b in zip(*np.unravel_index(order, R.shape)) if R[a, b] > 0]

    plan = denial.plan(chain, usage, reference=league, top=top_links)
    names = {denial.region_name(r): r for r in range(N_REGIONS)}
    candidates = [(r, True) for r in plan.get("unusual_links", [])] + [(r, False) for r in plan["links"]]
    picked, seen = [], set()
    for row, unusual in candidates:
        key = (row["from"], row["to"])
        if key in seen or len(picked) >= top_links:
            continue
        seen.add(key)
        picked.append({"from": names[row["from"]], "to": names[row["to"]],
                       "from_label": row["from"], "to_label": row["to"],
                       "usage": float(row["usage"]), "lo": float(row["drop_adapt"]),
                       "hi": float(row["drop_no_adapt"]),
                       "league_lo": float(row["league_drop_adapt"]),
                       "league_hi": float(row["league_drop_no_adapt"]), "unusual": unusual})
    return {"zone_bounds": chain.grid.bounds().tolist(),
            "zone_vs_league": (share / np.clip(lshare, 1e-9, None)).tolist(),
            "flows": flows, "links": picked, "threat": chain.threat, "league_threat": league.threat}


def _arrow(ax, a, b, lw, color, alpha=1.0, z=3, rad=0.18):
    ax.add_patch(FancyArrowPatch(region_centre(a), region_centre(b), connectionstyle=f"arc3,rad={rad}",
                                 arrowstyle="-|>", mutation_scale=10 + 3 * lw, lw=lw, color=color,
                                 alpha=alpha, zorder=z, shrinkA=6, shrinkB=6))


def _cap(label: str) -> str:
    return label[:1].upper() + label[1:]


def flow_map(data: dict, out: str | Path, title: str, subtitle: str = "", note: str = "") -> Path:
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=SIZES["wide"], dpi=DPI)
    ax = fig.add_axes([0.04, 0.15, 0.60, 0.66])
    side = fig.add_axes([0.67, 0.15, 0.29, 0.66])

    # zones: shaded where the team is present more than the league average
    for (x0, x1, y0, y1), ratio in zip(data["zone_bounds"], data["zone_vs_league"]):
        a = float(np.clip((ratio - 1.0) / 0.5, 0, 1)) * 0.45
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color=ACCENT_2, alpha=a, lw=0, zorder=1))
    draw_pitch(ax, line="#CFC9BF")

    cut = {(k["from"], k["to"]) for k in data["links"]}
    top = max(f["flow"] for f in data["flows"]) if data["flows"] else 1.0
    for f in data["flows"]:
        if (f["from"], f["to"]) not in cut:
            _arrow(ax, f["from"], f["to"], 1.5 + 6 * f["flow"] / top, INK, alpha=0.55)
    for i, k in enumerate(data["links"]):
        _arrow(ax, k["from"], k["to"], 7 if i == 0 else 4.5, ACCENT, z=5)
        x, y = np.mean([region_centre(k["from"]), region_centre(k["to"])], axis=0)
        ax.text(x, y - 4.5, str(i + 1), fontsize=17, fontweight="bold", color="white", ha="center",
                va="center", zorder=6, bbox=dict(boxstyle="circle,pad=0.25", fc=ACCENT, ec="white", lw=1.5))
    ax.text(60, 86, "attacking  →", ha="center", fontsize=13, color=MUTED)
    ax.set_ylim(88, -2)

    # side panel: how much threat each cut removes, as a range
    side.axis("off")
    side.set_xlim(0, 1)
    side.set_ylim(0, 1)
    side.text(0, 0.97, "Cut this link, lose this much threat", fontsize=17, fontweight="bold",
              color=INK, va="top")
    hi_max = max([k["hi"] for k in data["links"]] + [0.01])
    for i, k in enumerate(data["links"]):
        y = 0.80 - i * 0.27
        side.text(0.02, y, str(i + 1), fontsize=15, fontweight="bold", color="white", va="center", ha="center",
                  bbox=dict(boxstyle="circle,pad=0.25", fc=ACCENT, ec="none"))
        side.text(0.09, y + 0.028, _cap(k["from_label"]), fontsize=13.5, color=INK, va="center")
        side.text(0.09, y - 0.028, "→ " + k["to_label"], fontsize=13.5, color=INK, va="center")
        x0, x1 = 0.09 + 0.8 * k["lo"] / hi_max, 0.09 + 0.8 * k["hi"] / hi_max
        side.plot([0.09, 0.89], [y - 0.09] * 2, color=GRID, lw=8, solid_capstyle="round")
        side.plot([x0, x1], [y - 0.09] * 2, color=ACCENT, lw=8, solid_capstyle="round")
        side.text(0.09, y - 0.145, "{:.0%} if they adapt  ·  {:.0%} if they lose it".format(k["lo"], k["hi"]),
                  fontsize=12.5, color=MUTED, va="center")
    side.text(0, 0.0, "Blue zones: used more than the league average.\nDark arrows: their strongest routes.",
              fontsize=12, color=MUTED, va="bottom", linespacing=1.4)
    return finish(fig, out, title, subtitle, note)
