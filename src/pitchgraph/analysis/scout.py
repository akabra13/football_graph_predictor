"""The opposition report's analysis: claims, league context, confidence, evidence.

Every scalar claim is computed for EVERY team in the competition-season, which
gives each team a rank and the league a reference distribution; claims are never
stated in isolation. Each is then bootstrapped over the team's matches
(`reliability.estimate`) to get an interval and a confidence label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import polars as pl

from pitchgraph.analysis.context import score_diff_for
from pitchgraph.analysis.reliability import Estimate, estimate
from pitchgraph.graphs import flow, pressing, routes

Frame = pl.DataFrame


# -- helpers ---------------------------------------------------------------------
def _acts(ev: Frame, tid: int) -> Frame:
    return ev.filter((pl.col("team_id") == tid) & pl.col("kind").is_not_null())


def _opp_acts(ev: Frame, tid: int) -> Frame:
    return ev.filter((pl.col("team_id") != tid) & pl.col("kind").is_not_null()
                     & pl.col("in_possession"))


def _ratio(a: float, b: float) -> float:
    return float(a) / float(b) if b else float("nan")


def _entries(acts: Frame) -> Frame:
    """First move of each possession that crossed into the final third."""
    return (acts.filter((pl.col("kind") == "move") & (pl.col("x") < 80) & (pl.col("end_x") >= 80))
                .sort("idx").group_by("match_id", "possession", maintain_order=True).first())


# -- scalar stats: f(events of the team's matches, team_id) -> float --------------
def possession(ev, tid):
    p = ev.filter(pl.col("type") == "Pass")
    return _ratio(p.filter(pl.col("team_id") == tid).height, p.height)


def fast_attacks(ev, tid):
    e = _entries(_acts(ev, tid))
    return _ratio(e.filter(pl.col("pos_seconds") <= 10).height, e.height)


def long_balls(ev, tid):
    p = _acts(ev, tid).filter((pl.col("type") == "Pass") & pl.col("restart").is_null())
    length = ((pl.col("end_x") - pl.col("x")) ** 2 + (pl.col("end_y") - pl.col("y")) ** 2).sqrt()
    return _ratio(p.filter(length > 35).height, p.height)


def buildup_success(ev, tid):
    prog = routes.progressions(_acts(ev, tid))
    deep = prog.filter(pl.col("started_deep").fill_null(False))
    return _ratio(deep.filter(pl.col("idx_final").is_not_null()).height, deep.height)


def _entry_lanes(entries: Frame) -> Frame:
    cross_y = pl.col("y") + (80 - pl.col("x")) / (pl.col("end_x") - pl.col("x")) * (pl.col("end_y") - pl.col("y"))
    return entries.with_columns(lane=routes.lane_expr(cross_y))


def _wide_share(entries: Frame) -> float:
    e = _entry_lanes(entries)
    return _ratio(e.filter(pl.col("lane").str.starts_with("wide")).height, e.height)


def wide_entries(ev, tid):
    return _wide_share(_entries(_acts(ev, tid)))


def threat_per_match(ev, tid):
    a = _acts(ev, tid)
    return _ratio(a["value"].clip(lower_bound=0).sum(), ev["match_id"].n_unique())


def ppda(ev, tid):
    t = pressing.ppda(ev, tid)
    return _ratio(t["passes"].sum(), t["def_actions"].sum())


def press_height(ev, tid):
    s = pressing.press_starts(ev, tid)
    return float(s["x"].median()) if s.height else float("nan")


def high_regains(ev, tid):
    r = pressing.recoveries(ev, tid)
    return _ratio(r.filter(pl.col("x") >= 80).height, r.height)


def conceded_per_match(ev, tid):
    o = _opp_acts(ev, tid)
    return _ratio(o["value"].clip(lower_bound=0).sum(), ev["match_id"].n_unique())


def conceded_in_transition(ev, tid):
    o = _opp_acts(ev, tid).with_columns(v=pl.col("value").clip(lower_bound=0))
    return _ratio(o.filter(pl.col("transition").fill_null(False))["v"].sum(), o["v"].sum())


def conceded_late(ev, tid):
    o = _opp_acts(ev, tid).with_columns(v=pl.col("value").clip(lower_bound=0))
    return _ratio(o.filter(pl.col("bucket") == "60-90+")["v"].sum(), o["v"].sum())


def conceded_wide(ev, tid):
    """Share of opponents' final-third entries that came through the wide lanes."""
    return _wide_share(_entries(_opp_acts(ev, tid)))


