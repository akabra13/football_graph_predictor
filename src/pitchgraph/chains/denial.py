"""The denial planner: which connections, if taken away, cost a team the most.

Denying a link means the team can no longer move the ball along it. What the
team does instead is unknown, so every answer is a RANGE between two bounds:

  no adaptation    the blocked moves become lost balls. The most a denial can
                   possibly hurt - the press wins the ball every time.
  full adaptation  the blocked probability is redistributed over the zone's
                   other moves in proportion to how the team already uses them.
                   The least it can hurt - the team simply plays its next-best
                   pass.

The truth lies between them. A link whose range is wide and whose lower end
is still large is a link worth defending no matter how the team reacts.

Links are named in coaches' terms: regions are thirds x the five lanes, in the
attacking team's own frame (low y = its left).
"""

from __future__ import annotations

import numpy as np

from pitchgraph.chains.team import Chain
from pitchgraph.graphs.routes import LANE_EDGES, LANES

THIRDS = ["defensive third", "middle third", "final third"]
MATERIAL = 0.03   # a denial must remove at least 3% of threat to be listed as unusual
LANE_NAMES = {"wide_left": "left flank", "halfspace_left": "left half-space", "centre": "centre",
              "halfspace_right": "right half-space", "wide_right": "right flank"}


def zone_regions(grid) -> np.ndarray:
    """Region index (third * 5 + lane) of every zone."""
    c = grid.centres()
    third = np.minimum((c[:, 0] // 40).astype(int), 2)
    lane = np.searchsorted(LANE_EDGES, c[:, 1], side="right")
    return third * len(LANES) + lane


def region_name(r: int) -> str:
    third, lane = divmod(r, len(LANES))
    return f"{LANE_NAMES[LANES[lane]]}, {THIRDS[third]}"


def deny(chain: Chain, blocked: np.ndarray, adapt: bool) -> Chain:
    """Chain with the moves in `blocked` (n x n bool) taken away."""
    n = chain.n
    P = chain.P.copy()
    moves = P[:, :n]
    lost = (moves * blocked).sum(1)
    kept = moves * ~blocked
    if adapt:
        kept_total = kept.sum(1)
        scale = np.divide(kept_total + lost, kept_total, out=np.ones(n), where=kept_total > 0)
        moves_new = kept * scale[:, None]
        # Rows with no alternative move left still lose the ball.
        lost = np.where(kept_total > 0, 0.0, lost)
    else:
        moves_new = kept
    P[:, :n] = moves_new
    P[:, n + 1] += lost
    return chain.with_P(P)


def link_mask(regions: np.ndarray, a: int, b: int) -> np.ndarray:
    return (regions[:, None] == a) & (regions[None, :] == b)


def entry_mask(regions: np.ndarray, b: int) -> np.ndarray:
    """Every move INTO region b from outside it."""
    return (regions[:, None] != b) & (regions[None, :] == b)


def plan(chain: Chain, usage: np.ndarray, reference: Chain | None = None,
         top: int = 5, min_usage: float = 0.005) -> dict:
    """Rank region links and region entries by how much threat denial removes.

    `usage` is the team's raw move counts (n x n), so links can be reported with
    how often the team actually uses them; rarely-used links are skipped.

    Lists are ordered by the team's own drop: the biggest levers. With a
    `reference` chain (normally the league), every denial is also applied to the
    reference, so each lever shows what it would cost an average team, and two
    extra lists pick out UNUSUAL dependencies: links that matter for this team
    and matter clearly more than for an average side. Those are what make a plan
    specific to this opponent; the biggest levers alone are much the same for
    everyone (cutting passes into the central box hurts any side).
    """
    regions = zone_regions(chain.grid)
    R = regions.max() + 1
    base = chain.threat
    ref_base = reference.threat if reference is not None else None
    total_moves = usage.sum() or 1.0

    def drops(c, b, mask):
        return ((b - deny(c, mask, adapt=True).threat) / b,
                (b - deny(c, mask, adapt=False).threat) / b)

    def row(mask, share, **label):
        lo, hi = drops(chain, base, mask)
        out = {**label, "usage": share, "drop_adapt": lo, "drop_no_adapt": hi}
        if reference is not None:
            rlo, rhi = drops(reference, ref_base, mask)
            out.update(league_drop_adapt=rlo, league_drop_no_adapt=rhi,
                       excess=0.5 * (lo + hi) - 0.5 * (rlo + rhi))
        return out

    links, entries = [], []
    for a in range(R):
        for b in range(R):
            if a == b:
                continue
            m = link_mask(regions, a, b)
            share = float(usage[m].sum() / total_moves)
            if share >= min_usage:
                links.append(row(m, share, **{"from": region_name(a), "to": region_name(b)}))
    for b in range(R):
        m = entry_mask(regions, b)
        share = float(usage[m].sum() / total_moves)
        if share >= min_usage:
            entries.append(row(m, share, region=region_name(b)))

    def levers(rows):
        # Biggest effect first: the guaranteed part (adapt), then the ceiling.
        return sorted(rows, key=lambda r: (-r["drop_adapt"], -r["drop_no_adapt"]))[:top]

    out = {"threat": base, "links": levers(links), "entries": levers(entries)}
    if reference is not None:
        # Unusual dependencies: material for this team AND clearly more than
        # for an average team. Ranking on excess alone surfaces near-zero links
        # whose tiny excess is noise.
        def unusual(rows):
            material = [r for r in rows if 0.5 * (r["drop_adapt"] + r["drop_no_adapt"]) >= MATERIAL]
            return sorted((r for r in material if r["excess"] > 0),
                          key=lambda r: -r["excess"])[:3]
        out["unusual_links"] = unusual(links)
        out["unusual_entries"] = unusual(entries)
    return out
