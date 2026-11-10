"""A StatsBomb pitch (120 x 80, attacking to the right) and player-shape plots."""
from __future__ import annotations

from matplotlib.patches import Arc, Circle, Rectangle

from pitchgraph.figures.style import GRID, INK, MUTED

LENGTH, WIDTH = 120.0, 80.0


def draw_pitch(ax, line=GRID, lw=2.0):
    """Lines only, no fill, so the paper shows through. y grows downward like
    StatsBomb's, so the left touchline (y = 0) is at the top."""
    def rect(x, y, w, h):
        ax.add_patch(Rectangle((x, y), w, h, fill=False, ec=line, lw=lw))
    rect(0, 0, LENGTH, WIDTH)
    ax.plot([60, 60], [0, WIDTH], color=line, lw=lw)
    for x0, sign in ((0, 1), (LENGTH, -1)):
        rect(x0 if sign > 0 else x0 - 18, 18, 18, 44)
        rect(x0 if sign > 0 else x0 - 6, 30, 6, 20)
        spot = x0 + sign * 12
        ax.add_patch(Circle((spot, 40), 0.5, color=line))
        ax.add_patch(Arc((spot, 40), 20, 20, theta1=-53 if sign > 0 else 127,
                         theta2=53 if sign > 0 else 233, color=line, lw=lw))
    ax.add_patch(Circle((60, 40), 10, fill=False, ec=line, lw=lw))
    ax.add_patch(Circle((60, 40), 0.5, color=line))
    ax.set_xlim(-2, LENGTH + 2)
    ax.set_ylim(WIDTH + 2, -2)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


def plot_shape(ax, points, color, label=None, size=520):
    """points: [(x, y, text)] of average positions; text goes inside the dot."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    ax.scatter(xs, ys, s=size, color=color, ec="white", lw=2, zorder=3, label=label)
    for x, y, txt in points:
        if txt:
            ax.text(x, y, txt, ha="center", va="center", fontsize=11, color="white",
                    fontweight="bold", zorder=4)
    return ax


def arrow_label(ax, text, xy, color=MUTED):
    ax.text(*xy, text, fontsize=14, color=color, ha="center")
    return ax


__all__ = ["draw_pitch", "plot_shape", "arrow_label", "INK"]
