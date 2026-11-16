# Result and threat calls

A plan so far says how a match will look (who has the ball, where it is lost, how direct each side is). It says nothing about how dangerous each side will be or who is likely to win. This adds both, and tests them before they go into any plan.

## Pre-registered (written 2026-11-15, before running)

### The calls

- **Threat call:** a team's non-penalty xG in the match (all shots, set pieces included, shoot-outs excluded). Same arithmetic as every other call: the team's earlier matches, shrunk to the league with 5 pseudo-matches, plus what earlier opponents created against this opponent, minus the league average. Earlier dates only.
- **Result call:** the two threat calls are turned into expected goals and then into chances of a home win, a draw and an away win.
  - Expected goals = threat call x (league goals per match / league xG per match) x (league home or away goals / league goals), all three league figures from earlier dates only. The first factor puts penalties and own goals back in on average; the second is home advantage.
  - Each side's goals are treated as an independent Poisson count. No tuning of any kind; there is nothing to fit.
- **Comparison calls** (reported, no bar): the same model fed with goals instead of xG, and an even blend of the two.
- **Baseline:** the league's home-win, draw and away-win frequencies so far that season (earlier dates only).

### Units

The competition-seasons of the pooled replay. A team-match counts for the threat call under the pooled replay's rule (later half of the team's fixtures, at least 5 earlier matches). A match counts for the result call when both of its team-matches count.

### Scores and bars

1. **Threat call holds** if its skill against the league average (share of squared error removed) has a 90% interval above 0, resampling whole matches 500 times. Same rule as the nine existing calls.
2. **Result call holds** if its ranked probability score (RPS, lower is better; 0 is perfect) is below the baseline's, with the 90% interval of the difference above 0, resampling whole matches 500 times.
3. **Calibration** (reported): predicted chances in six bins against how often those outcomes happened. If the result call holds but any bin with at least 100 predictions is off by more than 5 points, plans show the chances with that stated.

### Decision rule

- Threat call holds: plans show expected threat for both sides.
- Result call holds: plans show the three chances. If it does not hold, plans show no chances at all.

### Stated expectations

- Threat call holds with modest skill (shots per possession scored 0.28; xG per shot was not predictable, so somewhere below that).
- Result call beats the baseline by a small margin, of the order of 5% of RPS. xG-fed about level with or slightly better than goals-fed.
- Independent Poisson is known to give draws slightly too little chance. Not corrected here.

### What this is not

- Not a comparison with bookmakers, who use far more information and will be better. Beating base rates is the floor for showing a number, not a claim of an edge.
- Not betting advice.
