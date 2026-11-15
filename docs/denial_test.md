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
