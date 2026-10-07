"""Every report claim as a ratio of per-match sums: the ledger.

The ledger has one row per (match, team) and, for each claim, a numerator and
a denominator column. A team's value is sum(num) / sum(den) over its matches;
"per match" claims use a denominator of 1 per match. Because each row is one
match, a bootstrap over matches is just resampling rows of a small array, so
confidence intervals cost milliseconds instead of re-running the analysis 200
times (which took ~75 s per team in v2).

One claim changes definition to fit the shape: press height was a median of
press-start positions; medians do not add across matches, so it is now a mean.

All teams in a competition-season are computed in one vectorised pass.
Defensive claims for team T are its opponents' attacking columns, joined on the
match.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from pitchgraph.graphs.pressing import DEFENSIVE_ACTIONS
from pitchgraph.graphs.routes import lane_expr

TRANSITION_WINDOW = 10.0
LONG_PASS = 35.0


@dataclass(frozen=True)
class Stat:
    key: str
    section: str
    label: str
    num: str
    den: str                 # "matches" means one per match
    fmt: str = "{:.1%}"
    higher: str = "more"
    lower: str = "less"
    sentence: str = ""


STATS = [
    Stat("possession", "buildup", "Possession (share of passes)", "passes", "passes_all",
         "{:.1%}", "more of the ball", "less of the ball",
         "They have {v} of the passes in their matches ({rank} in the league)."),
    Stat("buildup_success", "buildup", "Build-ups from own third that reach the final third",
         "deep_reached", "deep_poss", "{:.1%}", "more successful", "less successful",
         "{v} of their build-ups from their own third reach the final third ({rank} in the league)."),
    Stat("fast_attacks", "buildup", "Final-third entries within 10s of winning the ball",
         "fast_entries", "entries", "{:.1%}", "more direct", "more patient",
         "{v} of their final-third entries come within 10 seconds of winning the ball ({rank} in the league)."),
    Stat("long_balls", "buildup", "Open-play passes over 35 yards", "long_passes", "open_passes",
         "{:.1%}", "more long balls", "fewer long balls",
         "{v} of their open-play passes travel over 35 yards ({rank} in the league)."),
    Stat("wide_entries", "buildup", "Final-third entries through the wide lanes", "wide_entries",
         "entries", "{:.1%}", "wider", "more central",
         "{v} of their final-third entries come through the wide lanes ({rank} in the league)."),
    Stat("threat_per_match", "buildup", "Threat created per match", "threat", "matches",
         "{:.2f}", "more threatening", "less threatening",
         "They create {v} threat per match ({rank} in the league)."),
    Stat("ppda", "pressing", "PPDA (opponent passes per defensive action; lower = more intense)",
         "opp_passes_high", "def_actions_high", "{:.1f}", "less intense", "more intense",
         "They allow {v} opponent passes per defensive action ({rank} in the league; lower means a more intense press)."),
    Stat("press_height", "pressing", "Where their press starts (mean x, 0-120)", "press_x",
         "press_starts", "{:.0f}", "higher", "deeper",
         "Their press typically starts {v} yards from their own goal line ({rank} in the league)."),
    Stat("high_regains", "pressing", "Ball recoveries in the attacking third", "high_recoveries",
         "recoveries", "{:.1%}", "more high regains", "fewer high regains",
         "{v} of their ball recoveries happen in the attacking third ({rank} in the league)."),
    Stat("conceded_per_match", "vulnerability", "Threat conceded per match", "conc_threat", "matches",
         "{:.2f}", "more exposed", "tighter",
         "They concede {v} threat per match ({rank} in the league)."),
    Stat("conceded_in_transition", "vulnerability", "Share of conceded threat that comes in transition",
         "conc_trans_threat", "conc_threat", "{:.1%}", "more exposed on the break", "less exposed on the break",
         "{v} of the threat they concede comes in transition ({rank} in the league)."),
    Stat("conceded_wide", "vulnerability", "Opponent final-third entries through the wide lanes",
         "conc_wide_entries", "conc_entries", "{:.1%}", "attacked wide", "attacked centrally",
         "{v} of opponents' final-third entries against them come down the flanks ({rank} in the league)."),
    Stat("conceded_late", "vulnerability", "Share of conceded threat after the 60th minute",
         "conc_late_threat", "conc_threat", "{:.1%}", "fade late", "hold up late",
         "{v} of the threat they concede comes after the 60th minute ({rank} in the league)."),
]
BY_KEY = {s.key: s for s in STATS}


def _attack_side(ev: pl.DataFrame) -> pl.DataFrame:
    """Per (match, team): everything measured while that team had the ball."""
    keys = ["match_id", "team_id"]
    acts = ev.filter(pl.col("kind").is_not_null() & pl.col("in_possession"))
    pos_v = pl.col("value").clip(lower_bound=0.0)

    base = acts.group_by(keys).agg(
        threat=pos_v.sum(),
        trans_threat=pos_v.filter(pl.col("transition").fill_null(False)).sum(),
        late_threat=pos_v.filter(pl.col("bucket") == "60-90+").sum(),
    )
    passes = (ev.filter(pl.col("type") == "Pass").group_by(keys).agg(passes=pl.len()))
    length = ((pl.col("end_x") - pl.col("x")) ** 2 + (pl.col("end_y") - pl.col("y")) ** 2).sqrt()
    open_p = (acts.filter((pl.col("type") == "Pass") & pl.col("restart").is_null())
                  .group_by(keys).agg(open_passes=pl.len(), long_passes=(length > LONG_PASS).sum()))

    cross_y = pl.col("y") + (80 - pl.col("x")) / (pl.col("end_x") - pl.col("x")) * (pl.col("end_y") - pl.col("y"))
    entries = (acts.filter((pl.col("kind") == "move") & (pl.col("x") < 80) & (pl.col("end_x") >= 80))
                   .sort("idx").group_by("match_id", "possession", "team_id", maintain_order=True).first()
                   .with_columns(lane=lane_expr(cross_y))
                   .group_by(keys).agg(entries=pl.len(),
                                       fast_entries=(pl.col("pos_seconds") <= TRANSITION_WINDOW).sum(),
                                       wide_entries=pl.col("lane").str.starts_with("wide").sum()))
    poss = (acts.sort("idx").group_by("match_id", "possession", "team_id", maintain_order=True)
                # Reached = a completed move ended in the final third. A failed pass
                # aimed there does not count.
                .agg(deep=pl.first("x") < 40,
                     reached=((pl.col("kind") == "move") & (pl.col("end_x") >= 80)).any())
                .group_by(keys).agg(deep_poss=pl.col("deep").sum(),
                                    deep_reached=(pl.col("deep") & pl.col("reached").fill_null(False)).sum()))
    out = base
    for t in (passes, open_p, entries, poss):
        out = out.join(t, on=keys, how="left")
    return out.fill_null(0)


def _pressing_side(ev: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Per (match, team): what the team did without the ball, plus every team's
    passes in its own 60% (the PPDA numerator, attributed to the opponent)."""
    keys = ["match_id", "team_id"]
    clock = pl.col("period") * 10_000 + pl.col("period_seconds")
    first_press = (ev.filter((pl.col("type") == "Pressure") & ~pl.col("in_possession"))
                     .with_columns(clock=clock).sort("clock")
                     .group_by("match_id", "possession", "team_id", maintain_order=True).first()
                     .group_by(keys).agg(press_starts=pl.len(), press_x=pl.col("x").sum()))
    fail = pl.col("outcome").fill_null("")
    won = ((pl.col("type") == "Ball Recovery")
           | ((pl.col("type") == "Interception") & ~fail.is_in(["Lost", "Lost In Play", "Lost Out"])))
    rec = (ev.filter(won & pl.col("x").is_not_null()).group_by(keys)
             .agg(recoveries=pl.len(), high_recoveries=(pl.col("x") >= 80).sum()))
    sub = pl.col("sub_type").fill_null("")
    defn = (ev.filter((pl.col("x") > 48) & (pl.col("type").is_in(DEFENSIVE_ACTIONS)
                                            | ((pl.col("type") == "Duel") & (sub == "Tackle"))))
              .group_by(keys).agg(def_actions_high=pl.len()))
    # Passes the team ALLOWED in the opponent's own 60%: opponent passes at x < 72.
    opp_pass = (ev.filter((pl.col("type") == "Pass") & (pl.col("x") < 72))
                  .group_by("match_id", pl.col("team_id").alias("passer")).agg(n=pl.len()))
    out = first_press.join(rec, on=keys, how="full", coalesce=True).join(defn, on=keys, how="full", coalesce=True)
    return out, opp_pass


