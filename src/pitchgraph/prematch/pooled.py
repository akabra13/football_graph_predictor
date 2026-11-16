"""The replay's calls for every team-match in a season, computed in one pass.

Same arithmetic as `replay.asof_call`, vectorised over features and
matches: only matches on earlier dates are used for any call.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.prematch.audit import PSEUDO
from pitchgraph.prematch.lineups import overlap_weight

MIN_PRIOR = 5


def asof_arrays(table: pl.DataFrame, dates: dict, features: list[str], start_fraction: float = 0.5,
                xi: dict | None = None) -> dict:
    """Per row of `table`: actual, the full call, the team-only call and the
    league baseline for every feature (N x K arrays), plus `scored`: rows in
    the later part of the team's fixtures with at least MIN_PRIOR earlier matches.

    With `xi` (from `lineups.starters`), `call_xi` is the same call with each
    earlier match weighted by how many of today's starters started it."""
    mid = table["match_id"].to_numpy()
    team, opp = table["team_id"].to_numpy(), table["opp_id"].to_numpy()
    d = np.array([str(dates[int(m)]) for m in mid])
    V = table.select(features).to_numpy().astype(float)
    V = np.where(np.isfinite(V), V, np.nan)
    N, K = V.shape
    call, own_, league_, sd_ = (np.full((N, K), np.nan) for _ in range(4))
    n_prior = np.zeros(N, dtype=int)
    call_xi = np.full((N, K), np.nan) if xi is not None else None
    call_xin = np.full((N, K), np.nan) if xi is not None else None

    def weighted(rows: np.ndarray, w: np.ndarray, league: np.ndarray, rescale: bool = False) -> np.ndarray:
        if not rows.any():
            return league.copy()
        if rescale and w.sum() > 0:
            w = w * (len(w) / w.sum())       # same amount of data, different emphasis
        v, w = V[rows], w[:, None]
        ok = np.isfinite(v)
        return (np.where(ok, v * w, 0.0).sum(0) + PSEUDO * league) / ((ok * w).sum(0) + PSEUDO)

    def shrunk(rows: np.ndarray, league: np.ndarray) -> np.ndarray:
        if not rows.any():
            return league.copy()
        v = V[rows]
        return (np.nansum(v, 0) + PSEUDO * league) / (np.isfinite(v).sum(0) + PSEUDO)

    for dd in np.unique(d):
        prior = d < dd
        if not prior.any():
            continue
        with np.errstate(invalid="ignore"):
            cnt = np.isfinite(V[prior]).sum(0)
            league = np.where(cnt > 0, np.nansum(V[prior], 0) / np.maximum(cnt, 1), np.nan)
            sd = np.sqrt(np.where(cnt > 0, np.nansum((V[prior] - league) ** 2, 0) / np.maximum(cnt, 1), np.nan))
        for r in np.flatnonzero(d == dd):
            sd_[r] = sd
            mine = prior & (team == team[r])
            own = shrunk(mine, league)
            against = shrunk(prior & (opp == opp[r]), league)
            call[r], own_[r], league_[r] = own + against - league, own, league
            n_prior[r] = int(mine.sum())
            if xi is not None:
                theirs = prior & (opp == opp[r])
                me, them = xi.get((int(mid[r]), int(team[r]))), xi.get((int(mid[r]), int(opp[r])))
                w_me = np.array([overlap_weight(me, xi.get((int(m), int(team[r])))) for m in mid[mine]])
                w_them = np.array([overlap_weight(them, xi.get((int(m), int(opp[r])))) for m in mid[theirs]])
                call_xi[r] = weighted(mine, w_me, league) + weighted(theirs, w_them, league) - league
                call_xin[r] = (weighted(mine, w_me, league, True) + weighted(theirs, w_them, league, True)
                               - league)

    later = np.zeros(N, dtype=bool)
    for t in np.unique(team):
        idx = np.flatnonzero(team == t)
        order = idx[np.lexsort((mid[idx], d[idx]))]
        later[order[int(len(order) * start_fraction):]] = True
    return {"actual": V, "call": call, "own": own_, "league": league_, "league_sd": sd_, "match": mid,
            "team": team, "opp": opp, "call_xi": call_xi, "call_xin": call_xin,
            "scored": later & (n_prior >= MIN_PRIOR)}


