"""Season replay: what would the pre-match plan have said, game by game?

For each match the plan uses only matches played strictly before its date:

  they attack   where the opponent's entries into the final third are
                expected, from the matchup model (their habits x what we
                concede). Tested: `chains/validate.py` (lanes shift with
                the opponent in four of five leagues).
  the lever     the half-space-to-centre pass in the final third, the one
                denial confirmed against real matches (docs/denial_test.md),
                with which side the opponent plays it on and through whom.
  we attack     where our own entries are expected against this opponent.
  our players   who in our squad has been defending the zone their lever
                runs through, and who carries our entries in the lane the
                matchup favours.

After the match each call is scored: the predicted lane shares against the
real ones (and against two simpler guesses: the opponent's own habits, and
the league average), plus how much of the lever the opponent got and how
their threat compared with what strength alone predicted.

A replay shows what the tool would have said. It cannot show what would
have happened had the team acted on it.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.chains import denial, matchup
from pitchgraph.chains.counts import CountStore
from pitchgraph.chains.denial_test import region_links
from pitchgraph.chains.team import Chain, league_chain, shrunk_chain
from pitchgraph.chains.validate import _crossing_lanes, _observed_lanes
from pitchgraph.graphs.routes import LANE_EDGES
from pitchgraph.prematch import lineups, strategy
from pitchgraph.prematch.audit import PSEUDO, season_table

KAPPA = 1000.0
MIN_PRIOR = 5                       # matches a team needs before a plan is made
LANE_LABELS = ["left flank", "left half-space", "centre", "right half-space", "right flank"]
LEVERS = {"left": (11, 12), "right": (13, 12)}     # half-space -> centre, final third
DEFENSIVE = ["Pressure", "Duel", "Interception", "Block", "Ball Recovery", "Clearance", "Foul Committed"]
LINE = 80.0
TURNOVERS = ["Dispossessed", "Miscontrol"]

# What the plan calls before the match: features that passed the predictability
# audit (docs/predictability_audit.md), each predicted from the team's earlier
# matches plus what earlier opponents did against this opponent.
CALLS = [
    ("possession", "Share of the ball", "{:.0%}"),
    ("turnover_rate", "Giveaways per action", "{:.1%}"),
    ("own_third_turnover_share", "Share of giveaways in own third", "{:.0%}"),
    ("central_entries_per_possession", "Entries into the central final third per possession", "{:.2f}"),
    ("shots_per_possession", "Shots per possession", "{:.3f}"),
    ("start_height", "Where possessions start (0 own goal, 120 theirs)", "{:.0f}"),
    ("long_forward_share", "Long forward moves", "{:.1%}"),
    ("reciprocity", "Back-and-forth passing (graph reciprocity)", "{:.0%}"),
    ("entropy_rate", "Unpredictability of the next move (bits)", "{:.2f}"),
]


def asof_call(table: pl.DataFrame, feature: str, team: int, opp: int, prior: set) -> dict | None:
    """Predicted value of `feature` for `team` against `opp`, from `prior` matches only:
    the team's own mean plus how far earlier opponents of `opp` were pushed from the league mean,
    each shrunk to the league with PSEUDO pseudo-matches."""
    t = table.filter(pl.col("match_id").is_in(list(prior))).filter(pl.col(feature).is_finite())
    if t.height == 0:
        return None
    league = float(t[feature].mean())
    league_sd = float(t[feature].std(ddof=0)) if t.height > 1 else 0.0

    def shrunk(rows):
        v = rows[feature]
        return (float(v.sum()) + PSEUDO * league) / (v.len() + PSEUDO)

    own = shrunk(t.filter(pl.col("team_id") == team))
    against = shrunk(t.filter(pl.col("opp_id") == opp))
    return {"predicted": own + against - league, "own": own, "league": league, "league_sd": league_sd}


def calls_for(table: pl.DataFrame, us: int, them: int, mid: int, prior: set) -> dict:
    """Every call for both sides, with the real value from the match."""
    out = {}
    for who, a, b in (("we", us, them), ("they", them, us)):
        row = table.filter((pl.col("match_id") == mid) & (pl.col("team_id") == a))
        out[who] = {}
        for feature, _, _ in CALLS:
            c = asof_call(table, feature, a, b, prior)
            if c is None:
                continue
            actual = float(row[feature][0]) if row.height else None
            if actual is not None and not np.isfinite(actual):
                actual = None
            c["actual"] = actual
            c["closer_than_league"] = (abs(c["predicted"] - actual) < abs(c["league"] - actual)
                                       if actual is not None else None)
            out[who][feature] = c
    return out


def mirror_lane(lane: int) -> int:
    """The same strip of grass seen from the other team (their left is our right)."""
    return 4 - lane


def mirror_region(r: int) -> int:
    third, lane = divmod(r, 5)
    return (2 - third) * 5 + (4 - lane)


def region_expr(x: pl.Expr, y: pl.Expr) -> pl.Expr:
    third = pl.min_horizontal((x / 40.0).floor().cast(pl.Int32), pl.lit(2))
    lane = pl.sum_horizontal([(y >= e).cast(pl.Int32) for e in LANE_EDGES])
    return third * 5 + lane


def tv(a: np.ndarray, b: np.ndarray) -> float:
    """Total variation distance between two share vectors (0 = identical)."""
    return float(0.5 * np.abs(np.asarray(a) - np.asarray(b)).sum())


def noise_floor(shares, n: int, draws: int = 400, seed: int = 0) -> float:
    """The distance a PERFECT prediction would still show after n entries:
    the mean total variation between `shares` and a sample of n drawn from it.
    One match has only a few dozen entries, so even the truth looks wrong by this much."""
    p = np.asarray(shares, float)
    if n <= 0:
        return float("nan")
    sample = np.random.default_rng(seed).multinomial(n, p / p.sum(), size=draws) / n
    return float(0.5 * np.abs(sample - p).sum(1).mean())


class AsOf:
    """Chains fitted on a chosen set of earlier matches."""

    def __init__(self, store: CountStore, kappa: float = KAPPA):
        self.store, self.kappa = store, kappa
        self.per_match = store.match_totals()

    def league(self, prior: set) -> Chain:
        n = self.store.n
        C, xg, st = np.zeros((n, n + 2)), np.zeros(n), np.zeros(n)
        for m in prior:
            if m in self.per_match:
                c, x, s = self.per_match[m]
                C, xg, st = C + c, xg + x, st + s
        return league_chain(C, xg, st, self.store.grid)

    def keep(self, tid: int, side: str, prior: set) -> np.ndarray:
        return np.isin(self.store.team(tid, side).match_ids, list(prior))

    def team(self, tid: int, side: str, prior: set, league: Chain) -> Chain | None:
        keep = self.keep(tid, side, prior)
        if keep.sum() < MIN_PRIOR:
            return None
        return shrunk_chain(*self.store.team(tid, side).total(keep), league, self.kappa)

    def rate(self, tid: int, side: str, prior: set) -> float:
        tc = self.store.team(tid, side)
        keep = self.keep(tid, side, prior)
        return float(tc.xg[keep].sum() / max(tc.starts[keep].sum(), 1.0))


def _mid(chain: Chain, mask: np.ndarray) -> float:
    base = chain.threat
    return float(0.5 * ((base - denial.deny(chain, mask, True).threat)
                        + (base - denial.deny(chain, mask, False).threat)) / base)


def _top(df: pl.DataFrame, col: str, names: dict, k: int = 3, starting: frozenset | None = None) -> list[dict]:
    """The k players who did this most. With `starting` (today's XI), only
    starters are named; shares stay relative to everyone, so they show how
    much of the job the named players have actually carried."""
    if df.height == 0:
        return []
    g = (df.filter(pl.col(col).is_not_null()).group_by(col)
           .agg(n=pl.len(), fallback=pl.first("player")).sort(["n", col], descending=[True, False]))
    total = float(g["n"].sum())
    rows = [{"player_id": int(r[col]), "name": names.get(r[col]) or r["fallback"] or str(r[col]),
             "share": r["n"] / total} for r in g.iter_rows(named=True)]
    if starting:
        rows = [r for r in rows if r["player_id"] in starting]
    return rows[:k]


def player_links(ev: pl.DataFrame, prior: set, us: int, them: int, side: str, lane_we: int,
                 names: dict, xi_us: frozenset | None = None, xi_them: frozenset | None = None) -> dict:
    """Who is involved, from earlier matches only.

    their_passers / their_receivers  the opponent's players on their lever
    our_defenders                    our players' defensive actions in that zone
    our_carriers                     our players taking the ball across x = 80 in `lane_we`
    """
    a, b = LEVERS[side]
    prev = ev.filter(pl.col("match_id").is_in(list(prior)))
    reg0 = region_expr(pl.col("x"), pl.col("y"))
    reg1 = region_expr(pl.col("end_x"), pl.col("end_y"))
    done_pass = (pl.col("type") == "Pass") & pl.col("outcome").is_null() & pl.col("end_x").is_not_null()

    theirs = prev.filter((pl.col("team_id") == them) & done_pass & (reg0 == a) & (reg1 == b))
    recv = theirs.filter(pl.col("recipient_id").is_not_null()).with_columns(
        player=pl.lit(None, dtype=pl.Utf8))
    zone = [mirror_region(a), mirror_region(b)]
    ours_def = prev.filter((pl.col("team_id") == us) & pl.col("type").is_in(DEFENSIVE)
                           & pl.col("x").is_not_null() & reg0.is_in(zone))
    moves = prev.filter((pl.col("team_id") == us) & (done_pass | (pl.col("type") == "Carry"))
                        & pl.col("end_x").is_not_null() & (pl.col("x") < LINE) & (pl.col("end_x") >= LINE))
    t = (LINE - pl.col("x")) / (pl.col("end_x") - pl.col("x") + 1e-9)
    y_at = pl.col("y") + t * (pl.col("end_y") - pl.col("y"))
    cross_lane = pl.sum_horizontal([(y_at >= e).cast(pl.Int32) for e in LANE_EDGES])
    ours_att = moves.filter(cross_lane == lane_we) if lane_we is not None else moves
    failed_pass = (pl.col("type") == "Pass") & pl.col("outcome").is_not_null()
    their_losses = prev.filter((pl.col("team_id") == them) & (failed_pass | pl.col("type").is_in(TURNOVERS))
                               & pl.col("x").is_not_null() & (pl.col("x") < 40))
    our_press = prev.filter((pl.col("team_id") == us) & (pl.col("type") == "Pressure")
                            & pl.col("x").is_not_null() & (pl.col("x") >= 80))
    return {"their_giveaways": _top(their_losses, "player_id", names, 3, xi_them),
            "our_pressers": _top(our_press, "player_id", names, 3, xi_us),
            "their_passers": _top(theirs, "player_id", names, 2, xi_them),
            "their_receivers": _top(recv, "recipient_id", names, 2, xi_them),
            "our_defenders": _top(ours_def, "player_id", names, 3, xi_us),
            "our_carriers": _top(ours_att, "player_id", names, 3, xi_us)}


def plan(asof: AsOf, ev: pl.DataFrame, us: int, them: int, prior: set, names: dict,
         xi: dict | None = None, mid: int | None = None) -> dict | None:
    """The pre-match plan for `us` against `them`, from `prior` matches only."""
    league = asof.league(prior)
    chains = {k: asof.team(t, s, prior, league) for k, (t, s) in
              {"them_att": (them, "attack"), "us_con": (us, "conceded"),
               "us_att": (us, "attack"), "them_con": (them, "conceded")}.items()}
    if any(c is None for c in chains.values()):
        return None
    lanes = matchup.entry_lanes
    they = {"matchup": lanes(matchup.matchup_chain(chains["them_att"], chains["us_con"], league)),
            "own": lanes(chains["them_att"]), "league": lanes(league)}
    we = {"matchup": lanes(matchup.matchup_chain(chains["us_att"], chains["them_con"], league)),
          "own": lanes(chains["us_att"]), "league": lanes(league)}

    regions = denial.zone_regions(asof.store.grid)
    n = asof.store.n
    usage = region_links(asof.store.team(them, "attack").total(asof.keep(them, "attack", prior))[0][:, :n],
                         regions)
    usage = usage / max(usage.sum(), 1.0)
    lever = {}
    for side, (a, b) in LEVERS.items():
        mask = denial.link_mask(regions, a, b)
        lever[side] = {"share": float(usage[a, b]), "team_value": _mid(chains["them_att"], mask),
                       "league_value": _mid(league, mask)}
    side = max(lever, key=lambda s: lever[s]["share"])
    lane_we = int(np.argmax(we["matchup"] - we["own"]))       # where this opponent pulls our attack
    return {"they_attack": {k: v.tolist() for k, v in they.items()},
            "we_attack": {k: v.tolist() for k, v in we.items()},
            "lever": lever, "lever_side": side, "lane_we": lane_we,
            "players": player_links(ev, prior, us, them, side, None, names,
                                    (xi or {}).get((mid, us)), (xi or {}).get((mid, them))),
            "lineup": None if not xi else {
                "known": bool((mid, us) in xi and (mid, them) in xi),
                "us_missing": lineups.missing_regulars(xi, us, mid, prior, names),
                "them_missing": lineups.missing_regulars(xi, them, mid, prior, names)},
            "prior_matches": {"us": int(asof.keep(us, "attack", prior).sum()),
                              "them": int(asof.keep(them, "attack", prior).sum())}}


def outcome(asof: AsOf, us: int, them: int, mid: int, prior: set, the_plan: dict) -> dict:
    """What happened in the match, and how each call scored."""
    store = asof.store
    n = store.n
    crossing, lane = _crossing_lanes(store.grid)
    regions = denial.zone_regions(store.grid)
    out = {}
    for who, tid, key in (("they", them, "they_attack"), ("we", us, "we_attack")):
        tc = store.team(tid, "attack")
        k = int(np.where(tc.match_ids == mid)[0][0])
        counts = _observed_lanes(tc.C[k].astype(float), n, crossing, lane)
        actual = counts / max(counts.sum(), 1.0)
        calls = the_plan[key]
        out[who] = {"entries": float(counts.sum()), "actual": actual.tolist(),
                    "tv": {m: tv(calls[m], actual) for m in calls},
                    "floor": noise_floor(calls["matchup"], int(counts.sum())),
                    "top_hit": {m: bool(int(np.argmax(calls[m])) == int(np.argmax(actual))) for m in calls}}

    tc = store.team(them, "attack")
    k = int(np.where(tc.match_ids == mid)[0][0])
    poss = float(tc.starts[k].sum())
    league_prior = asof.league(prior)
    league_rate = 0.0
    C_all = [asof.per_match[m] for m in prior if m in asof.per_match]
    if C_all:
        league_rate = sum(x.sum() for _, x, _ in C_all) / max(sum(s.sum() for _, _, s in C_all), 1.0)
    expected = asof.rate(them, "attack", prior) * asof.rate(us, "conceded", prior) / league_rate \
        if league_rate > 0 else 0.0
    now = region_links(tc.C[k][:, :n].astype(float), regions)
    now = now / max(now.sum(), 1.0)
    a, b = LEVERS[the_plan["lever_side"]]
    usual = the_plan["lever"][the_plan["lever_side"]]["share"]
    out["lever"] = {"share": float(now[a, b]), "usual": usual,
                    "vs_usual": float(now[a, b] / usual - 1.0) if usual > 0 else None}
    out["their_threat"] = {"xg_per_possession": float(tc.xg[k].sum()) / max(poss, 1.0),
                           "expected": float(expected),
                           "vs_expected": float(tc.xg[k].sum() / max(poss, 1.0) / expected - 1.0)
                           if expected > 0 else None, "xg": float(tc.xg[k].sum())}
    del league_prior
    return out


def replay(ev: pl.DataFrame, matches: pl.DataFrame, team_id: int, names: dict | None = None,
           start_fraction: float = 0.5, kappa: float = KAPPA, min_matches: int = 10,
           lineup_table: pl.DataFrame | None = None) -> dict:
    """Walk `team_id` through the later part of its season.

    `ev` is one competition-season of `Lake.events()`; `matches` its rows of
    the matches table. Plans start at the match `start_fraction` of the way
    through the team's fixtures by date.
    """
    names = names or {}
    xi = lineups.starters(lineup_table) if lineup_table is not None else None
    if lineup_table is not None and "player" in lineup_table.columns:
        full = dict(zip(lineup_table["player_id"].to_list(), lineup_table["player"].to_list()))
        names = {**full, **{k: v for k, v in names.items() if v}}      # nickname where there is one
    store = CountStore.from_events(ev.lazy())
    asof = AsOf(store, kappa)
    ftable = season_table(store, min_matches=min_matches)
    info ={r["match_id"]: r for r in matches.iter_rows(named=True)}
    dates = {m: str(r["match_date"]) for m, r in info.items()}
    mine = sorted((m for m, r in info.items() if team_id in (r["home_team_id"], r["away_team_id"])),
                  key=lambda m: (dates[m], m))
    games = []
    for mid in mine[int(len(mine) * start_fraction):]:
        r = info[mid]
        home = r["home_team_id"] == team_id
        them = r["away_team_id"] if home else r["home_team_id"]
        prior = {m for m, d in dates.items() if d < dates[mid]}
        p = plan(asof, ev, team_id, them, prior, names, xi, int(mid))
        game = {"match_id": int(mid), "date": dates[mid], "home": bool(home),
                "opponent": r["away_team"] if home else r["home_team"], "opponent_id": int(them),
                "score": [r["home_score"], r["away_score"]] if home else [r["away_score"], r["home_score"]],
                "plan": p}
        if p is not None and mid in asof.per_match:
            game["outcome"] = outcome(asof, team_id, them, mid, prior, p)
            game["calls"] = calls_for(ftable, team_id, them, mid, prior)
            game["strategy"] = strategy.lines(game["calls"], p["players"], game["opponent"],
                                              {f: fmt for f, _, fmt in CALLS})
        games.append(game)
    return {"team_id": int(team_id), "games": games, "summary": summarise(games)}


def summarise(games: list[dict]) -> dict:
    """Lane calls over all games: how often each guess named the busiest lane,
    and how far its shares were from the real ones (lower is better)."""
    done = [g for g in games if g.get("outcome")]
    out = {"games": len(done), "calls": {}}
    closer = total = 0
    for who in ("we", "they"):
        out["calls"][who] = {}
        for feature, _, _ in CALLS:
            rows = [g["calls"][who][feature] for g in done
                    if g.get("calls") and feature in g["calls"][who]
                    and g["calls"][who][feature]["actual"] is not None]
            if not rows:
                continue
            a = np.array([r["actual"] for r in rows])
            sse = float(((np.array([r["predicted"] for r in rows]) - a) ** 2).sum())
            sse0 = float(((np.array([r["league"] for r in rows]) - a) ** 2).sum())
            hits = int(sum(r["closer_than_league"] for r in rows))
            closer, total = closer + hits, total + len(rows)
            out["calls"][who][feature] = {"n": len(rows), "closer_than_league": hits,
                                          "skill": 1 - sse / sse0 if sse0 > 0 else None}
    out["calls_closer"], out["calls_total"] = closer, total
    fired = [s for g in done for s in g.get("strategy", []) if s["premise_held"] is not None]
    out["strategy_lines"] = len(fired)
    out["strategy_premises_held"] = int(sum(s["premise_held"] for s in fired))
    by_rule = {}
    for s in fired:
        r = by_rule.setdefault(s["rule"], [0, 0])
        r[0] += int(s["premise_held"])
        r[1] += 1
    out["strategy_by_rule"] = by_rule
    for who in ("they", "we"):
        rows = [g["outcome"][who] for g in done]
        out[who] = {m: {"top_lane_hits": int(sum(r["top_hit"][m] for r in rows)),
                        "mean_tv": float(np.mean([r["tv"][m] for r in rows])) if rows else None}
                    for m in ("matchup", "own", "league")}
        out[who]["matchup_beats_own"] = int(sum(r["tv"]["matchup"] < r["tv"]["own"] for r in rows))
        out[who]["floor"] = float(np.nanmean([r["floor"] for r in rows])) if rows else None
    pairs = [(g["outcome"]["lever"]["vs_usual"], g["outcome"]["their_threat"]["vs_expected"]) for g in done]
    pairs = [(u, y) for u, y in pairs if u is not None and y is not None]
    if len(pairs) >= 4:
        u, y = np.array(pairs).T
        low = u < np.median(u)
        if u.std() > 0 and y.std() > 0 and low.any() and (~low).any():
            out["lever_vs_threat_r"] = float(np.corrcoef(u, y)[0, 1])
            out["threat_when_lever_low"] = float(y[low].mean())
            out["threat_when_lever_high"] = float(y[~low].mean())
    return out
