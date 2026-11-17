"""The frozen version scored on data released after it was frozen.

Design, bars and reading rules: docs/blind_test.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pitchgraph.prematch.pooled import premise_rows

FROZEN = Path(__file__).resolve().parents[3] / "docs" / "frozen_seasons.json"
MIN_TEAMS, MIN_MATCHES = 8, 10          # the pooled replay's rule for a usable competition-season
MIN_UNITS = 300                         # scored team-matches needed before any verdict
PASS_SHARE = 0.60


def frozen_keys(path: Path = FROZEN) -> set[str]:
    return set(json.loads(path.read_text(encoding="utf-8"))["seasons"])


def new_keys(live: list[dict], frozen: set[str]) -> list[str]:
    """Competition-season keys in the live competitions list that the frozen version never saw."""
    keys = {f"{c['competition_id']}_{c['season_id']}" for c in live}
    return sorted(keys - frozen)


def usable(matches: list[dict]) -> bool:
    """At least MIN_TEAMS teams with MIN_MATCHES matches, from StatsBomb's raw match list."""
    n: dict[int, int] = {}
    for m in matches:
        for side in ("home", "away"):
            t = m[f"{side}_team"][f"{side}_team_id"]
            n[t] = n.get(t, 0) + 1
    return sum(v >= MIN_MATCHES for v in n.values()) >= MIN_TEAMS


def pooled_premises(parts: list[dict], feats: list[str], rules: list, threshold: float, n_boot: int = 500,
                    seed: int = 0) -> dict:
    """Over every instruction issued by any rule: the share whose situation
    occurred, with a 90% interval by resampling whole matches."""
    hit, n, keys = [], [], []
    for _, who, feature, direction, _ in rules:
        for i, p in enumerate(parts):
            f, h, m = premise_rows(p, feats.index(feature), who, direction, threshold, "usual")
            hit.append((f & h).astype(float)); n.append(f.astype(float))
            keys.append(np.array([f"{i}_{x}" for x in m]))
    if not keys or sum(len(k) for k in keys) == 0:
        return {"issued": 0}
    hit, n, keys = (np.concatenate(v) for v in (hit, n, keys))
    if n.sum() == 0:
        return {"issued": 0}
    uniq, inv = np.unique(keys, return_inverse=True)
    hit_m = np.bincount(inv, weights=hit, minlength=len(uniq))
    n_m = np.bincount(inv, weights=n, minlength=len(uniq))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
        if (w * n_m).sum() > 0:
            boots.append((w * hit_m).sum() / (w * n_m).sum())
    lo, hi = float(np.percentile(boots, 5)), float(np.percentile(boots, 95))
    share = float(hit.sum() / n.sum())
    return {"issued": int(n.sum()), "occurred_share": share, "ci": [lo, hi],
            "holds": bool(share >= PASS_SHARE and lo > 0.5)}


def verdict(threat: dict, result: dict, instructions: dict) -> dict:
    """The three registered claims, judged only once there is enough unseen data."""
    units = int(threat.get("n", 0))
    if units < MIN_UNITS:
        return {"units": units, "judged": False, "reading": f"too small to judge (needs {MIN_UNITS} team-matches)"}
    claims = {"threat_call": bool(threat.get("holds")), "result_call": bool(result.get("result_call_holds")),
              "instructions": bool(instructions.get("holds"))}
    return {"units": units, "judged": True, "claims": claims,
            "reading": "all three hold on unseen data" if all(claims.values())
            else "failed on unseen data: " + ", ".join(k for k, v in claims.items() if not v)}