@dataclass
class Stat:
    key: str
    section: str
    label: str
    fn: Callable
    fmt: str = "{:.1%}"
    higher: str = "more"          # how to describe a high value
    lower: str = "less"
    sentence: str = ""            # summary line; {v} = value, {rank} = rank words


STATS = [
    Stat("possession", "buildup", "Possession (share of passes)", possession, "{:.1%}", "more of the ball", "less of the ball", sentence="They have {v} of the passes in their matches ({rank} in the league)."),
    Stat("buildup_success", "buildup", "Build-ups from own third that reach the final third", buildup_success, "{:.1%}", "more successful", "less successful", sentence="{v} of their build-ups from their own third reach the final third ({rank} in the league)."),
    Stat("fast_attacks", "buildup", "Final-third entries within 10s of winning the ball", fast_attacks, "{:.1%}", "more direct", "more patient", sentence="{v} of their final-third entries come within 10 seconds of winning the ball ({rank} in the league)."),
    Stat("long_balls", "buildup", "Open-play passes over 35 yards", long_balls, "{:.1%}", "more long balls", "fewer long balls", sentence="{v} of their open-play passes travel over 35 yards ({rank} in the league)."),
    Stat("wide_entries", "buildup", "Final-third entries through the wide lanes", wide_entries, "{:.1%}", "wider", "more central", sentence="{v} of their final-third entries come through the wide lanes ({rank} in the league)."),
    Stat("threat_per_match", "buildup", "Threat created per match (value added)", threat_per_match, "{:.2f}", "more threatening", "less threatening", sentence="They create {v} threat per match ({rank} in the league)."),
    Stat("ppda", "pressing", "PPDA (opponent passes per defensive action; lower = more intense)", ppda, "{:.1f}", "less intense", "more intense", sentence="They allow {v} opponent passes per defensive action ({rank} in the league; lower means a more intense press)."),
    Stat("press_height", "pressing", "Where their press starts (median x, 0-120)", press_height, "{:.0f}", "higher", "deeper", sentence="Their press typically starts {v} yards from their own goal line ({rank} in the league)."),
    Stat("high_regains", "pressing", "Ball recoveries in the attacking third", high_regains, "{:.1%}", "more high regains", "fewer high regains", sentence="{v} of their ball recoveries happen in the attacking third ({rank} in the league)."),
    Stat("conceded_per_match", "vulnerability", "Threat conceded per match", conceded_per_match, "{:.2f}", "more exposed", "tighter", sentence="They concede {v} threat per match ({rank} in the league)."),
    Stat("conceded_in_transition", "vulnerability", "Share of conceded threat that comes in transition", conceded_in_transition, "{:.1%}", "more exposed on the break", "less exposed on the break", sentence="{v} of the threat they concede comes in transition ({rank} in the league)."),
    Stat("conceded_wide", "vulnerability", "Opponent final-third entries through the wide lanes", conceded_wide, "{:.1%}", "attacked wide", "attacked centrally", sentence="{v} of opponents' final-third entries against them come down the flanks ({rank} in the league)."),
    Stat("conceded_late", "vulnerability", "Share of conceded threat after the 60th minute", conceded_late, "{:.1%}", "fade late", "hold up late", sentence="{v} of the threat they concede comes after the 60th minute ({rank} in the league)."),
]


