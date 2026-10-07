"""How much to trust a number computed from one team's matches.

Two independent checks, and a label combining them:

  bootstrap   resample the team's MATCHES (not events: events within a match are
              correlated, and resampling them would overstate precision the same
              way v1's interaction test once did) and take a 90% interval.
  split-half  compute the stat on odd- and even-numbered matches separately. If
              the two halves disagree about which side of the league average the
              team is on, the "finding" is not stable.

  label       High   interval excludes the league value AND halves agree
              Medium one of the two
              Low    neither - reported, but flagged as not established
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import polars as pl


@dataclass
class Estimate:
    value: float
    lo: float
    hi: float
    league: float | None
    halves: tuple[float, float]
    n_matches: int
    confidence: str

    @property
    def vs_league(self) -> float | None:
        if self.league in (None, 0) or not np.isfinite(self.league):
            return None
        return self.value / self.league


def estimate(frame: pl.DataFrame, stat: Callable[[pl.DataFrame], float],
             league: float | None = None, n_boot: int = 300, seed: int = 0) -> Estimate:
    """`stat` maps a frame of the team's rows (with match_id) to one number."""
    matches = np.array(frame["match_id"].unique().sort().to_list())
    value = float(stat(frame))
    n = len(matches)
    if n < 2:
        return Estimate(value, np.nan, np.nan, league, (np.nan, np.nan), n, "Low")

    rng = np.random.default_rng(seed)
    by_match = {m: frame.filter(pl.col("match_id") == m) for m in matches}
    dtype = frame.schema["match_id"]
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(matches, size=n, replace=True)
        # Each drawn copy gets its own match id. Resampling WITH replacement
        # repeats matches, and without relabelling a repeated match counts once
        # in any per-match denominator (n_unique) but twice in the numerator,
        # which pushed per-match stats' intervals entirely above the estimate.
        copies = [by_match[m].with_columns(pl.lit(k, dtype=dtype).alias("match_id"))
                  for k, m in enumerate(pick)]
        boots.append(stat(pl.concat(copies)))
    boots = np.array([b for b in boots if np.isfinite(b)])
    lo, hi = (np.percentile(boots, [5, 95]) if len(boots) else (np.nan, np.nan))

    odd = frame.filter(pl.col("match_id").is_in(matches[0::2].tolist()))
    even = frame.filter(pl.col("match_id").is_in(matches[1::2].tolist()))
    halves = (float(stat(odd)), float(stat(even)))

    return Estimate(value, float(lo), float(hi), league, halves, n,
                    _label(value, lo, hi, league, halves))


def estimate_ratio(num: np.ndarray, den: np.ndarray, league: float | None = None,
                   n_boot: int = 1000, seed: int = 0) -> Estimate:
    """Fast path for ledger claims: value = sum(num) / sum(den) over matches.

    Rows are matches in chronological (or id) order. Resampling rows is the same
    bootstrap-by-match as `estimate`, without re-running any analysis, so it
    affords 1000 resamples in milliseconds. Split halves are alternate rows,
    matching `estimate`.
    """
    num, den = np.asarray(num, float), np.asarray(den, float)
    n = len(num)

    def ratio(a, b):
        return float(a.sum() / b.sum()) if b.sum() > 0 else float("nan")

    value = ratio(num, den)
    if n < 2:
        return Estimate(value, np.nan, np.nan, league, (np.nan, np.nan), n, "Low")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    nb, db = num[idx].sum(1), den[idx].sum(1)
    boots = np.divide(nb, db, out=np.full(n_boot, np.nan), where=db > 0)
    boots = boots[np.isfinite(boots)]
    lo, hi = (np.percentile(boots, [5, 95]) if len(boots) else (np.nan, np.nan))
    halves = (ratio(num[0::2], den[0::2]), ratio(num[1::2], den[1::2]))
    return Estimate(value, float(lo), float(hi), league, halves, n,
                    _label(value, lo, hi, league, halves))


def _label(value, lo, hi, league, halves) -> str:
    if league is None or not np.isfinite(league):
        # Nothing to compare against: judge on precision and agreement alone.
        width_ok = np.isfinite(lo) and (hi - lo) <= 0.5 * abs(value) if value else False
        agree = np.isfinite(halves).all() and abs(halves[0] - halves[1]) <= 0.25 * abs(value) if value else False
        score = int(bool(width_ok)) + int(bool(agree))
    else:
        separated = np.isfinite(lo) and (lo > league or hi < league)
        agree = np.isfinite(halves).all() and ((halves[0] - league) * (halves[1] - league) > 0)
        score = int(bool(separated)) + int(bool(agree))
    return {2: "High", 1: "Medium", 0: "Low"}[score]


def split_half_agreement(estimates: list[Estimate]) -> float:
    """Share of claims whose two halves sit on the same side of the league."""
    ok = [e for e in estimates if e.league is not None and np.isfinite(e.halves).all()]
    if not ok:
        return float("nan")
    return float(np.mean([(e.halves[0] - e.league) * (e.halves[1] - e.league) > 0 for e in ok]))
