"""One competition-season, analysed once, ready to answer any team's questions.

A Season holds the ledger (every claim as per-match sums), each team's attacking
and conceded flow graphs, the league chain they are shrunk toward, and the
player actions. Everything the Library shows for a team or a matchup comes from
here; nothing re-reads the raw events per question except the few descriptive
sections that need them.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pitchgraph.analysis import sections, stats
from pitchgraph.analysis.reliability import estimate_ratio, split_half_agreement
from pitchgraph.chains import denial, fingerprint, matchup, players
from pitchgraph.chains.counts import CountStore
from pitchgraph.chains.grid import TACTICAL, Grid
from pitchgraph.chains.team import league_chain, select_kappa, team_chain

MIN_MATCHES = 5          # a team needs this many matches to get a page
SMALL_SAMPLE = 10        # below this the page carries a prominent warning
DEFAULT_KAPPA = 1000.0   # chosen by held-out likelihood in all four test leagues
HEADLINES = 5

REGION_CENTRE_Y = [9.0, 24.0, 40.0, 56.0, 71.0]
REGION_CENTRE_X = [20.0, 60.0, 100.0]


def _r(x, digits=4):
    """Round for compact JSON; NaN becomes None."""
    if x is None:
        return None
    x = float(x)
    return None if not np.isfinite(x) else round(x, digits)


class Season:
    def __init__(self, ev: pl.DataFrame, meta: dict, names: dict | None = None,
                 lineups: pl.DataFrame | None = None, grid: Grid = TACTICAL):
        self.ev, self.meta, self.grid = ev, meta, grid
        self.names = names or {}
        self.lineups = lineups
        self.teams = dict(ev.select("team_id", "team").unique().drop_nulls().iter_rows())

        self.ledger = stats.ledger(ev)
        n_matches = dict(self.ledger.group_by("team_id").len().iter_rows())
        self.eligible = sorted(t for t in self.teams if n_matches.get(t, 0) >= MIN_MATCHES)
        self.n_matches = n_matches
        self.values = stats.team_values(self.ledger).filter(pl.col("team_id").is_in(self.eligible))

        self.counts = CountStore.from_events(ev.lazy(), grid)
        C, xg, st = self.counts.league_total()
        self.league = league_chain(C, xg, st, grid)
        fit = [self.counts.team(t) for t in self.eligible if self.counts.team(t).n_matches >= 3]
        self.kappa = select_kappa(fit, self.league)[0] if len(fit) >= 4 else DEFAULT_KAPPA
        self.attack = {t: team_chain(self.counts.team(t, "attack"), self.league, self.kappa)
                       for t in self.eligible}
        self.conceded = {t: team_chain(self.counts.team(t, "conceded"), self.league, self.kappa)
                         for t in self.eligible}

        self.player_actions = players.player_actions(ev.lazy())
        self.baselines = sections.league_baselines(ev, self.eligible)
        self.opp_adjust = self._opponent_adjustment()

    def display(self, player_id, fallback=None) -> str:
        return sections.clean(self.names.get(player_id) or fallback)

    # -- claims -------------------------------------------------------------
    def claims(self, tid: int) -> list[dict]:
        rows = self.ledger.filter(pl.col("team_id") == tid).sort("match_id")
        out = []
        for s in stats.STATS:
            col = self.values[s.key].drop_nans().drop_nulls()
            league = float(col.median())
            e = estimate_ratio(rows[s.num].to_numpy(), rows[s.den].to_numpy(), league)
            rank = 1 + int((col > e.value).sum())
            of = len(col)
            out.append({
                "key": s.key, "section": s.section, "label": s.label, "fmt": s.fmt,
                "value": _r(e.value), "lo": _r(e.lo), "hi": _r(e.hi), "league": _r(league),
                "halves": [_r(h) for h in e.halves], "confidence": e.confidence,
                "rank": rank, "of": of,
                "word": s.higher if e.value > league else s.lower,
                "sentence": s.sentence.format(v=s.fmt.format(e.value),
                                              rank=sections.rank_words(rank, of)),
                "_est": e,
            })
        return out

    # -- flow graph views -----------------------------------------------------
    def _region_flow(self, chain) -> np.ndarray:
        """Expected moves per possession between the 15 regions (thirds x lanes)."""
        regions = denial.zone_regions(self.grid)
        F = chain.visits()[:, None] * chain.move
        R = np.zeros((15, 15))
        np.add.at(R, (regions[:, None].repeat(self.grid.n, 1), regions[None, :].repeat(self.grid.n, 0)), F)
        return R

    def flow_section(self, tid: int, top: int = 10) -> list[dict]:
        """Their strongest region-to-region links, and how each compares with the league."""
        R, L = self._region_flow(self.attack[tid]), self._region_flow(self.league)
        np.fill_diagonal(R, 0.0)
        out = []
        for a, b in zip(*np.unravel_index(np.argsort(-R, axis=None)[:top], R.shape)):
            out.append({"from": int(a), "to": int(b), "from_label": denial.region_name(int(a)),
                        "to_label": denial.region_name(int(b)), "flow": _r(R[a, b]),
                        "vs_league": _r(R[a, b] / L[a, b] if L[a, b] > 0 else None)})
        return out

    def denial_section(self, tid: int) -> dict:
        usage = self.counts.team(tid, "attack").total()[0][:, : self.grid.n]
        plan = denial.plan(self.attack[tid], usage, reference=self.league)
        return {k: ([{kk: (_r(vv) if isinstance(vv, float) else vv) for kk, vv in row.items()}
                     for row in v] if isinstance(v, list) else _r(v)) for k, v in plan.items()}

    def defence_section(self, tid: int) -> dict:
        """The same planner on what opponents do against them: which opponent
        routes their conceded threat depends on - the places to protect."""
        usage = self.counts.team(tid, "conceded").total()[0][:, : self.grid.n]
        plan = denial.plan(self.conceded[tid], usage, reference=self.league)
        R, L = self._region_flow(self.conceded[tid]), self._region_flow(self.league)
        np.fill_diagonal(R, 0.0)
        leak = np.divide(R, L, out=np.ones_like(R), where=L > 1e-4)
        order = np.argsort(-(R - L), axis=None)[:5]
        leaks = [{"from_label": denial.region_name(int(a)), "to_label": denial.region_name(int(b)),
                  "flow": _r(R[a, b]), "vs_league": _r(leak[a, b])}
                 for a, b in zip(*np.unravel_index(order, R.shape))]
        clean = lambda rows: [{kk: (_r(vv) if isinstance(vv, float) else vv) for kk, vv in row.items()}
                              for row in rows]
        return {"protect": clean(plan["links"]), "unusual": clean(plan.get("unusual_links", [])),
                "leaks": leaks}

    # -- players ----------------------------------------------------------------
    def player_section(self, tid: int, sub: pl.DataFrame) -> dict:
        base = sections.players_section(sub, tid, self.display)
        chain = players.build(self.player_actions, tid)
        effects = {r["player_id"]: r for r in players.removal_effects(chain, top=len(chain.players))}
        for node in base["nodes"]:
            e = effects.get(node["id"])
            node["removal"] = [_r(e["drop_adapt"]), _r(e["drop_no_adapt"])] if e else None
        return base

    # -- style ----------------------------------------------------------------
    def style(self) -> dict:
        ids = self.eligible
        if len(ids) < 3:
            return {"coords": {}, "neighbours": {}}
        D = fingerprint.distance_matrix([self.attack[t] for t in ids])
        xy = fingerprint.mds(D)
        nb = {}
        for i, t in enumerate(ids):
            order = [j for j in np.argsort(D[i]) if j != i][:3]
            nb[t] = [{"team_id": ids[j], "name": self.teams[ids[j]], "distance": _r(D[i, j])} for j in order]
        return {"coords": {t: [_r(xy[i, 0]), _r(xy[i, 1])] for i, t in enumerate(ids)}, "neighbours": nb}

    # -- matchups -------------------------------------------------------------
    def matchup(self, a: int, b: int) -> dict:
        A, B = self.attack[a], self.conceded[b]
        M = matchup.matchup_chain(A, B, self.league)
        RA, RM = self._region_flow(A), self._region_flow(M)
        diff = RM - RA
        np.fill_diagonal(diff, 0.0)

        def links(order):
            return [{"from_label": denial.region_name(int(x)), "to_label": denial.region_name(int(y)),
                     "change": _r(diff[x, y] / RA[x, y] if RA[x, y] > 0 else None)}
                    for x, y in zip(*np.unravel_index(order, diff.shape))]

        return {
            "lanes_own": [_r(v) for v in matchup.entry_lanes(A)],
            "lanes_matchup": [_r(v) for v in matchup.entry_lanes(M)],
            # Validated: threat VOLUME follows strength (A's level x how much B
            # concedes), not the edge-by-edge matchup, so that is what is shown.
            "threat_vs_usual": _r(B.threat / self.league.threat - 1),
            "more_of": links(np.argsort(-diff, axis=None)[:3]),
            "less_of": links(np.argsort(diff, axis=None)[:3]),
            "head_to_head": self._head_to_head(a, b),
        }

    def _head_to_head(self, a: int, b: int) -> list[dict]:
        ms = (self.ev.filter(pl.col("team_id").is_in([a, b]))
                     .group_by("match_id").agg(pl.col("team_id").n_unique().alias("k"),
                                               pl.first("match_date"))
                     .filter(pl.col("k") == 2).sort("match_date"))
        out = []
        for mid, date in ms.select("match_id", "match_date").iter_rows():
            m = self.ev.filter(pl.col("match_id") == mid)
            goal = (((pl.col("type") == "Shot") & (pl.col("outcome").fill_null("") == "Goal"))
                    | (pl.col("type") == "Own Goal For"))
            goals = dict(m.filter(goal).group_by("team_id").len().iter_rows())
            xg = dict(m.filter(pl.col("type") == "Shot").group_by("team_id")
                       .agg(pl.col("xg").fill_null(0.0).sum()).iter_rows())
            out.append({"date": date, "score": [goals.get(a, 0), goals.get(b, 0)],
                        "xg": [_r(xg.get(a, 0.0), 2), _r(xg.get(b, 0.0), 2)]})
        return out

    # -- opponent adjustment ------------------------------------------------------
    def _opponent_adjustment(self) -> dict:
        """Mean over matches of (opponent's threat vs this team) minus (that
        opponent's threat in its OTHER matches). Negative = held opponents
        below their usual level."""
        per = self.ledger.select("match_id", "team_id", "threat")
        tot = per.group_by("team_id").agg(s=pl.col("threat").sum(), n=pl.len())
        per = per.join(tot, on="team_id").with_columns(
            usual=pl.when(pl.col("n") > 1).then((pl.col("s") - pl.col("threat")) / (pl.col("n") - 1)))
        opp = self.ledger.select("match_id", "team_id", "opp_id")
        joined = opp.join(per.select("match_id", pl.col("team_id").alias("opp_id"), "threat", "usual"),
                          on=["match_id", "opp_id"])
        out = {}
        for t, rows in joined.group_by("team_id"):
            d = (rows["threat"] - rows["usual"]).drop_nulls()
            out[t[0]] = (_r(d.mean()) if len(d) else None, len(d))
        return out

    # -- everything for one team -------------------------------------------------
    def team_page(self, tid: int) -> dict:
        sub = sections.team_matches(self.ev, tid)
        claims = self.claims(tid)
        ests = [c.pop("_est") for c in claims]
        strong = [c for c in claims if c["confidence"] == "High" and c["value"] is not None]
        headlines = sorted(strong, key=lambda c: -abs(c["rank"] - (c["of"] + 1) / 2))[:HEADLINES]
        labels = sections.match_labels(sub, self.teams, tid)
        adj, n_adj = self.opp_adjust.get(tid, (None, 0))
        return {
            "id": tid, "name": self.teams[tid], "matches": self.n_matches[tid],
            "small_sample": self.n_matches[tid] < SMALL_SAMPLE,
            "has_360": bool(sub.filter(pl.col("team_id") == tid)["has_360"].any()),
            "agreement": _r(split_half_agreement(ests)),
            "headlines": [c["key"] for c in headlines],
            "claims": claims,
            "threat_per_possession": _r(self.attack[tid].threat),
            "flow": self.flow_section(tid),
            "denial": self.denial_section(tid),
            "defence": self.defence_section(tid),
            "routes": sections.routes_section(sub, tid),
            "players": self.player_section(tid, sub),
            "pressing": sections.pressing_section(sub, tid, self.display, self.baselines["pressed"]),
            "exposure": sections.exposure_section(sub, tid, labels, self.display,
                                                  self.baselines["lanes"], self.baselines["states"]),
            "opp_adjusted": {"value": adj, "matches": n_adj},
        }

    def to_json(self, with_matchups: bool = True) -> dict:
        style = self.style()
        teams = {}
        for t in self.eligible:
            page = self.team_page(t)
            page["similar"] = style["neighbours"].get(t, [])
            page["style_xy"] = style["coords"].get(t)
            teams[str(t)] = page
        out = {**self.meta, "kappa": self.kappa, "grid": {"x": list(self.grid.x_edges),
                                                          "y": list(self.grid.y_edges)},
               "lane_names": [sections.OWN[k] for k in ("wide_left", "halfspace_left", "centre",
                                                         "halfspace_right", "wide_right")],
               "teams": teams}
        if with_matchups:
            out["matchups"] = {f"{a}-{b}": self.matchup(a, b)
                               for a in self.eligible for b in self.eligible if a != b}
        return out
