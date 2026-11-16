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

## Result (2026-11-15, run exactly as registered)

13 league seasons, 5,456 team-matches. R² is against predicting the league average; "+ opponent" is what knowing the opponent adds on top.

| Feature | R² from the team (90% CI) | + opponent (90% CI) | Tier |
|---|---|---|---|
| Turnovers per action | 0.430 (0.414 to 0.448) | +0.109 | lead |
| Possession | 0.335 (0.322 to 0.349) | **+0.338** | lead |
| Entries into the central final third per possession | 0.294 (0.272 to 0.315) | +0.154 | lead |
| **Reciprocity** (graph) | 0.289 (0.272 to 0.306) | +0.077 | lead |
| Long forward moves | 0.243 (0.227 to 0.258) | +0.070 | lead |
| **Entropy rate** (graph) | 0.238 (0.221 to 0.253) | +0.105 | lead |
| Directness | 0.203 (0.187 to 0.217) | +0.058 | lead |
| xG per possession | 0.195 | +0.083 | usable |
| Share of actions in the final third | 0.194 | +0.124 | usable |
| Switches of play | 0.188 | +0.079 | usable |
| Shots per possession | 0.173 | +0.140 | usable |
| Height where possessions start | 0.157 | +0.151 | usable |
| Width in the final third | 0.154 | +0.056 | usable |
| Share of turnovers in own third | 0.126 | **+0.195** | usable |
| Left-right balance | 0.117 | +0.019 | usable |
| **Spectral gap** (graph) | 0.108 | +0.077 | usable |
| Share of moves on the half-space-to-centre links | 0.108 | +0.069 | usable |
| **Hodge circulation share** (graph) | 0.105 | +0.027 | usable |
| Entries down the right flank / centre / left flank | 0.069 / 0.056 / 0.056 | about +0.01 to +0.03 | usable |
| xG per shot | 0.038 | +0.018 | drop |
| Entries through the left / right half-space | -0.003 / -0.007 | -0.019 | drop |

What this says:

- **The replay was scoring the wrong thing.** Where a team enters the final third, lane by lane, is the least knowable item on the list: 0 to 7% of a match is predictable, and half-space entries not at all. That is why no plan could beat the league average on lanes.
- **A lot is knowable.** Who will have the ball (67% of the variation explained once both teams are known), how often a side gives it away, how often it reaches the central final third, how direct it plays, how high it wins the ball.
- **The opponent matters for almost everything** (22 of 24 intervals above 0), and for two things it matters as much as the team itself: possession, and the share of turnovers in a team's own third. The second is the opponent's press showing up in the team's numbers.
- **Graph features, against my stated expectation:** reciprocity and entropy rate are in the top tier, and spectral gap and Hodge circulation are usable. By the registered rule they earn a place. Not shown: that they add information beyond possession and directness, which they are likely to overlap with; that would need a joint model.
- **Shot quality (xG per shot) is not predictable** match to match; shot volume is.

Consequence: the pre-match report leads with the lead and usable features, both teams' predicted values with the opponent adjustment, and drops lane-by-lane entry calls.

## Pre-registered: pooled replay, every team (written 2026-11-15, before running)

The audit above used leave-one-match-out, which borrows from matches played later. The Leicester replay used only earlier matches but is one team. This test puts the two together: **the replay's calls for every team, scored together.**

- **Units:** in each of the 13 league seasons, every team-match in the second half of that team's fixtures (by date) where the team has at least 5 earlier matches.
- **Call:** exactly the replay's (`asof_call`): the team's mean over matches played on earlier dates, plus how far earlier opponents of this opponent were pushed from the league mean, each shrunk with 5 pseudo-matches. League baseline: the mean over earlier matches.
- **Score per feature:** skill = 1 − SSE(call) / SSE(league baseline), pooled over all units, with a 90% interval from resampling whole matches (500 times).
- **Primary:** the nine calls the replay makes. A call **holds** if its interval is above 0. **Pass bar: at least 7 of the 9 hold.**
- **Secondary (descriptive):** the same for all 24 audited features; what the opponent term adds (skill of the full call minus skill of the team-only call); and, per team with at least 8 scored games, the share of its calls that were closer than the league baseline (reported as a distribution, so one good team cannot carry the result).

### Result (2026-11-15, run exactly as registered): PASS, 9 of 9 calls hold

13 league seasons, 181 teams, 2,741 scored team-matches. Every call uses only matches played on earlier dates.

| Call | Skill vs league baseline (90% CI) | Team only | Opponent adds | Calls closer than league |
|---|---|---|---|---|
| Share of the ball | **0.648** (0.626 to 0.671) | 0.326 | +0.322 | 72% |
| Giveaways per action | **0.499** (0.479 to 0.519) | 0.412 | +0.087 | 69% |
| Entries into the central final third per possession | **0.427** (0.402 to 0.455) | 0.294 | +0.133 | 64% |
| Reciprocity (graph) | **0.350** (0.329 to 0.372) | 0.281 | +0.069 | 64% |
| Entropy rate (graph) | **0.322** (0.298 to 0.345) | 0.230 | +0.092 | 62% |
| Long forward moves | **0.292** (0.268 to 0.314) | 0.229 | +0.063 | 60% |
| Where possessions start | **0.284** (0.250 to 0.312) | 0.149 | +0.135 | 59% |
| Shots per possession | **0.283** (0.254 to 0.313) | 0.164 | +0.119 | 58% |
| Share of giveaways in own third | **0.283** (0.250 to 0.316) | 0.101 | +0.183 | 57% |

- **All nine intervals are above 0; the bar (7 of 9) is passed.** This is the first pre-registered pass in the programme made with predictions that use only earlier matches, which is how a pre-match report would be made.
- **Not carried by a few teams:** per team (181 with 8+ scored games), the median share of calls closer than the league baseline is 62% (quartiles 58 to 68%, range 42 to 89%); 97% of teams are above half.
- **The opponent term adds to every one of the nine** (all intervals above 0), most for possession (+0.32) and own-third giveaways (+0.18).
- **Secondary, all 24 features:** 22 hold. The two that do not are entries through the left and right half-space, where the call is *worse* than the league average (-0.04). Lane entries on the flanks and centre hold but are weak (0.05 to 0.08), and the opponent adds nothing to them.
- **What skill means in practice:** a skill of 0.65 for possession removes 65% of the squared error of saying "50%". At the other end, 57% of own-third-giveaway calls beat the league average: better than a coin, far from certain, in any single match.
- **Limits:** these are descriptions of how a match will look, not of who wins; nothing here tests whether acting on a call changes the result. Open play only (set pieces are excluded from the counts). The league seasons are 2015/16 men's and 2018 to 2024 women's; other eras are untested.
