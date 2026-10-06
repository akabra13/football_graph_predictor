"""Dependency-free SVG pitch diagrams in StatsBomb coordinates (120 x 80 yards).

Everything is drawn in pitch units, so a marker at x=102 sits exactly on the
edge of the penalty area. Colours come from CSS custom properties defined by the
report page, so the diagrams follow its light and dark themes.
"""

from __future__ import annotations

import math
from html import escape

LANE_CENTRE = {"wide_left": 9.0, "halfspace_left": 24.0, "centre": 40.0,
               "halfspace_right": 56.0, "wide_right": 71.0}


def _pitch(inner: str, label: str, lanes: bool = False) -> str:
    marks = [
        '<rect x="0" y="0" width="120" height="80" class="turf"/>',
        '<rect x="0" y="0" width="120" height="80" class="line"/>',
        '<line x1="60" y1="0" x2="60" y2="80" class="line"/>',
        '<circle cx="60" cy="40" r="10" class="line"/>',
        '<rect x="102" y="18" width="18" height="44" class="line"/>',
        '<rect x="114" y="30" width="6" height="20" class="line"/>',
        '<rect x="0" y="18" width="18" height="44" class="line"/>',
        '<rect x="0" y="30" width="6" height="20" class="line"/>',
        '<rect x="120" y="36" width="1.6" height="8" class="goal"/>',
        '<rect x="-1.6" y="36" width="1.6" height="8" class="goal"/>',
    ]
    if lanes:
        for y in (18, 30, 50, 62):
            marks.append(f'<line x1="0" y1="{y}" x2="120" y2="{y}" class="lane"/>')
        for x in (40, 80):
            marks.append(f'<line x1="{x}" y1="0" x2="{x}" y2="80" class="third"/>')
    marks.append('<text x="118" y="-1.8" class="dir" text-anchor="end">attacking &#8594;</text>')
    return (f'<svg viewBox="-3 -5 126 88" role="img" aria-label="{escape(label)}" class="pitch">'
            + "".join(marks) + inner + "</svg>")


def routes_svg(routes: list[dict]) -> str:
    """Top progression routes: middle-third entry lane -> final-third entry lane."""
    if not routes:
        return ""
    top = max(r["share"] for r in routes)
    parts = []
    for r in sorted(routes, key=lambda r: r["share"]):
        y0, y1 = LANE_CENTRE[r["from"]], LANE_CENTRE[r["to"]]
        w = 0.6 + 3.4 * r["share"] / top
        cx, cy = 60, (y0 + y1) / 2 + (y1 - y0) * 0.15
        parts.append(f'<path d="M40,{y0} Q{cx},{cy} 80,{y1}" class="route" stroke-width="{w:.2f}" '
                     f'marker-end="url(#arrow)"/>')
        parts.append(f'<circle cx="40" cy="{y0}" r="1.1" class="route-dot"/>')
        parts.append(f'<text x="{(40 + 80) / 2 + 3}" y="{(y0 + y1) / 2 - 1.2:.1f}" class="lbl">'
                     f'{r["share"]:.0%}</text>')
    defs = ('<defs><marker id="arrow" viewBox="0 0 6 6" refX="4.5" refY="3" markerWidth="3.2" '
            'markerHeight="3.2" orient="auto"><path d="M0,0 L6,3 L0,6 z" class="route-head"/></marker></defs>')
    return _pitch(defs + "".join(parts), "Most common progression routes", lanes=True)


def network_svg(nodes: list[dict], links: list[dict], size_key: str, label: str,
                link_key: str = "v", kind: str = "own") -> str:
    """Nodes at median pitch positions, sized by `size_key`, with weighted links."""
    if not nodes:
        return ""
    by_id = {n.get("id", n["name"]): n for n in nodes}
    top_link = max((l[link_key] for l in links), default=1) or 1
    top_node = max(n[size_key] for n in nodes) or 1
    parts = []
    for l in links:
        a, b = by_id.get(l["a"]), by_id.get(l["b"])
        if not a or not b:
            continue
        w = 0.25 + 2.2 * l[link_key] / top_link
        parts.append(f'<line x1="{a["x"]:.1f}" y1="{a["y"]:.1f}" x2="{b["x"]:.1f}" y2="{b["y"]:.1f}" '
                     f'class="edge {kind}" stroke-width="{w:.2f}"/>')
    for n in nodes:
        r = 1.3 + 3.6 * math.sqrt(n[size_key] / top_node)
        parts.append(f'<circle cx="{n["x"]:.1f}" cy="{n["y"]:.1f}" r="{r:.2f}" class="node {kind}"/>')
        parts.append(f'<text x="{n["x"]:.1f}" y="{n["y"] + r + 3.2:.1f}" class="name" '
                     f'text-anchor="middle">{escape(n["name"])}</text>')
    return _pitch("".join(parts), label)