def pooled_skill(parts: list[dict], k: int, n_boot: int = 500, seed: int = 0) -> dict:
    """Skill of the call and of the team-only call for feature column k, pooled
    over seasons, with 90% intervals by resampling matches."""
    a, c, o, lg, keys = [], [], [], [], []
    for i, p in enumerate(parts):
        s = p["scored"] & np.isfinite(p["actual"][:, k]) & np.isfinite(p["call"][:, k])
        a.append(p["actual"][s, k]); c.append(p["call"][s, k]); o.append(p["own"][s, k])
        lg.append(p["league"][s, k]); keys.append(np.array([f"{i}_{m}" for m in p["match"][s]]))
    a, c, o, lg, keys = (np.concatenate(v) for v in (a, c, o, lg, keys))
    if len(a) == 0:
        return {"n": 0}
    uniq, inv = np.unique(keys, return_inverse=True)
    e = {name: np.bincount(inv, weights=(pred - a) ** 2, minlength=len(uniq))
         for name, pred in (("call", c), ("own", o), ("league", lg))}

    def skills(w):
        s0 = (w * e["league"]).sum()
        if s0 <= 0:
            return np.nan, np.nan
        return 1 - (w * e["call"]).sum() / s0, 1 - (w * e["own"]).sum() / s0

    sc, so = skills(np.ones(len(uniq)))
    rng = np.random.default_rng(seed)
    boots = np.array([skills(np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq)).astype(float))
                      for _ in range(n_boot)])
    ci = lambda v: [float(np.nanpercentile(v, 5)), float(np.nanpercentile(v, 95))]
    call_ci = ci(boots[:, 0])
    return {"n": int(len(a)), "skill": float(sc), "skill_ci": call_ci, "holds": bool(call_ci[0] > 0),
            "skill_team_only": float(so), "opponent_adds": float(sc - so),
            "opponent_adds_ci": ci(boots[:, 0] - boots[:, 1]),
            "closer_than_league": float(np.mean(np.abs(c - a) < np.abs(lg - a)))}


def team_shares(parts: list[dict], cols: list[int], min_games: int = 8) -> list[float]:
    """Per team: the share of its scored calls (over `cols`) closer than the league baseline."""
    out = []
    for p in parts:
        for t in np.unique(p["team"]):
            rows = p["scored"] & (p["team"] == t)
            if rows.sum() < min_games:
                continue
            a, c, lg = p["actual"][rows][:, cols], p["call"][rows][:, cols], p["league"][rows][:, cols]
            ok = np.isfinite(a) & np.isfinite(c)
            if ok.any():
                out.append(float((np.abs(c - a) < np.abs(lg - a))[ok].mean()))
    return out


