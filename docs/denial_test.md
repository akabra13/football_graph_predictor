# Pre-registered: does the denial planner rank links the way real matches do?

Written 2026-11-15, before any run. Code: `src/pitchgraph/chains/denial_test.py`, `scripts/validate_denial.py`, workflow `denial_check.yml`.

## Why

The pre-match claim the Library and the "how to stop them" images make is: take this link away and their threat falls by this range. The only outcome test so far was for removing a *player* (r = 0.08 against real absences). Removing a *link* has never been checked against what happens in matches.

## Design

- **Seasons:** every competition-season in the lake with at least 8 teams that each have 10+ matches (a real league baseline).
- **Unit:** one team in one match, with at least 20 possessions. Everything it is compared with comes from other matches only (as it would before kick-off).
- **Outcome `y`:** the team's xG per possession in the match, divided by what strength alone predicts (its own rate in its other matches x the opponent's conceded rate in its other matches / the league rate without this match), minus 1.
- **Link usage `u_L`:** for each of the region-to-region links (thirds x five lanes), the team's share of moves on that link in the match divided by its usual share in its other matches, minus 1 (so -1 means the link was fully shut down). Clipped to [-1, 3]; set to 0 where the team's usual share is under 0.2%.
- **Links tested:** those carrying at least 1% of all moves, pooled over all team-matches.
- **Observed value of a link:** its coefficient in one joint least-squares regression of `y` on all the `u_L` (with intercept), pooled over all seasons. It reads as the share of threat missing when that link is fully suppressed and the others are unchanged.
- **Planner's value of a link:** the midpoint of its adapt / no-adapt drop on each season's league chain, averaged over seasons.

## Pass bar (all three)

1. Spearman rank correlation between observed and planner values across links is at least **0.5**.
2. Its 90% interval (resampling whole matches, 500 times) lies above 0.
3. It is higher than the rank correlation between observed values and plain usage share ("busy links matter more"), which is the trivial explanation the planner has to beat.

Reported but not part of the bar: the share of links whose observed value falls inside the planner's [adapt, no-adapt] range, and the per-link table.

## What a result can and cannot mean

This is observational. A team having a bad day uses its dangerous links less, so the coefficients can overstate what denying a link would cause. A pass would mean the planner orders links the way matches do; it would not prove that a defence that shuts the link gets the drop. A fail means the "how to stop them" framing has to go, and the images become descriptions of where a team's threat comes from.

## Result (2026-11-15, run exactly as registered): FAIL, and the test missed the claim

13 league seasons, 5,456 team-matches, 2,728 matches. Only **10 links** carried 1% of moves, all of them in the middle third.

| | Rank correlation with observed link values (90% CI) |
|---|---|
| Planner (midpoint of its range) | **0.455** (0.15 to 0.66) |
| Plain usage share | -0.83 (-0.88 to -0.48) |

- Bar 1 (at least 0.5): **missed**, narrowly. Bar 2 (interval above 0): met. Bar 3 (beats usage): met by a wide margin; the busiest links are sideways passes in midfield, which go with *less* threat.
- 5 of the 10 observed values fall inside the planner's range. Moving the ball from the flank in the middle third into the final third is worth 3 to 5% of threat (planner: 3 to 7%). Sideways moves from the half-space out to the flank are negative (-8%), where the planner says about 0 to 5%.
- **The design flaw:** the 1% threshold, which I set, removed every final-third link. The planner's headline levers (half-space to centre in the final third, 11 to 27% in the published images) were never tested. So this result says the planner orders midfield links moderately well; it says nothing about the claims the images make.

## Amendment (written 2026-11-15, after seeing the result above; disclosed as a second look)

Same data, outcome, regression and bar. One change: links are tested if they carry at least **0.25%** of moves (was 1%), so that final-third links are included. Rarer links have noisier usage ratios, which biases their observed values toward zero; that works against the planner, not for it. Because this follows a look at the first result, a pass here is weaker evidence than a first-time pass, and is reported that way.

## Amendment result (2026-11-15): FAIL on the bar, but the two biggest levers are confirmed

Same 5,456 team-matches, now **57 links**.

| | Rank correlation with observed link values (90% CI) |
|---|---|
| Planner | **0.188** (0.02 to 0.30) |
| Plain usage share | 0.013 (-0.14 to 0.14) |

Bar 1 (at least 0.5) is missed clearly. 40% of observed values fall inside the planner's range. **Both versions of the test fail; the planner does not order the full set of links the way matches do.**

What the per-link table shows:

| Link | Planner range | Observed (90% CI) |
|---|---|---|
| Left half-space to centre, final third | 11.5 to 14.4% | **14.4%** (12.1 to 16.6) |
| Right half-space to centre, final third | 11.6 to 14.3% | **12.3%** (10.2 to 14.5) |
| Right flank to right half-space, final third | 4.1 to 9.9% | 4.2% (0.7 to 7.1) |
| Left flank to left half-space, final third | 4.5 to 10.1% | 2.4% (-0.4 to 5.6) |
| Flank, middle third to final third (both sides) | 2.7 to 6.9% | -1.2% and 2.0%, intervals include 0 |
| The other 51 links | mostly under 3% | all within about 3 points of zero |

- **The planner's two largest levers are the two largest in the data, and the sizes agree.** Moves from a half-space into the centre of the final third are worth 12 to 14% of a team's threat each; nothing else comes close.
- **Below the top four, the data cannot tell links apart.** Observed values are within noise of zero, so a rank correlation over all 57 is mostly a correlation between noise and small numbers. That is why the bar fails, and it is also a limit on the planner: its ordering of minor links is not supported.
- **Where the planner is too generous:** flank to half-space in the final third sits at or below the bottom of its range, and progression up the flank shows no measurable value. The "they lose the ball" end of those ranges is not reached.
- **Still untested:** everything here pools all teams against the league chain. The claim that one team depends on a link more than another (Barcelona 2015/16 at 21 to 27% against 15% for an average side) has not been tested. And the caveat above stands: half-space to centre moves lead to shots almost by construction, so agreement on those two links is partly built in.

**Consequence for pre-match use:** "deny the half-space to centre pass in the final third" is supported as the main lever against any team, at 12 to 14% of threat. A ranked plan of three or more links, and team-specific plans, are not supported yet.

## Pre-registered: team-specific test (written 2026-11-15, before running)

Question: when the planner says one team depends on a link more than an average side does, do that team's real matches show it?

- Same team-matches, outcome `y`, usage deviations `u_L` and 57 control links as the amended run.
- For each team-match and each tested link, the **team's excess** `e` = the planner's midpoint drop on the team's own chain (fitted without this match, shrunk to the league without this match, with the season's kappa) minus the same midpoint on that league chain.
- One extra term is added to the joint regression: `z = sum over tested links of u_L x e`. Its coefficient **gamma** reads directly: 1 means the planner's team-specific excess is the right size, 0 means it carries no information about this team.
- **Primary:** tested links are the two confirmed levers (left and right half-space to centre, final third). **Pass bar:** the 90% interval of gamma (resampling whole matches, 500 times) lies above 0.
- Secondary (descriptive): the same with the two flank to half-space final-third links added; gamma's distance from 1.
- Limit stated up front: with kappa = 1000 the team chains sit close to the league, so excesses are small and gamma may be imprecise. An interval that includes both 0 and 1 is reported as "cannot tell", not as a pass or a fail of the idea.
