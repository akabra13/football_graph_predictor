"""Does doing what an instruction says go with a better outcome?

Design, limits and reading rules: docs/followed.md.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.graphs.routes import LANE_EDGES
from pitchgraph.prematch.replay import region_expr

FEATURES = ["lv_press", "lv_long", "lv_width", "lv_lever", "lv_xgd90"]
OUTCOME = "lv_xgd90"
MIN_LEVEL_MINUTES = 20.0
LINE, LONG = 80.0, 40.0

# rule id -> (feature showing the action, whose row, direction of "did it")
ACTIONS = {
    "press_them": ("lv_press", "we", +1),
    "leave_them": ("lv_press", "we", -1),
    "pressed_deep": ("lv_long", "we", +1),
    "centre_tighter": ("lv_width", "we", +1),
    "they_come_central": ("lv_lever", "they", -1),
}


def level_table(ev) -> pl.DataFrame:
    """One row per team-match, measured only while the score was level.

    `ev` is one competition-season of `Lake.events()` (lazy or not). Columns:
    match_id, team_id, opp_id, level_minutes and FEATURES (NaN when the match
    had fewer than MIN_LEVEL_MINUTES level minutes or the ratio is empty).
    """
    kind = pl.col("sub_type").fill_null("")
    goal = ((pl.col("type") == "Shot") & (pl.col("outcome") == "Goal")) | (pl.col("type") == "Own Goal For")
    home = pl.col("team_id") == pl.col("home_team_id")
    e = (ev.lazy().filter(pl.col("period") <= 4).sort("match_id", "period", "idx")
         .with_columns(hg=(goal & home).fill_null(False).cast(pl.Int32),
                       ag=(goal & ~home).fill_null(False).cast(pl.Int32))
         .with_columns(h=pl.col("hg").cum_sum().over("match_id") - pl.col("hg"),       # score before this event
                       a=pl.col("ag").cum_sum().over("match_id") - pl.col("ag"),
                       dt=pl.col("period_seconds").diff().over("match_id", "period").fill_null(0.0).clip(0.0, 120.0))
         .with_columns(level=pl.col("h") == pl.col("a")))
    minutes = e.group_by("match_id").agg(level_minutes=(pl.col("dt") * pl.col("level")).sum() / 60.0)

    shot = (pl.col("type") == "Shot") & (kind != "Penalty")
    pas = pl.col("type") == "Pass"
    done = pas & pl.col("outcome").is_null() & pl.col("end_x").is_not_null()
    final = pl.col("x").fill_null(0.0) >= LINE
    onball = pl.col("type").is_in(["Pass", "Carry", "Shot", "Dribble"])
    flank = (pl.col("y") < LANE_EDGES[0]) | (pl.col("y") >= LANE_EDGES[-1])
    reg0 = region_expr(pl.col("x"), pl.col("y"))
    reg1 = region_expr(pl.col("end_x"), pl.col("end_y"))
    t = (e.filter(pl.col("level")).group_by("match_id", "team_id").agg(
        xg=pl.when(shot).then(pl.col("xg").fill_null(0.0)).otherwise(0.0).sum(),
        press=((pl.col("type") == "Pressure") & final).sum(),
        passes=pas.sum(),
        long=(pas & ((pl.col("end_x") - pl.col("x")) >= LONG)).fill_null(False).sum(),
        fin=(onball & final).sum(),
        wide=(onball & final & flank).fill_null(False).sum(),
        lever=(done & reg0.is_in([11, 13]) & (reg1 == 12)).fill_null(False).sum(),
    ).collect())
    opp = t.select("match_id", pl.col("team_id").alias("opp_id"), pl.col("xg").alias("opp_xg"),
                   pl.col("passes").alias("opp_passes"))
    nan = float("nan")

    def ratio(num, den):
        return pl.when(enough & (den > 0)).then(num / den).otherwise(nan)

    enough = pl.col("level_minutes") >= MIN_LEVEL_MINUTES
    t = (t.join(opp, on="match_id").filter(pl.col("team_id") != pl.col("opp_id"))
         .join(minutes.collect(), on="match_id")
         .with_columns(
             lv_press=ratio(pl.col("press"), pl.col("opp_passes")),
             lv_long=ratio(pl.col("long"), pl.col("passes")),
             lv_width=ratio(pl.col("wide"), pl.col("fin")),
             lv_lever=ratio(pl.col("lever"), pl.col("passes")),
             lv_xgd90=pl.when(enough).then((pl.col("xg") - pl.col("opp_xg")) / pl.col("level_minutes") * 90.0)
             .otherwise(nan)))
    return t.select("match_id", "team_id", "opp_id", "level_minutes", *FEATURES).sort("match_id", "team_id")


def rule_rows(p: dict, feats: list[str], rule: tuple, threshold: float):
    """Per row of one season's `asof_arrays`: usable, rule fired, team did it, outcome above its call."""
    name, who, feature, direction, _ = rule
    act_feature, act_who, act_dir = ACTIONS[name]
    n = len(p["match"])
    me = np.arange(n)
    where = {(int(m), int(t)): i for i, (m, t) in enumerate(zip(p["match"], p["team"]))}
    other = np.array([where.get((int(m), int(o)), -1) for m, o in zip(p["match"], p["opp"])])
    ok = p["scored"].copy()

    src = me if who == "we" else other
    ok &= src >= 0
    s = np.where(src >= 0, src, 0)
    k = feats.index(feature)
    call, own, league, sd = (p[x][s, k] for x in ("call", "own", "league", "league_sd"))
    ref = own if who == "we" else call - own + league
    with np.errstate(invalid="ignore", divide="ignore"):
        dep = direction * (call - ref) / sd
    ok &= np.isfinite(dep) & (sd > 0)
    fired = np.where(np.isfinite(dep), dep, -np.inf) >= threshold

    src = me if act_who == "we" else other
    ok &= src >= 0
    s = np.where(src >= 0, src, 0)
    c = feats.index(act_feature)
    actual, usual = p["actual"][s, c], p["own"][s, c]
    ok &= np.isfinite(actual) & np.isfinite(usual)
    with np.errstate(invalid="ignore"):
        did = act_dir * (actual - usual) > 0

    o = feats.index(OUTCOME)
    resid = p["actual"][:, o] - p["call"][:, o]
    ok &= np.isfinite(resid)
    return ok, fired, did, np.where(np.isfinite(resid), resid, 0.0)