def premise_rows(p: dict, k: int, who: str, direction: int, threshold: float, reference: str = "league"):
    """For feature column k of one season's `asof_arrays`: per scored unit,
    whether a rule on that feature fires and whether its situation occurred.

    who = "we" reads the unit's own row; "they" reads the opponent's row of
    the same match (the opponent's call against this team).
    Returns (fired, held, match ids), over scored units with usable values.
    """
    idx = np.arange(len(p["match"]))
    if who == "they":
        where = {(int(m), int(t)): i for i, (m, t) in enumerate(zip(p["match"], p["team"]))}
        idx = np.array([where.get((int(m), int(o)), -1) for m, o in zip(p["match"], p["opp"])])
    ok = p["scored"] & (idx >= 0)
    src = np.where(idx >= 0, idx, 0)
    call, league, sd, actual = (p[name][src, k] for name in ("call", "league", "league_sd", "actual"))
    ref = league
    if reference == "usual":
        # a normal week for the unit's team: its own usual for its own numbers; for the
        # opponent's numbers, what opponents usually do against it (call - own + league)
        own = p["own"][src, k]
        ref = own if who == "we" else call - own + league
    ok &= np.isfinite(call) & np.isfinite(league) & np.isfinite(actual) & np.isfinite(sd) & (sd > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        fired = direction * (call - ref) / sd >= threshold
        held = direction * (actual - ref) > 0
    return fired[ok], held[ok], p["match"][ok]


def skill_difference(parts: list[dict], k: int, n_boot: int = 500, seed: int = 0,
                     key: str = "call_xi") -> dict:
    """Skill of the line-up-weighted call minus skill of the plain call for
    feature column k, on the same units, with a 90% interval by resampling matches."""
    a, c, x, lg, keys = [], [], [], [], []
    for i, p in enumerate(parts):
        s_ = (p["scored"] & np.isfinite(p["actual"][:, k]) & np.isfinite(p["call"][:, k])
              & np.isfinite(p[key][:, k]))
        a.append(p["actual"][s_, k]); c.append(p["call"][s_, k]); x.append(p[key][s_, k])
        lg.append(p["league"][s_, k]); keys.append(np.array([f"{i}_{m}" for m in p["match"][s_]]))
    a, c, x, lg, keys = (np.concatenate(v) for v in (a, c, x, lg, keys))
    uniq, inv = np.unique(keys, return_inverse=True)
    e = {n: np.bincount(inv, weights=(pred - a) ** 2, minlength=len(uniq))
         for n, pred in (("plain", c), ("xi", x), ("league", lg))}

    def both(w):
        s0 = (w * e["league"]).sum()
        return 1 - (w * e["plain"]).sum() / s0, 1 - (w * e["xi"]).sum() / s0

    plain, with_xi = both(np.ones(len(uniq)))
    rng = np.random.default_rng(seed)
    boots = np.array([both(np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq)).astype(float))
                      for _ in range(n_boot)])
    d = boots[:, 1] - boots[:, 0]
    lo, hi = float(np.percentile(d, 5)), float(np.percentile(d, 95))
    return {"n": int(len(a)), "skill_plain": float(plain), "skill_lineup": float(with_xi),
            "difference": float(with_xi - plain), "ci": [lo, hi], "helped": bool(lo > 0), "hurt": bool(hi < 0)}


def premise_test(parts: list[dict], feats: list[str], rules: list, threshold: float, min_fires: int = 100,
                 pass_share: float = 0.60, n_boot: int = 500, seed: int = 0, reference: str = "league") -> dict:
    """Per rule: how often it fires and how often its situation then occurred,
    with a 90% interval by resampling whole matches (docs/strategy.md)."""
    rng = np.random.default_rng(seed)
    out = {}
    for rule, who, feature, direction, _ in rules:
        fired, held, keys = [], [], []
        for i, p in enumerate(parts):
            f, h, m = premise_rows(p, feats.index(feature), who, direction, threshold, reference)
            fired.append(f); held.append(h); keys.append(np.array([f"{i}_{x}" for x in m]))
        fired, held, keys = (np.concatenate(v) for v in (fired, held, keys))
        n = int(fired.sum())
        o = {"who": who, "feature": feature, "direction": direction, "fires": n,
             "fire_rate": float(fired.mean()) if len(fired) else 0.0, "judged": bool(n >= min_fires), "holds": False}
        if n:
            uniq, inv = np.unique(keys, return_inverse=True)
            hit_m = np.bincount(inv, weights=(fired & held).astype(float), minlength=len(uniq))
            n_m = np.bincount(inv, weights=fired.astype(float), minlength=len(uniq))
            boots = []
            for _ in range(n_boot):
                w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
                if (w * n_m).sum() > 0:
                    boots.append((w * hit_m).sum() / (w * n_m).sum())
            share = float(held[fired].mean())
            lo, hi = float(np.percentile(boots, 5)), float(np.percentile(boots, 95))
            o.update(held_share=share, ci=[lo, hi],
                     not_fired_share=float(held[~fired].mean()) if (~fired).any() else None,
                     holds=bool(n >= min_fires and share >= pass_share and lo > 0.5))
        out[rule] = o
    return out
