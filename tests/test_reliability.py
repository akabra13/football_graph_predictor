"""Bootstrap-by-match intervals and confidence labels."""
import sys
from pathlib import Path

import numpy as np
import pytest
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.analysis.reliability import estimate  # noqa: E402


def _frame(per_match_values):
    rows = [{"match_id": m, "v": v} for m, vals in enumerate(per_match_values) for v in vals]
    return pl.DataFrame(rows)


def per_match_total(f):
    return f["v"].sum() / f["match_id"].n_unique()


def test_per_match_stat_interval_contains_the_estimate():
    """Regression: resampling with replacement must relabel repeated matches,
    or per-match denominators undercount and the interval lands above the value."""
    rng = np.random.default_rng(1)
    f = _frame([rng.uniform(0, 1, 30).tolist() for _ in range(38)])
    e = estimate(f, per_match_total, league=None, n_boot=200)
    assert e.lo <= e.value <= e.hi


def test_clear_difference_from_league_is_high_confidence():
    f = _frame([[1.0, 1.0, 1.1] for _ in range(20)])
    e = estimate(f, per_match_total, league=1.0, n_boot=100)
    assert e.confidence == "High"


def test_no_difference_from_league_is_low_confidence():
    rng = np.random.default_rng(2)
    f = _frame([rng.normal(1.0, 0.5, 5).tolist() for _ in range(20)])
    league = per_match_total(f)
    e = estimate(f, per_match_total, league=league, n_boot=100)
    assert e.confidence in ("Low", "Medium")
    assert e.lo < league < e.hi


def test_single_match_is_always_low_confidence():
    e = estimate(_frame([[1.0, 2.0]]), per_match_total, league=0.1)
    assert e.confidence == "Low"


def test_fast_ratio_path_agrees_with_the_generic_bootstrap():
    """The ledger fast path must give the same answer as resampling frames."""
    from pitchgraph.analysis.reliability import estimate_ratio
    rng = np.random.default_rng(3)
    num = rng.poisson(20, 38).astype(float)
    den = num + rng.poisson(30, 38)
    f = pl.DataFrame({"match_id": np.repeat(np.arange(38), 2),
                      "num": np.column_stack([num, np.zeros(38)]).ravel(),
                      "den": np.column_stack([den, np.zeros(38)]).ravel()})
    slow = estimate(f, lambda g: g["num"].sum() / g["den"].sum(), league=0.35, n_boot=2000)
    fast = estimate_ratio(num, den, league=0.35, n_boot=2000)
    assert fast.value == pytest.approx(slow.value)
    assert fast.halves == pytest.approx(slow.halves)
    assert fast.lo == pytest.approx(slow.lo, abs=0.01) and fast.hi == pytest.approx(slow.hi, abs=0.01)
    assert fast.confidence == slow.confidence
