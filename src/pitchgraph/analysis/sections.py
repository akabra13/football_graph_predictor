"""Report sections that are not single numbers, as JSON-ready dicts.

Each function takes the events of one team's matches (`ev`, from
`analysis.context.prepare`) and returns plain data for the Library to draw.
Moved out of v2's `analysis/scout.py`, which also kept a filtered copy of the
season per team; at full-season scale that copying exhausted a 7 GB laptop.
"""

from __future__ import annotations

import polars as pl

from pitchgraph.analysis.context import score_diff_for
from pitchgraph.graphs import flow, pressing, routes

Frame = pl.DataFrame

# Opponent lanes are in the OPPONENT's frame, where their left is the scouted
# team's right. Reports speak from the scouted team's side.
MIRROR = {"wide_left": "right flank", "halfspace_left": "right half-space",
          "centre": "centre", "halfspace_right": "left half-space",
          "wide_right": "left flank"}
OWN = {"wide_left": "left flank", "halfspace_left": "left half-space", "centre": "centre",
       "halfspace_right": "right half-space", "wide_right": "right flank"}


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def rank_words(rank: int, of: int) -> str:
    """'highest', '3rd highest', 'lowest', '2nd lowest' - from a 1 = highest rank."""
    if rank <= (of + 1) / 2:
        return "highest" if rank == 1 else f"{ordinal(rank)} highest"
    low = of + 1 - rank
    return "lowest" if low == 1 else f"{ordinal(low)} lowest"


def clean(name: str | None) -> str:
    return (name or "").replace("''", "'")


def surname(name: str | None) -> str:
    if not name:
        return "?"
    name = clean(name)
    return name.split()[-1] if len(name.split()) > 1 else name


def team_matches(ev: Frame, tid: int) -> Frame:
    return ev.filter(pl.col("match_id").is_in(ev.filter(pl.col("team_id") == tid)["match_id"].unique()))


def acts(ev: Frame, tid: int) -> Frame:
    return ev.filter((pl.col("team_id") == tid) & pl.col("kind").is_not_null())


def opp_acts(ev: Frame, tid: int) -> Frame:
    return ev.filter((pl.col("team_id") != tid) & pl.col("kind").is_not_null() & pl.col("in_possession"))


def entries(a: Frame) -> Frame:
    """First move of each possession that crossed into the final third, with its lane."""
    cross_y = pl.col("y") + (80 - pl.col("x")) / (pl.col("end_x") - pl.col("x")) * (pl.col("end_y") - pl.col("y"))
    return (a.filter((pl.col("kind") == "move") & (pl.col("x") < 80) & (pl.col("end_x") >= 80))
             .sort("idx").group_by("match_id", "possession", maintain_order=True).first()
             .with_columns(lane=routes.lane_expr(cross_y)))


def shares(frame: Frame, col: str) -> dict:
    total = max(frame.height, 1)
    return {k: v / total for k, v in frame.group_by(col).len().iter_rows() if k is not None}


def match_labels(ev: Frame, teams: dict, tid: int) -> dict:
    m = ev.select("match_id", "match_date", "home_team_id", "away_team_id").unique("match_id")
    out = {}
    for r in m.iter_rows(named=True):
        home = r["home_team_id"] == tid
        opp = teams.get(r["away_team_id"] if home else r["home_team_id"], "?")
        out[r["match_id"]] = f"{'vs' if home else 'at'} {opp}, {r['match_date']}"
    return out


# -- sections ---------------------------------------------------------------------
def routes_section(ev: Frame, tid: int) -> list[dict]:
    rt = routes.route_table(routes.progressions(acts(ev, tid))).head(5)
    return [{"from": r["entry_mid"], "to": r["entry_final"], "share": r["share"],
             "shot_rate": r["shot_rate"], "from_label": OWN[r["entry_mid"]],
             "to_label": OWN[r["entry_final"]]} for r in rt.iter_rows(named=True)]


