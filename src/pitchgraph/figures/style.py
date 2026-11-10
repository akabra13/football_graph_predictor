"""One visual style for every post image.

Sizes are Twitter's: 1600x900 (16:9, the timeline default) and 1200x1200
(square). Colours: a dark ink on warm paper, one accent for the claim,
grey for baselines and controls, so the eye goes to the one thing the
post is about.
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PAPER = "#F6F3EE"
INK = "#1D1D1F"
MUTED = "#8A8580"
GRID = "#E2DDD5"
ACCENT = "#D1495B"
ACCENT_2 = "#2E86AB"
CONTROL = "#B5AFA6"

SIZES = {"wide": (16, 9), "square": (12, 12)}
DPI = 100

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 16,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "axes.titlecolor": INK,
    "xtick.color": MUTED,
    "ytick.color": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "savefig.facecolor": PAPER,
})


def new_figure(size: str = "wide"):
    """Figure with room for a title block on top and a credit line below."""
    fig = plt.figure(figsize=SIZES[size], dpi=DPI)
    top = 0.80 if size == "wide" else 0.84
    ax = fig.add_axes([0.08, 0.16, 0.86, top - 0.16])
    return fig, ax


def _fit_left_labels(fig, margin=0.05, gap=0.015):
    """Move each axis right so its y tick labels start at the page margin."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width_px = fig.get_figwidth() * fig.dpi
    for ax in fig.axes:
        labels = [t for t in ax.get_yticklabels() if t.get_visible() and t.get_text()]
        if not labels or not ax.yaxis.get_visible():
            continue
        w = max(t.get_window_extent(renderer).width for t in labels) / width_px
        pos = ax.get_position()
        left = margin + w + gap
        ax.set_position([left, pos.y0, pos.x1 - left, pos.height])


def finish(fig, path: str | Path, title: str, subtitle: str = "", note: str = "") -> Path:
    """Title block, honesty note and credit line, then save."""
    wide = fig.get_figwidth() > fig.get_figheight()
    _fit_left_labels(fig)
    fig.text(0.05, 0.94, title, fontsize=34, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.05, 0.875, textwrap.fill(subtitle, 110 if wide else 80),
                 fontsize=19, color=MUTED, va="top", linespacing=1.3)
    if note:
        fig.text(0.05, 0.05, textwrap.fill(note, 150 if wide else 110),
                 fontsize=13, color=MUTED, va="bottom", linespacing=1.4)
    handle = os.environ.get("POST_HANDLE", "")
    credit = "Data: StatsBomb Open Data" + (f"   ·   {handle}" if handle else "")
    fig.text(0.05, 0.025, credit, fontsize=13, color=MUTED, va="center")
    logo = os.environ.get("PITCHGRAPH_LOGO")
    if logo and Path(logo).exists():
        img = plt.imread(logo)
        h = 0.06
        w = h * img.shape[1] / img.shape[0] * fig.get_figheight() / fig.get_figwidth()
        lax = fig.add_axes([0.95 - w, 0.005, w, h])
        lax.imshow(img)
        lax.axis("off")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path