@dataclass
class Claim:
    stat: Stat
    est: Estimate
    rank: int
    of: int
    league_values: dict = field(default_factory=dict)

    @property
    def sentence(self) -> str:
        return self.stat.sentence.format(v=self.stat.fmt.format(self.est.value),
                                         rank=rank_words(self.rank, self.of))

    @property
    def extremeness(self) -> int:
        """Distance from the middle of the league table (0 = median team)."""
        return abs(self.rank - (self.of + 1) / 2)

    @property
    def text(self) -> str:
        e, s = self.est, self.stat
        if e.league is None or not np.isfinite(e.league) or not np.isfinite(e.value):
            return f"{s.fmt.format(e.value)}"
        word = s.higher if e.value > e.league else s.lower
        return (f"{s.fmt.format(e.value)} - {self.rank} of {self.of} "
                f"(league median {s.fmt.format(e.league)}): {word}")


# -- report sections that are not single numbers ------------------------------------
def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def rank_words(rank: int, of: int) -> str:
    """'highest', '3rd highest', 'lowest', '2nd lowest' - from a 1 = highest rank."""
    if rank <= (of + 1) / 2:
        return "highest" if rank == 1 else f"{ordinal(rank)} highest"
    low = of + 1 - rank
    return "lowest" if low == 1 else f"{ordinal(low)} lowest"


def _clean(name: str | None) -> str:
    return (name or "").replace("''", "'")


def _surname(name: str | None) -> str:
    if not name:
        return "?"
    name = _clean(name)
    return name.split()[-1] if len(name.split()) > 1 else name


# Opponent lanes are in the OPPONENT's frame, where their left is the scouted
# team's right. Reports speak from the scouted team's side.
MIRROR = {"wide_left": "right flank", "halfspace_left": "right half-space",
          "centre": "centre", "halfspace_right": "left half-space",
          "wide_right": "left flank"}
OWN = {"wide_left": "left flank", "halfspace_left": "left half-space", "centre": "centre",
       "halfspace_right": "right half-space", "wide_right": "right flank"}


def _match_label(ev: Frame, teams: dict, tid: int) -> dict:
    m = (ev.select("match_id", "match_date", "home_team_id", "away_team_id")
           .unique("match_id"))
    out = {}
    for r in m.iter_rows(named=True):
        home = r["home_team_id"] == tid
        opp = teams.get(r["away_team_id"] if home else r["home_team_id"], "?")
        out[r["match_id"]] = f"{'vs' if home else 'at'} {opp}, {r['match_date']}"
    return out


def _state_totals(ev: Frame, tid: int) -> Frame:
    """Threat conceded and opponent possessions, by the team's score state."""
    sd = score_diff_for(tid)
    return (_opp_acts(ev, tid)
            .with_columns(state=pl.when(sd > 0).then(pl.lit("leading"))
                                  .when(sd < 0).then(pl.lit("trailing"))
                                  .otherwise(pl.lit("level")))
            .group_by("state")
            .agg(v=pl.col("value").clip(lower_bound=0).sum(),
                 poss=pl.struct("match_id", "possession").n_unique()))


def _state_rates(totals: Frame) -> dict:
    return {r["state"]: r["v"] / max(r["poss"], 1) for r in totals.iter_rows(named=True)}


def _shares(frame: Frame, col: str) -> dict:
    total = max(frame.height, 1)
    return {k: v / total for k, v in frame.group_by(col).len().iter_rows() if k is not None}