def players_section(ev: Frame, tid: int, display) -> dict:
    """Who the threat flows through, positioned for the pitch view."""
    a = acts(ev, tid)
    prog = routes.progressions(a)
    inv = flow.involvement(a).join(flow.dependency(a, prog), on="player_id", how="left")
    pos = a.group_by("player_id").agg(x=pl.col("x").median(), y=pl.col("y").median())
    inv = inv.join(pos, on="player_id", how="left").filter(pl.col("actions") >= 150)
    nodes = [{"id": r["player_id"], "name": surname(display(r["player_id"], r["player"])),
              "full": display(r["player_id"], r["player"]),
              "involvement": r["involvement"], "created": r["created"],
              "dependency": r["dependency"] or 0.0, "x": r["x"], "y": r["y"], "actions": r["actions"]}
             for r in inv.head(11).iter_rows(named=True)]
    ids = {p["id"] for p in nodes}
    links = (a.filter((pl.col("type") == "Pass") & (pl.col("kind") == "move")
                      & pl.col("player_id").is_in(list(ids)) & pl.col("recipient_id").is_in(list(ids)))
              .group_by("player_id", "recipient_id")
              .agg(n=pl.len(), v=pl.col("value").clip(lower_bound=0).sum())
              .sort("v", descending=True).head(12))
    return {"nodes": nodes, "links": [{"a": r["player_id"], "b": r["recipient_id"], "n": r["n"], "v": r["v"]}
                                      for r in links.iter_rows(named=True)]}


def pressing_section(ev: Frame, tid: int, display, league_pressed: dict) -> dict:
    g = pressing.copress_graph(ev, tid)
    top = sorted(g.edges(data=True), key=lambda e: -e[2]["weight"])[:5]
    pairs = [{"a": surname(display(u, g.nodes[u]["name"])), "b": surname(display(v, g.nodes[v]["name"])),
              "n": d["weight"]} for u, v, d in top]
    nodes = sorted(({"name": surname(display(pid, d["name"])), "n": d["pressures"], "x": d["x"], "y": d["y"]}
                    for pid, d in g.nodes(data=True)), key=lambda p: -p["n"])[:11]
    starts = pressing.press_starts(ev, tid).filter(pl.col("pressed_position").is_not_null())
    pressed = sorted(({"position": k, "share": v, "league": league_pressed.get(k, 0.0)}
                      for k, v in shares(starts, "pressed_position").items()),
                     key=lambda r: -r["share"])[:5]
    return {"pairs": pairs, "nodes": nodes, "pressed": pressed}


def state_totals(ev: Frame, tid: int) -> Frame:
    """Threat conceded and opponent possessions, by the team's score state."""
    sd = score_diff_for(tid)
    return (opp_acts(ev, tid)
            .with_columns(state=pl.when(sd > 0).then(pl.lit("leading"))
                                  .when(sd < 0).then(pl.lit("trailing"))
                                  .otherwise(pl.lit("level")))
            .group_by("state")
            .agg(v=pl.col("value").clip(lower_bound=0).sum(),
                 poss=pl.struct("match_id", "possession").n_unique()))


def state_rates(totals: Frame) -> dict:
    return {r["state"]: r["v"] / max(r["poss"], 1) for r in totals.iter_rows(named=True)}


def exposure_section(ev: Frame, tid: int, labels: dict, display, league_lanes: dict,
                     league_states: dict) -> dict:
    """Where opponents get in, when it hurts, and the moments to watch."""
    e = entries(opp_acts(ev, tid))
    team = shares(e, "lane")
    lanes = [{"lane": k, "side": MIRROR[k], "share": team.get(k, 0.0),
              "league": league_lanes.get(k, 0.0)} for k in routes.LANES]
    worst = max(lanes, key=lambda r: r["share"] - r["league"])
    moments = e.filter(pl.col("lane") == worst["lane"]).sort("xg_after", descending=True).head(4)
    return {"lanes": lanes, "worst": worst,
            "moments": [{"match": labels.get(r["match_id"], ""), "minute": r["minute"],
                         "xg": r["xg_after"], "by": display(r["player_id"], r["player"])}
                        for r in moments.iter_rows(named=True)],
            "states": state_rates(state_totals(ev, tid)), "league_states": league_states}


def league_baselines(ev: Frame, team_ids) -> dict:
    """League-wide shares the non-scalar sections are compared against."""
    press, lanes, states = [], [], []
    for t in team_ids:
        sub = team_matches(ev, t)
        press.append(pressing.press_starts(sub, t).filter(pl.col("pressed_position").is_not_null())
                     .select("pressed_position"))
        lanes.append(entries(opp_acts(sub, t)).select("lane"))
        states.append(state_totals(sub, t))
    totals = pl.concat(states).group_by("state").agg(pl.col("v").sum(), pl.col("poss").sum())
    return {"pressed": shares(pl.concat(press), "pressed_position"),
            "lanes": shares(pl.concat(lanes), "lane"),
            "states": state_rates(totals)}
