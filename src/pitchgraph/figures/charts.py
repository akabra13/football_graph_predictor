"""Chart types used by posts. Each takes an axis and plain rows."""
from __future__ import annotations

import numpy as np

from pitchgraph.figures.style import ACCENT, CONTROL, GRID, INK, MUTED


def paired_bars(ax, rows, value_label="", base_label="", fmt="{:.0%}"):
    """rows: [{"label", "value", "base"}]: the result next to its baseline
    (chance, a control), horizontal, largest first as given."""
    labels = [r["label"] for r in rows][::-1]
    vals = np.array([r["value"] for r in rows])[::-1]
    base = np.array([r["base"] for r in rows])[::-1]
    y = np.arange(len(rows))
    ax.barh(y + 0.18, vals, height=0.36, color=ACCENT, label=value_label)
    ax.barh(y - 0.18, base, height=0.36, color=CONTROL, label=base_label)
    for yi, v in zip(y, vals):
        ax.text(v + 0.01, yi + 0.18, fmt.format(v), va="center", fontsize=16, color=INK, fontweight="bold")
    for yi, b in zip(y, base):
        ax.text(b + 0.01, yi - 0.18, fmt.format(b), va="center", fontsize=13, color=MUTED)
    ax.set_yticks(y, labels, fontsize=17)
    ax.set_xlim(0, 1.08)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.legend(loc="lower right", frameon=False, fontsize=15)
    return ax


def dumbbell(ax, rows, bar=None, bar_label="", value_label="", control_label="",
             xlim=(0.45, 0.70), fmt="{:.2f}"):
    """rows: [{"label", "value", "control", "highlight"?}]: each method's
    result next to its negative control. A vertical line marks the bar."""
    y = np.arange(len(rows))[::-1]
    for yi, r in zip(y, rows):
        hi = r.get("highlight", False)
        ax.plot([r["control"], r["value"]], [yi, yi], color=GRID, lw=6, zorder=1, solid_capstyle="round")
        ax.scatter(r["control"], yi, s=260, color=CONTROL, zorder=2,
                   label=control_label if yi == y[0] else None)
        ax.scatter(r["value"], yi, s=320, color=ACCENT if hi else INK, zorder=3,
                   label=value_label if yi == y[0] else None)
        ax.text(max(r["value"], r["control"]) + 0.006, yi, fmt.format(r["value"]),
                va="center", fontsize=15, color=ACCENT if hi else INK, fontweight="bold")
    ax.axvline(0.5, color=MUTED, lw=1, ls=":")
    ax.text(0.5, y[0] + 0.7, "coin flip", ha="center", fontsize=13, color=MUTED)
    if bar is not None:
        ax.axvline(bar, color=ACCENT, lw=1.5, ls="--")
        ax.text(bar, y[0] + 0.7, bar_label, ha="center", fontsize=13, color=ACCENT)
    ax.set_yticks(y, [r["label"] for r in rows], fontsize=16)
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.7, len(rows) - 0.1)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color=GRID, lw=1)
    ax.set_axisbelow(True)
    ax.legend(loc="center right", frameon=False, fontsize=14)
    return ax


def interval_bars(ax, rows, base=None, base_label="", fmt="{:.0%}", xlim=(0, 1)):
    """rows: [{"label", "value", "lo", "hi", "highlight"?}] with a baseline line."""
    y = np.arange(len(rows))[::-1]
    for yi, r in zip(y, rows):
        c = ACCENT if r.get("highlight", True) else CONTROL
        ax.barh(yi, r["value"], height=0.55, color=c)
        if r.get("lo") is not None:
            ax.plot([r["lo"], r["hi"]], [yi, yi], color=INK, lw=2.5)
        ax.text(r["value"] / 2, yi, fmt.format(r["value"]), va="center", ha="center",
                fontsize=22, color="white", fontweight="bold")
    if base is not None:
        ax.axvline(base, color=INK, lw=1.5, ls="--")
        ax.text(base, y[0] + 0.5, base_label, ha="center", fontsize=14, color=INK)
    ax.set_yticks(y, [r["label"] for r in rows], fontsize=17)
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.6, len(rows) - 0.2)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    return ax
