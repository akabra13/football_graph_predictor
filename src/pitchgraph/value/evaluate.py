"""Is the value model any good? Held-out-competition evaluation.

For every competition-season in turn: fit on all the others, then ask how well
each in-possession action's starting value predicts `xg_after` (the xG the
possession actually went on to produce) in the held-out competition.

Two baselines:
  constant   the training mean - skill 0 by construction
  zone mean  the empirical mean of xg_after per zone in training. This is the
             direct estimator of the target, so the chain should not be
             expected to beat it on raw MSE with plenty of data. The chain's
             case is structure: it values every *action*, decomposes value
             into shoot / move / lose, and should degrade more gracefully when
             data is thin. `data_efficiency` tests exactly that.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.data.possessions import add_possession_context
from pitchgraph.value.markov import MarkovValue, classify_actions, zone_expr


def prepare(events: pl.LazyFrame) -> pl.DataFrame:
    """Open-play, in-possession actions with their outcome target."""
    ev = add_possession_context(events)
    act = classify_actions(ev, open_play_only=True)
    return act.with_columns(
        season_key=pl.concat_str([pl.col("competition_id"), pl.col("season_id")], separator="_"),
    ).collect()


def _scores(y: np.ndarray, pred: np.ndarray, base: float) -> dict:
    """Skill vs constant, correlation, and calibration (mean pred / mean actual)."""
    mse = float(np.mean((y - pred) ** 2))
    mse0 = float(np.mean((y - base) ** 2))
    return {"mse": mse, "skill": 1 - mse / mse0,
            "calib": float(pred.mean() / y.mean()),
            "corr": float(np.corrcoef(y, pred)[0, 1]) if np.std(pred) > 0 else 0.0}


def _zone_mean(train: pl.DataFrame, test: pl.DataFrame, nx: int, ny: int) -> np.ndarray:
    z = zone_expr(pl.col("x"), pl.col("y"), nx, ny).alias("z")
    table = train.select(z, "xg_after").group_by("z").agg(m=pl.col("xg_after").mean())
    t = test.select(z).join(table, on="z", how="left")
    return t["m"].fill_null(float(train["xg_after"].mean())).to_numpy()


def _scale(model: MarkovValue, train: pl.DataFrame) -> float:
    """One multiplicative calibration factor, fit on training data only.

    The chain ends at the first shot; xg_after sums every shot in the
    possession (rebounds, second balls), so the chain runs low (~0.59x on an
    8-league sample). The factor is fit on training data only.

    RESULT: rejected. Rescaling fixed the mean but made held-out skill WORSE
    (0.075 -> 0.053): the shortfall is not a constant factor, and scaling
    inflates the near-goal zones that were already high. Kept in the evaluation
    so the finding stays reproducible; the model itself is left unscaled and is
    used for RELATIVE value, where it matches the direct estimator.
    """
    pred = train.select(model.state_value(pl.col("x"), pl.col("y"))).to_series().to_numpy()
    return float(train["xg_after"].mean() / max(pred.mean(), 1e-9))


def holdout(acts: pl.DataFrame, nx: int = 16, ny: int = 12) -> pl.DataFrame:
    rows = []
    for key in acts["season_key"].unique().sort().to_list():
        train = acts.filter(pl.col("season_key") != key)
        test = acts.filter(pl.col("season_key") == key)
        if test.height < 1000:
            continue
        model = MarkovValue(nx, ny).fit(train.lazy())
        y = test["xg_after"].to_numpy()
        base = float(train["xg_after"].mean())
        chain = test.select(model.state_value(pl.col("x"), pl.col("y"))).to_series().to_numpy()
        k = _scale(model, train)
        zone = _zone_mean(train, test, nx, ny)
        first = test.row(0, named=True)
        for name, pred in (("markov", chain), ("markov_cal", chain * k), ("zone_mean", zone)):
            rows.append({"held_out": f"{first['competition']} {first['season']}",
                         "gender": first["gender"], "model": name, "n": test.height,
                         **_scores(y, pred, base)})
    return pl.DataFrame(rows)


def data_efficiency(acts: pl.DataFrame, fractions=(0.02, 0.05, 0.2, 1.0),
                    nx: int = 16, ny: int = 12, seed: int = 0) -> pl.DataFrame:
    """Train on a fraction of MATCHES, test on a fixed held-out set of matches."""
    rng = np.random.default_rng(seed)
    matches = np.array(acts["match_id"].unique().sort().to_list())
    rng.shuffle(matches)
    test_ids = set(matches[: len(matches) // 4].tolist())
    pool = matches[len(matches) // 4:]
    test = acts.filter(pl.col("match_id").is_in(list(test_ids)))
    y = test["xg_after"].to_numpy()
    rows = []
    for f in fractions:
        ids = pool[: max(2, int(len(pool) * f))].tolist()
        train = acts.filter(pl.col("match_id").is_in(ids))
        base = float(train["xg_after"].mean())
        chain = MarkovValue(nx, ny).fit(train.lazy())
        pred = test.select(chain.state_value(pl.col("x"), pl.col("y"))).to_series().to_numpy()
        zone = _zone_mean(train, test, nx, ny)
        for name, p in (("markov", pred), ("zone_mean", zone)):
            rows.append({"train_matches": len(ids), "model": name, **_scores(y, p, base)})
    return pl.DataFrame(rows)


def monotone_share(model: MarkovValue) -> float:
    """Share of adjacent x-columns where mean value rises toward goal."""
    cols = model.grid().mean(axis=1)
    return float(np.mean(np.diff(cols) > 0))
