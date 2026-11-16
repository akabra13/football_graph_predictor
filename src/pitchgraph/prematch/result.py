"""Threat and result calls: expected goals each way and win / draw / loss chances.

Design, bars and reading rules: docs/result_calls.md.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import polars as pl

from pitchgraph.prematch.pooled import asof_arrays

FEATS = ["xg", "goals", "goals_home", "goals_away", "home_win", "draw", "away_win"]
MODELS = ("xg", "goals", "blend", "base")
FLOOR = 0.05                      # a call can go slightly negative; goals cannot
BINS = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 1.0001]
SHRINKAGE = "fixed"               # "eb" = league-aware pseudo-matches (docs/result_calls.md)
STRETCH = 1.0                     # see docs/result_calls.md (calibration fix)
GRID = [round(1.0 + 0.1 * i, 1) for i in range(11)]


def is_lockbox(key: str) -> bool:
    """Held-out competition-seasons for the calibration fix: fixed by a hash of the key."""
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % 2 == 0


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


def result_calls(table: pl.DataFrame, dates: dict, start_fraction: float = 0.5, stretch: float | None = None,
                 arrays: dict | None = None, pseudo: str | None = None) -> dict:
    """Every match of one season with a usable call.

    Returns `arrays` (the `asof_arrays` of the table, for the threat call's
    skill) and `matches`: {match_id: {home_id, away_id, lam: {model: (home, away)},
    p: {model: [home, draw, away]}, xg, outcome, scored}}.
    """
    stretch = STRETCH if stretch is None else stretch
    A = arrays if arrays is not None else asof_arrays(table, dates, FEATS, start_fraction=start_fraction,
                                                      pseudo=SHRINKAGE if pseudo is None else pseudo)
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
        th, ta = (lg[k["xg"]] + stretch * (A["call"][r, k["xg"]] - lg[k["xg"]]) for r in (h, a))
        lam = {"xg": (max(th, FLOOR) * ratio * hf, max(ta, FLOOR) * ratio * af),
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


def calibration(P: np.ndarray, o: np.ndarray, min_n: int = 100):
    """Chances in bins against how often those outcomes happened; and the
    worst gap among bins with at least `min_n` predictions."""
    hit = np.zeros_like(P)
    hit[np.arange(len(o)), o] = 1.0
    cal = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        sel = (P >= lo) & (P < hi)
        if sel.any():
            cal.append({"from": lo, "to": min(hi, 1.0), "n": int(sel.sum()),
                        "predicted": float(P[sel].mean()), "happened": float(hit[sel].mean())})
    worst = float(max((abs(c["predicted"] - c["happened"]) for c in cal if c["n"] >= min_n), default=float("nan")))
    return cal, worst


def scored_rps(seasons: list[dict]):
    """(RPS per scored match, chances, outcomes) for the xG-fed call, in a fixed order."""
    ms = [m for s in seasons for _, m in sorted(s["matches"].items()) if m["scored"]]
    o = np.array([m["outcome"] for m in ms], dtype=int)
    P = np.array([m["p"]["xg"] for m in ms]).reshape(len(ms), 3)
    return np.array([rps(p, y) for p, y in zip(P, o)]), P, o


def compare(plain: list[dict], stretched: list[dict], n_boot: int = 500, seed: int = 0) -> dict:
    """The same matches scored with and without the stretch."""
    r0, P0, o = scored_rps(plain)
    r1, P1, _ = scored_rps(stretched)
    gain = r0 - r1
    draws = np.random.default_rng(seed).integers(0, len(o), (n_boot, len(o)))
    b = gain[draws].mean(1)
    cal0, worst0 = calibration(P0, o)
    cal1, worst1 = calibration(P1, o)
    return {"n": int(len(o)), "rps_plain": float(r0.mean()), "rps_stretched": float(r1.mean()),
            "gain": float(gain.mean()), "gain_ci": [float(np.percentile(b, 5)), float(np.percentile(b, 95))],
            "calibration_plain": cal0, "worst_gap_plain": worst0,
            "calibration_stretched": cal1, "worst_gap_stretched": worst1}


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
    res["calibration"], res["calibration_worst_gap"] = calibration(P["xg"], o)
    res["result_call_holds"] = bool(res["models"]["xg"]["gain_ci"][0] > 0)
    return res


def for_team(m: dict | None, home: bool) -> dict | None:
    """One match's calls seen from one side: [for, against] and [win, draw, loss]."""
    if m is None:
        return None
    side = (lambda v: [v[0], v[1]]) if home else (lambda v: [v[1], v[0]])
    flip = (lambda p: list(p)) if home else (lambda p: list(p)[::-1])
    p, base = np.array(flip(m["p"]["xg"])), np.array(flip(m["p"]["base"]))
    result = m["outcome"] if home else 2 - m["outcome"]
    return {"expected_goals": side(m["lam"]["xg"]), "threat_call": side(m["threat"]), "threat_actual": side(m["xg"]),
            "threat_league": m["threat_league"], "chances": p.tolist(), "base": base.tolist(), "result": int(result),
            "rps": rps(p, result), "rps_base": rps(base, result),
            "expected_points": float(3 * p[0] + p[1]), "points": [3, 1, 0][result]}


def summarise_team(rows: list[dict]) -> dict | None:
    """A team's result and threat calls over its replayed games."""
    if not rows:
        return None
    out = {"n": len(rows), "rps": float(np.mean([r["rps"] for r in rows])),
           "rps_base": float(np.mean([r["rps_base"] for r in rows])),
           "top_pick_right": int(sum(int(np.argmax(r["chances"])) == r["result"] for r in rows)),
           "expected_points": float(sum(r["expected_points"] for r in rows)),
           "points": int(sum(r["points"] for r in rows)), "threat": {}}
    for i, who in enumerate(("we", "they")):
        a = np.array([r["threat_actual"][i] for r in rows])
        c = np.array([r["threat_call"][i] for r in rows])
        lg = np.array([r["threat_league"] for r in rows])
        sse0 = float(((lg - a) ** 2).sum())
        out["threat"][who] = {"closer_than_league": int((np.abs(c - a) < np.abs(lg - a)).sum()),
                              "skill": 1 - float(((c - a) ** 2).sum()) / sse0 if sse0 > 0 else None,
                              "called": float(c.sum()), "actual": float(a.sum())}
    return out
