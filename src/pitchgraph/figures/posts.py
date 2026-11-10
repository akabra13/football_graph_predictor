"""Render one post spec (a dict, usually loaded from posts/*.json) to a PNG.

Spec fields: id, kind, title, subtitle, note (the honesty line: sample
size, interval, what failed), size ("wide" or "square"), and the kind's
own data. Kinds: paired_bars, dumbbell, interval_bars, pitch_shapes.
"""
from __future__ import annotations

from pathlib import Path

from pitchgraph.figures import charts
from pitchgraph.figures.pitch import draw_pitch, plot_shape
from pitchgraph.figures.style import ACCENT, ACCENT_2, MUTED, finish, new_figure


def _pitch_shapes(ax, spec):
    """spec["shapes"]: [{"label", "points": [[x, y, text], ...]}], up to two."""
    draw_pitch(ax)
    colours = (ACCENT_2, ACCENT)
    for shape, c in zip(spec["shapes"], colours):
        plot_shape(ax, shape["points"], c, label=shape["label"])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=2, frameon=False, fontsize=16)
    ax.text(118, 84, "attacking →", ha="right", fontsize=13, color=MUTED)


KINDS = {
    "paired_bars": lambda ax, s: charts.paired_bars(ax, s["rows"], s.get("value_label", ""),
                                                    s.get("base_label", ""), s.get("fmt", "{:.0%}")),
    "dumbbell": lambda ax, s: charts.dumbbell(ax, s["rows"], s.get("bar"), s.get("bar_label", ""),
                                              s.get("value_label", ""), s.get("control_label", ""),
                                              tuple(s.get("xlim", (0.45, 0.70))), s.get("fmt", "{:.2f}")),
    "interval_bars": lambda ax, s: charts.interval_bars(ax, s["rows"], s.get("base"), s.get("base_label", ""),
                                                        s.get("fmt", "{:.0%}"), tuple(s.get("xlim", (0, 1)))),
    "pitch_shapes": _pitch_shapes,
}


def render(spec: dict, out_dir: str | Path) -> Path:
    if spec["kind"] not in KINDS:
        raise ValueError(f"unknown post kind {spec['kind']!r}; known: {sorted(KINDS)}")
    fig, ax = new_figure(spec.get("size", "wide"))
    KINDS[spec["kind"]](ax, spec)
    return finish(fig, Path(out_dir) / f"{spec['id']}.png", spec["title"],
                  spec.get("subtitle", ""), spec.get("note", ""))