# -- league-wide computation -------------------------------------------------------
class League:
    """One competition-season, prepared once, queried for any of its teams."""

    def __init__(self, ev: Frame, names: dict | None = None):
        self.ev = ev
        # Lineup nicknames ("Alexis Sánchez") over full legal names
        # ("Alexis Alejandro Sánchez Sánchez") wherever the lineups have one.
        self.names = names or {}
        self.teams = dict(ev.select("team_id", "team").unique().drop_nulls().iter_rows())
        self._by_team = {t: ev.filter(pl.col("match_id").is_in(
            ev.filter(pl.col("team_id") == t)["match_id"].unique().to_list())) for t in self.teams}
        self.table = self._league_table()
        self.opp_adjust = self._opponent_adjustment()
        self._league_baselines()

    def display(self, player_id, fallback: str | None) -> str:
        return _clean(self.names.get(player_id) or fallback)

    def matches_of(self, tid: int) -> Frame:
        return self._by_team[tid]

    def _league_table(self) -> pl.DataFrame:
        rows = []
        for t in self.teams:
            ev = self._by_team[t]
            rows.append({"team_id": t, "team": self.teams[t],
                         **{s.key: s.fn(ev, t) for s in STATS}})
        return pl.DataFrame(rows)

    def _opponent_adjustment(self) -> dict:
        """Per team: mean over matches of (threat an opponent made vs them) minus
        (that opponent's average threat in its OTHER matches). Negative = they
        held opponents below their usual level. Only meaningful when opponents
        play several matches, i.e. complete league seasons."""
        per = (self.ev.filter(pl.col("in_possession") & pl.col("kind").is_not_null())
                      .group_by("match_id", "team_id")
                      .agg(threat=pl.col("value").clip(lower_bound=0).sum()))
        tot = per.group_by("team_id").agg(s=pl.col("threat").sum(), n=pl.len())
        per = per.join(tot, on="team_id").with_columns(
            usual=pl.when(pl.col("n") > 1)
                    .then((pl.col("s") - pl.col("threat")) / (pl.col("n") - 1))
                    .otherwise(None))
        out = {}
        for t in self.teams:
            ms = self._by_team[t]["match_id"].unique().to_list()
            opp = per.filter(pl.col("match_id").is_in(ms) & (pl.col("team_id") != t))
            d = (opp["threat"] - opp["usual"]).drop_nulls()
            out[t] = (float(d.mean()) if len(d) else float("nan"), len(d))
        return out

    def _league_baselines(self):
        """League-wide shares that the team's non-scalar sections are compared against."""
        press, lanes, states = [], [], []
        for t in self.teams:
            ev = self._by_team[t]
            press.append(pressing.press_starts(ev, t).filter(pl.col("pressed_position").is_not_null())
                         .select("pressed_position"))
            lanes.append(_entry_lanes(_entries(_opp_acts(ev, t))).select("lane"))
            states.append(_state_totals(ev, t))
        self._league_pressed = _shares(pl.concat(press), "pressed_position")
        self._league_lanes = _shares(pl.concat(lanes), "lane")
        self._league_states = _state_rates(pl.concat(states).group_by("state").agg(
            pl.col("v").sum(), pl.col("poss").sum()))

    def details(self, tid: int) -> dict:
        """Everything in the report that is not a single number."""
        ev = self._by_team[tid]
        acts = _acts(ev, tid)
        labels = _match_label(ev, self.teams, tid)

        # Routes
        prog = routes.progressions(acts)
        rt = routes.route_table(prog).head(5)
        route_rows = [{"from": r["entry_mid"], "to": r["entry_final"], "share": r["share"],
                       "n": r["n"], "shot_rate": r["shot_rate"],
                       "from_label": OWN[r["entry_mid"]], "to_label": OWN[r["entry_final"]]}
                      for r in rt.iter_rows(named=True)]

        # Players: who the threat flows through, positioned for the pitch view
        inv = flow.involvement(acts).join(flow.dependency(acts, prog), on="player_id", how="left")
        pos = acts.group_by("player_id").agg(x=pl.col("x").median(), y=pl.col("y").median())
        inv = inv.join(pos, on="player_id", how="left").filter(pl.col("actions") >= 150)
        players = [{"id": r["player_id"], "name": _surname(self.display(r["player_id"], r["player"])),
                    "full": self.display(r["player_id"], r["player"]),
                    "involvement": r["involvement"], "created": r["created"],
                    "dependency": r["dependency"] or 0.0, "x": r["x"], "y": r["y"],
                    "actions": r["actions"]}
                   for r in inv.head(11).iter_rows(named=True)]
        ids = {p["id"] for p in players}
        links = (acts.filter((pl.col("type") == "Pass") & (pl.col("kind") == "move")
                             & pl.col("player_id").is_in(ids) & pl.col("recipient_id").is_in(ids))
                     .group_by("player_id", "recipient_id")
                     .agg(n=pl.len(), v=pl.col("value").clip(lower_bound=0).sum())
                     .sort("v", descending=True).head(12))
        link_rows = [{"a": r["player_id"], "b": r["recipient_id"], "n": r["n"], "v": r["v"]}
                     for r in links.iter_rows(named=True)]

        # Pressing units and targets
        g = pressing.copress_graph(ev, tid)
        top = sorted(g.edges(data=True), key=lambda e: -e[2]["weight"])[:5]
        pairs = [{"a": _surname(self.display(u, g.nodes[u]["name"])),
                  "b": _surname(self.display(v, g.nodes[v]["name"])),
                  "n": d["weight"], "ax": g.nodes[u]["x"], "ay": g.nodes[u]["y"],
                  "bx": g.nodes[v]["x"], "by": g.nodes[v]["y"]} for u, v, d in top]
        press_nodes = sorted(({"name": _surname(self.display(pid, d["name"])), "n": d["pressures"],
                               "x": d["x"], "y": d["y"]}
                              for pid, d in g.nodes(data=True)), key=lambda p: -p["n"])[:11]
        starts = pressing.press_starts(ev, tid).filter(pl.col("pressed_position").is_not_null())
        team_pos = _shares(starts, "pressed_position")
        pressed = sorted(({"position": k, "share": v, "league": self._league_pressed.get(k, 0.0)}
                          for k, v in team_pos.items()), key=lambda r: -r["share"])[:5]

        # Where they get attacked
        opp_entries = _entry_lanes(_entries(_opp_acts(ev, tid)))
        lanes_team = _shares(opp_entries, "lane")
        lanes = [{"lane": k, "side": MIRROR[k], "share": lanes_team.get(k, 0.0),
                  "league": self._league_lanes.get(k, 0.0)} for k in routes.LANES]
        worst = max(lanes, key=lambda r: r["share"] - r["league"])
        moments = (opp_entries.filter(pl.col("lane") == worst["lane"])
                              .sort("xg_after", descending=True).head(4))
        moment_rows = [{"match": labels.get(r["match_id"], ""), "minute": r["minute"],
                        "xg": r["xg_after"], "by": self.display(r["player_id"], r["player"])}
                       for r in moments.iter_rows(named=True)]

        # When: threat conceded per opponent possession by score state
        states = _state_rates(_state_totals(ev, tid))

        adj, n_adj = self.opp_adjust[tid]
        return {"routes": route_rows, "players": players, "links": link_rows,
                "copress": pairs, "press_nodes": press_nodes, "pressed": pressed,
                "conceded_lanes": lanes, "worst_lane": worst, "moments": moment_rows,
                "states": states, "league_states": self._league_states,
                "opp_adjusted": adj, "opp_adjusted_n": n_adj}

    # -- one team ---------------------------------------------------------------
    def claims(self, tid: int, n_boot: int = 200) -> list[Claim]:
        ev = self._by_team[tid]
        out = []
        for s in STATS:
            col = self.table[s.key]
            league = float(col.drop_nans().median())
            est = estimate(ev, lambda f, s=s: s.fn(f, tid), league=league, n_boot=n_boot)
            vals = col.drop_nans().to_list()
            rank = 1 + sum(v > est.value for v in vals)
            out.append(Claim(s, est, rank, len(vals)))
        return out