def ledger(ev: pl.DataFrame) -> pl.DataFrame:
    """One row per (match, team) with a num/den column pair for every claim.

    `ev` is the output of `analysis.context.prepare` for one competition-season.
    """
    att = _attack_side(ev)
    press, opp_pass = _pressing_side(ev)
    teams = ev.select("match_id", "team_id").drop_nulls().unique()
    pair = (teams.join(teams.rename({"team_id": "opp_id"}), on="match_id")
                 .filter(pl.col("team_id") != pl.col("opp_id")))

    conc = att.select("match_id", pl.col("team_id").alias("opp_id"),
                      pl.col("threat").alias("conc_threat"),
                      pl.col("trans_threat").alias("conc_trans_threat"),
                      pl.col("late_threat").alias("conc_late_threat"),
                      pl.col("entries").alias("conc_entries"),
                      pl.col("wide_entries").alias("conc_wide_entries"),
                      pl.col("passes").alias("opp_passes_total"))
    led = (pair.join(att, on=["match_id", "team_id"], how="left")
               .join(conc, on=["match_id", "opp_id"], how="left")
               .join(press, on=["match_id", "team_id"], how="left")
               .join(opp_pass.rename({"passer": "opp_id", "n": "opp_passes_high"}),
                     on=["match_id", "opp_id"], how="left")
               .fill_null(0))
    return led.with_columns(passes_all=pl.col("passes") + pl.col("opp_passes_total"),
                            matches=pl.lit(1))


def team_values(led: pl.DataFrame) -> pl.DataFrame:
    """Every team's value for every claim: sum(num) / sum(den)."""
    sums = led.group_by("team_id").agg([pl.col(c).sum() for c in
                                         sorted({s.num for s in STATS} | {s.den for s in STATS})])
    return sums.select("team_id", *[(pl.col(s.num) / pl.col(s.den)).alias(s.key) for s in STATS])