def evaluate(parts: list[dict], feats: list[str], rules: list, threshold: float, n_boot: int = 500,
             seed: int = 0) -> dict:
    """Per testable rule: the outcome gap between teams that did it and teams
    that did not, where the rule fired and where it did not, and the difference
    of the two. `parts` are `asof_arrays` with a `weight` (level minutes) each."""
    rng = np.random.default_rng(seed)
    out = {}
    for rule in rules:
        if rule[0] not in ACTIONS:
            continue
        fired, did, resid, w, keys = [], [], [], [], []
        for i, p in enumerate(parts):
            ok, f, d, r = rule_rows(p, feats, rule, threshold)
            fired.append(f[ok]); did.append(d[ok]); resid.append(r[ok]); w.append(p["weight"][ok])
            keys.append(np.array([f"{i}_{m}" for m in p["match"][ok]]))
        fired, did, resid, w, keys = (np.concatenate(v) for v in (fired, did, resid, w, keys))
        uniq, inv = np.unique(keys, return_inverse=True)
        cells = {}
        for a in (True, False):
            for b in (True, False):
                sel = (fired == a) & (did == b)
                cells[(a, b)] = (np.bincount(inv, weights=np.where(sel, w * resid, 0.0), minlength=len(uniq)),
                                 np.bincount(inv, weights=np.where(sel, w, 0.0), minlength=len(uniq)))

        def stats(m):
            mean = {c: (m * s).sum() / (m * ww).sum() if (m * ww).sum() > 0 else np.nan for c, (s, ww) in cells.items()}
            gap_fired = mean[(True, True)] - mean[(True, False)]
            gap_not = mean[(False, True)] - mean[(False, False)]
            return gap_fired, gap_not, gap_fired - gap_not

        point = stats(np.ones(len(uniq)))
        boots = np.array([stats(np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq)).astype(float))
                          for _ in range(n_boot)])

        def ci(j):
            return [float(np.nanpercentile(boots[:, j], 5)), float(np.nanpercentile(boots[:, j], 95))]

        lo, hi = ci(2)
        out[rule[0]] = {
            "fired": int(fired.sum()), "did_it_when_fired": float(did[fired].mean()) if fired.any() else None,
            "did_it_when_not_fired": float(did[~fired].mean()) if (~fired).any() else None,
            "gap_when_fired": float(point[0]), "gap_when_fired_ci": ci(0),
            "gap_when_not_fired": float(point[1]), "gap_when_not_fired_ci": ci(1),
            "extra_when_asked": float(point[2]), "extra_when_asked_ci": [lo, hi],
            "verdict": "supported" if lo > 0 else "contradicted" if hi < 0 else "no evidence either way"}
    return out
