"""Threat and result calls: expected goals each way and win / draw / loss chances.

Design, bars and reading rules: docs/result_calls.md.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from pitchgraph.prematch.pooled import asof_arrays

FEATS = ["xg", "goals", "goals_home", "goals_away", "home_win", "draw", "away_win"]
MODELS = ("xg", "goals", "blend", "base")
FLOOR = 0.05                      # a call can go slightly negative; goals cannot
BINS = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 1.0001]


def result_table(ev, matches: pl.DataFrame) -> pl.DataFrame:
    """One row per team-match: goals, non-penalty xG and the league helper columns.

    `ev` is one competition-season of `Lake.events()` (lazy or not); `matches`
    its rows of the matches table.
    """
    shots = (ev.lazy().filter((pl.col("type") == "Shot") & (pl.col("period") <= 4)
                              & (pl.col("sub_type").fill_null("") != "Penalty"))
             .group_by("match_id", "team_id").agg(xg=pl.col("xg").fill_null(0.0).sum()).collect())
    seen = set(shots["match_id"].to_list())
    xg = {(m, t): v for m, t, v in shots.iter_rows()}
    nan = float("nan")
    rows = []
    for r in matches.iter_rows(named=True):
        hs, as_, m = r["home_score"], r["away_score"], r["match_id"]
        if hs is None or as_ is None or m not in seen:
            continue
        for home, t, o, g, ga in ((True, r["home_team_id"], r["away_team_id"], hs, as_),
                                  (False, r["away_team_id"], r["home_team_id"], as_, hs)):
            rows.append({"match_id": int(m), "team_id": int(t), "opp_id": int(o), "home": home,
                         "xg": float(xg.get((m, t), 0.0)), "goals": float(g),
                         "goals_home": float(g) if home else nan, "goals_away": nan if home else float(g),
                         "home_win": float(g > ga) if home else nan, "draw": float(g == ga) if home else nan,
                         "away_win": float(g < ga) if home else nan})
    return pl.DataFrame(rows, schema_overrides={c: pl.Float64 for c in FEATS})


def outcome_chances(lam_home: float, lam_away: float, max_goals: int = 12) -> np.ndarray:
    """[home win, draw, away win] for two independent Poisson goal counts."""
    k = np.arange(max_goals + 1)
    fact = np.array([math.factorial(int(i)) for i in k], dtype=float)
    ph = np.exp(-lam_home) * lam_home ** k / fact
    pa = np.exp(-lam_away) * lam_away ** k / fact
    grid = np.outer(ph, pa)
    p = np.array([np.tril(grid, -1).sum(), np.trace(grid), np.triu(grid, 1).sum()])
    return p / p.sum()


def rps(p: np.ndarray, outcome: int) -> float:
    """Ranked probability score for ordered outcomes (home, draw, away). Lower is better."""
    o = np.zeros(3)
    o[outcome] = 1.0
    return float(((np.cumsum(p)[:2] - np.cumsum(o)[:2]) ** 2).sum() / 2.0)


def result_calls(table: pl.DataFrame, dates: dict, start_fraction: float = 0.5) -> dict:
    """Every match of one season with a usable call.

    Returns `arrays` (the `asof_arrays` of the table, for the threat call's
    skill) and `matches`: {match_id: {home_id, away_id, lam: {model: (home, away)},
    p: {model: [home, draw, away]}, xg, outcome, scored}}.
    """
    A = asof_arrays(table, dates, FEATS, start_fraction=start_fraction)
    k = {f: i for i, f in enumerate(FEATS)}
    home = table["home"].to_numpy()
    rows: dict = {}
    for i, (m, h) in enumerate(zip(A["match"], home)):
        rows.setdefault(int(m), {})["h" if h else "a"] = i
    out = {}
    for m, pair in rows.items():
        if len(pair) < 2:
            continue
        h, a = pair["h"], pair["a"]
        lg = A["league"][h]
        need = [A["call"][h, k["xg"]], A["call"][a, k["xg"]], A["call"][h, k["goals"]], A["call"][a, k["goals"]],
                *lg]
        if not np.all(np.isfinite(need)) or lg[k["xg"]] <= 0 or lg[k["goals"]] <= 0:
            continue
        hf, af = lg[k["goals_home"]] / lg[k["goals"]], lg[k["goals_away"]] / lg[k["goals"]]
        ratio = lg[k["goals"]] / lg[k["xg"]]
        lam = {"xg": (max(A["call"][h, k["xg"]], FLOOR) * ratio * hf, max(A["call"][a, k["xg"]], FLOOR) * ratio * af),
               "goals": (max(A["call"][h, k["goals"]], FLOOR) * hf, max(A["call"][a, k["goals"]], FLOOR) * af)}
        lam["blend"] = tuple((x + g) / 2.0 for x, g in zip(lam["xg"], lam["goals"]))
        p = {name: outcome_chances(*lam[name]) for name in ("xg", "goals", "blend")}
        base = np.array([lg[k["home_win"]], lg[k["draw"]], lg[k["away_win"]]])
        p["base"] = base / base.sum()
        gh, ga = A["actual"][h, k["goals"]], A["actual"][a, k["goals"]]
        out[m] = {"home_id": int(A["team"][h]), "away_id": int(A["team"][a]),
                  "lam": {n: (float(v[0]), float(v[1])) for n, v in lam.items()},
                  "threat": (float(A["call"][h, k["xg"]]), float(A["call"][a, k["xg"]])),
                  "threat_league": float(lg[k["xg"]]),
                  "p": {n: v.tolist() for n, v in p.items()},
                  "xg": (float(A["actual"][h, k["xg"]]), float(A["actual"][a, k["xg"]])),
                  "outcome": 0 if gh > ga else 1 if gh == ga else 2,
                  "scored": bool(A["scored"][h] and A["scored"][a])}
    return {"arrays": A, "matches": out}


def evaluate(seasons: list[dict], n_boot: int = 500, seed: int = 0) -> dict:
    """Pooled RPS of each model over scored matches, the gain over the baseline
    with a 90% interval by resampling matches, hit rates and calibration."""
    ms = [m for s in seasons for m in s["matches"].values() if m["scored"]]
    if not ms:
        return {"n": 0}
    o = np.array([m["outcome"] for m in ms])
    P = {n: np.array([m["p"][n] for m in ms]) for n in MODELS}
    R = {n: np.array([rps(p, y) for p, y in zip(P[n], o)]) for n in MODELS}
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(ms), (n_boot, len(ms)))

    def ci(v):
        return [float(np.percentile(v, 5)), float(np.percentile(v, 95))]

    res = {"n": len(ms), "outcome_shares": [float((o == i).mean()) for i in range(3)], "models": {}}
    for n in MODELS:
        gain = R["base"] - R[n]
        res["models"][n] = {
            "rps": float(R[n].mean()), "gain_over_base": float(gain.mean()),
            "gain_ci": ci(gain[draws].mean(1)), "relative_gain": float(gain.mean() / R["base"].mean()),
            "top_pick_right": float((P[n].argmax(1) == o).mean()),
            "mean_chance_given_to_result": float(P[n][np.arange(len(o)), o].mean()),
            "mean_chances": P[n].mean(0).tolist()}
    d = R["goals"] - R["xg"]
    res["xg_over_goals"] = {"gain": float(d.mean()), "ci": ci(d[draws].mean(1))}
    hit = np.zeros_like(P["xg"])
    hit[np.arange(len(o)), o] = 1.0
    cal = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        sel = (P["xg"] >= lo) & (P["xg"] < hi)
        if sel.any():
            cal.append({"from": lo, "to": min(hi, 1.0), "n": int(sel.sum()),
                        "predicted": float(P["xg"][sel].mean()), "happened": float(hit[sel].mean())})
    res["calibration"] = cal
    res["calibration_worst_gap"] = float(max((abs(c["predicted"] - c["happened"]) for c in cal if c["n"] >= 100),
                                             default=float("nan")))
    res["result_call_holds"] = bool(res["models"]["xg"]["gain_ci"][0] > 0)
    return res
