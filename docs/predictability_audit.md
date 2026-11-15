# Pre-registered: what can be said about a team before a match?

Written 2026-11-15, before any run. Code: `src/pitchgraph/prematch/audit.py`, `scripts/audit_predictability.py`.

## Why

The season replay (Leicester 2015/16, 19 games) showed that the plan's lane calls were no closer to what happened than the league average, and that both sat near the best a single match allows. Lanes were chosen because the matchup model existed, not because lanes are what differs most between opponents. This audit asks the prior question for 24 candidate statements: **how much of what a team does in its next match is knowable beforehand, and does the opponent change it?** A pre-match report should lead with what passes and drop the rest.

## Design

- **Seasons and units:** as in the denial test: league seasons with at least 8 teams of 10+ matches; one team in one match (at least 20 possessions), open play.
- **Feature value** `v`: computed from that team's actions in that match only.
- **Three predictions** for team T against opponent O in match m, all from other matches only (leave this match out):
  - `league`: the mean of `v` over all other team-matches in the season;
  - `team`: T's mean over its other matches, shrunk to the league with 5 pseudo-matches;
  - `team + opponent`: `team` plus (what teams do against O in O's other matches, shrunk the same way, minus the league mean).
- **Score:** out-of-sample R² against the league prediction, pooled over seasons, with a 90% interval from resampling whole matches (500 times).
  - `R2_team` = 1 − SSE(team) / SSE(league): how much of the next match is known from who the team is.
  - `gain_opponent` = R²(team + opponent) − R²(team): what knowing the opponent adds.

## Candidate features (fixed now)

Lanes and territory: share of final-third entries in each of the five lanes (5); share of actions in the final third; left-right balance; width in the final third; mean height where possessions start.

Tempo and risk: share of the match's moves (possession); mean forward distance per move (directness); share of long forward moves; share of moves that switch two or more lanes; turnovers per action; share of turnovers in the own third.

Threat: shots per possession; xG per shot; xG per possession; entries into the central final third per possession; share of moves on the two half-space-to-centre links (the confirmed lever).

Graph structure and topology of the match's region flow graph (15 regions): **entropy rate** of the transition chain (how unpredictable the next move is); **spectral gap** (how fast the ball's position mixes); **reciprocity** (share of movement that is back-and-forth); **Hodge circulation share** (splitting net flow between regions into a gradient part, which is progression toward goal, and a cyclic part, which is circulation; the share that is cyclic).

## Reading the result (fixed now)

- **Lead with it:** `R2_team` at least 0.20 with the interval above 0.
- **Usable:** `R2_team` at least 0.05 with the interval above 0.
- **Drop:** anything else.
- **Opponent matters** for a feature if the interval of `gain_opponent` is above 0.
- The graph and topology features are held to the same rule. Stated expectation: they are summaries of the same counts, so they should not do better than the plain features; they earn a place only if they do.

Not tested here: whether acting on a predictable feature changes a result.
