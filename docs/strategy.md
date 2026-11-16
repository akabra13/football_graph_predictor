# Strategy lines: from calls to instructions

Written 2026-11-15, before any run. Code: `src/pitchgraph/prematch/strategy.py`, `scripts/strategy_premises.py`.

## What a strategy line is

Each line is an instruction that rests on one **premise**: a pre-match call that departs clearly from the league in one direction. For example, "Press high" rests on "this opponent, against us, will lose an unusually large share of its giveaways in its own third". The instruction itself is football judgement written into a rule. The premise is a prediction, and predictions can be checked.

- A line **fires** when the call for its feature is at least **0.5 standard deviations** from the league mean in the rule's direction. Mean and standard deviation are taken over team-matches played on earlier dates.
- At most four lines are shown per game, strongest departure first.
- Players named in a line come from earlier matches only: who has done that job so far.

## The rules (fixed now)

| Rule | Premise: call at least 0.5 SD ... | Instruction |
|---|---|---|
| without_ball | our share of the ball below league | Stay compact, plan to break |
| with_ball | our share of the ball above league | Open a set defence |
| press_high | their own-third giveaway share above league | Press high, named targets and pressers |
| hold_block | their own-third giveaway share below league | Do not chase high |
| beat_press | our own-third giveaway share above league | Play out early or go longer |
| protect_centre | their central entries per possession above league | Stop the half-space pass, named players |
| long_balls | their long forward share above league | Win first and second balls |
| centre_open | our central entries per possession above league | Get carriers on the ball |
| centre_shut | our central entries per possession below league | Go wide, value set pieces |
| high_regain | their possession start height above league | First pass must clear the counter-press |
| patterned | their entropy rate below league | Their routes repeat; sit on them |

## Pre-registered test of the premises

- **Units:** the pooled replay's (13 league seasons, second half of each team's fixtures, at least 5 earlier matches, earlier dates only).
- **For each rule:** among units where it fires, the share where the real value in the match fell on the called side of the league mean.
- **A premise holds** if that share is at least **60%** and its 90% interval (resampling whole matches, 500 times) is above 50%.
- **Pass bar:** every rule that fires at least 100 times holds. Rules firing fewer than 100 times are reported as too rare to judge.
- Also reported: how often each rule fires, and the hit share of the opposite, non-firing case as a reference.

## What this does not test

That following the instruction helps. A held premise means the situation the instruction was written for did occur. Whether pressing high against a side that loses the ball deep wins more matches needs an experiment nobody can run on historical data.

## Result (2026-11-15, run exactly as registered): PASS, 11 of 11 premises hold

13 league seasons, 2,741 team-matches. "Occurred" = the real value fell on the called side of the league mean.

| Rule | Fires in | Situation occurred when fired (90% CI) | When not fired |
|---|---|---|---|
| without_ball | 24% of games | **94%** (93 to 96) | 36% |
| with_ball | 24% | **94%** (93 to 96) | 36% |
| centre_shut | 19% | **90%** (88 to 92) | 50% |
| protect_centre | 17% | **83%** (80 to 86) | 34% |
| centre_open | 17% | **83%** (80 to 86) | 34% |
| patterned | 17% | **81%** (79 to 84) | 41% |
| hold_block | 15% | **80%** (77 to 83) | 47% |
| high_regain | 15% | **80%** (76 to 83) | 45% |
| press_high | 16% | **76%** (72 to 79) | 43% |
| beat_press | 16% | **76%** (72 to 79) | 43% |
| long_balls | 16% | **76%** (73 to 80) | 39% |

- Every rule fired more than 400 times and every one clears the bar (at least 60%, interval above 50%).
- When a plan says a situation will occur, it does in 76 to 94% of games. The weakest are the pressing and long-ball rules: about one time in four the instruction would have been written for a situation that did not arrive.
- Rules are selective: each fires in 15 to 24% of games, so a typical game gets one or two lines, and some get none.

### Leicester City 2015/16, second half (19 games)

26 instructions, 23 with the situation occurring. 12 of the 26 are "expect to be without the ball" (11 occurred): a team's own strong traits repeat week to week, so its plans look alike. What changes game to game is the opponent-specific lines: for example "press high" before Stoke (targets Butland, Pieters, Whelan; pressers Vardy, Albrighton, Mahrez) and "do not chase high" before two others.

### Limits

- A held premise means the situation occurred, not that the instruction was right or would have worked.
- Thresholds are in league standard deviations, so a line can rest on a gap that looks small in raw numbers (18% against 16% of giveaways in the own third).
- The named players are who did the job in earlier matches. Injuries, suspensions and line-up changes are not known to the plan.

## Pre-registered: do line-ups sharpen the calls? (written 2026-11-15, before running)

Starting line-ups are announced before kick-off, so a pre-match plan may use them. Two uses, treated separately.

**1. Naming players (no test needed).** Players named in a plan are restricted to those starting today. A regular (started at least 60% of the team's earlier matches, minimum 5) who is not starting is listed as missing, for both sides.

**2. Weighting the calls (tested).** Idea: a team's earlier matches say more about today when more of today's starters played in them.

- **Line-up-weighted call:** as the plain call, but each earlier match of the team counts with weight (shared starters / 11)^4, so 11 shared = 1, 9 = 0.45, 7 = 0.16. The opponent term is weighted the same way by the opponent's shared starters. The 5 pseudo-matches of shrinkage are unchanged, so a heavily rotated side is pulled further toward the league.
- **Units and score:** the pooled replay's units and skill, for the nine primary calls.
- **A call is helped** if the 90% interval (resampling whole matches, 500 times) of skill(weighted) minus skill(plain) is above 0, and **hurt** if it is below 0.
- **Decision rule:** the plans switch to weighted calls only if at least 5 of the 9 are helped and none is hurt. Otherwise the plain calls stay and line-ups are used for naming players only.
- Stated expectation: small either way. Weighting trades sample size for relevance, and most of what the calls capture is club-level style that survives rotation.

### Result (2026-11-15, run exactly as registered): line-up weighting HURTS; plain calls stay

2,741 team-matches. A team shares on average 8.4 starters with its previous match (median 9, 10th percentile 6).

| Call | Plain | Line-up weighted | Difference (90% CI) |
|---|---|---|---|
| Share of the ball | 0.648 | 0.466 | -0.18 (-0.20 to -0.17) |
| Central entries per possession | 0.427 | 0.303 | -0.12 |
| Giveaways per action | 0.499 | 0.379 | -0.12 |
| Reciprocity | 0.350 | 0.270 | -0.08 |
| Shots per possession | 0.283 | 0.206 | -0.08 |
| Own-third giveaway share | 0.283 | 0.210 | -0.07 |
| Entropy rate | 0.322 | 0.249 | -0.07 |
| Where possessions start | 0.284 | 0.214 | -0.07 |
| Long forward moves | 0.292 | 0.226 | -0.07 |

- **0 of 9 helped, 9 of 9 hurt.** By the registered rule the plans keep the plain calls, and line-ups are used for naming players only.
- The only features helped are the lane entries, which the audit found barely knowable: left flank 0.053 to 0.065, and the half-space entries from worse-than-league to about level. Who plays seems to matter for *which side* a team goes down, not for how it plays overall.
- **A flaw in my design:** the weights also shrink the effective sample (a typical weight is 0.45), so each call is pulled harder toward the league. The result cannot separate "who plays does not matter" from "less data is worse".

### Amendment (written 2026-11-15, after seeing the result above; disclosed second look)

Same weights, but rescaled per call so they sum to the number of earlier matches used: the amount of data is unchanged and only its emphasis moves toward matches with today's starters. Same units, score and decision rule. A pass here is weaker evidence than a first-time pass.

### Amendment result (2026-11-15): line-ups make almost no difference to the calls

With the amount of data held equal, line-up weighting helps 1 of the 9 calls (giveaways per action, +0.017), hurts 2 (possession -0.011, long forward moves -0.010) and leaves 6 unchanged within noise. The rule says keep the plain calls.

- **Reading:** the first result's large losses came from throwing data away, not from line-ups being misleading. Once that is removed, who starts barely moves these calls. How a team plays, at the level these nine calls describe, belongs to the club and its coach, not to the eleven on the day, at least for the ordinary rotation seen here (a typical side keeps 9 of 11 starters).
- **Correction to the first reading:** the apparent help for lane entries was also an artefact of extra shrinkage. With data held equal, lane entry calls get worse with line-up weighting.
- **Not tested:** heavy rotation specifically (the 10% of matches with 6 or fewer shared starters), or the absence of one particular player. v3 found player-removal forecasts weak (r = 0.08), which points the same way.
- **What line-ups are used for:** naming. Players in a plan are restricted to today's starters, and regulars who are not starting are listed for both sides.

## Second team: Barcelona 2015/16, second half (19 games; run 2026-11-16)

Run to see whether the plan reads as well for a possession side as for Leicester. Nothing here was pre-registered; it is a reading of one replay.

- **The calls work better than for Leicester:** 248 of 342 closer than the league average (Leicester 206 of 342). The most likely result was the real one in 15 of 19 games.
- **The instructions held:** 82 given, 69 with the situation occurring.
- **But the plan barely changes from week to week.** "You will have the ball" fired in 19 of 19 games, "the centre is open for you" in 19 and "they are patterned" in 15. Those three lines are 53 of the 82 instructions. They are true, and a Barcelona coach already knows them.
- **Cause:** every rule compares a call with the league average. A team far from the league average in its own style trips the same rules against everyone. Leicester showed the same thing less strongly (11 of 26 lines were "expect to be without the ball").
- **What did change by opponent:** press high (9 games, situation occurred in 5), expect long balls (4), set pieces as a route to goal (12, occurred in 9).
- **Favourites understated again:** 38 expected points, 46 taken; away at Deportivo the win was given 49% (it finished 8-0).
- **Corners over-called:** 113 called for Barcelona, 95 taken.

**What this points to:** instructions should rest on how this game differs from the team's own usual, not from the league. That is a new set of premises and needs its own registered test.


## Pre-registered: instructions about this game, not about the team (written 2026-11-16, before running)

**Problem.** Every rule above compares a call with the league average, so a side with an extreme style gets the same lines every week (Barcelona: three lines were 53 of 82 instructions).

**Change.** A rule now compares a call with **a normal week for this team**:

- For our own numbers, the reference is **our usual**: our earlier matches, shrunk to the league as always.
- For the opponent's numbers, the reference is **what opponents usually do against us**: the earlier matches of teams playing us, shrunk the same way.

By the arithmetic of the calls, the first departure is what this opponent does to teams, and the second is how this opponent's own habits differ from the league. Neither contains our own constant style, so a line can only fire for something about this opponent.

- A line **fires** when the call is at least **0.4 league standard deviations** from the reference in the rule's direction. (Lower than the 0.5 used above because opponent effects are smaller than team-versus-league gaps. Fixed now, not tuned.)
- Its **premise holds** in a match if the real value landed on the called side of the reference.
- Same units, same bar per rule as above: fires at least 100 times, premise occurs in at least 60% of those, 90% interval above 50%.

### The rules (fixed now)

| Rule | Whose number, against which reference | Direction |
|---|---|---|
| less_ball / more_ball | our share of the ball v our usual | below / above |
| pressed_deep | our own-third giveaway share v our usual | above |
| sloppier | our giveaways per action v our usual | above |
| centre_tighter / centre_looser | our central entries per possession v our usual | below / above |
| fewer_shots / more_shots | our shots per possession v our usual | below / above |
| forced_long | our long forward share v our usual | above |
| pinned_back | where our possessions start v our usual | below |
| win_more_corners | our corners v our usual | above |
| press_them | their own-third giveaway share v our usual opponents | above |
| leave_them | the same | below |
| they_go_long | their long forward share v our usual opponents | above |
| they_come_central | their central entries per possession v our usual opponents | above |
| they_regain_high | where their possessions start v our usual opponents | above |
| they_are_readable | their entropy rate v our usual opponents | below |
| more_corners_against | their corners v our usual opponents | above |

### Decision rule

- Each rule is judged alone. Rules that hold replace the league-based lines in the plans; a plan shows at most four, strongest first. The league-based rules stay documented above.
- If fewer than six rules hold, the plans keep the league-based lines and this is reported as a failed rebuild.

### Stated expectations

- Fire rates lower than before (5 to 15% each), because opponent effects are small next to team style.
- Possession rules hold comfortably (the opponent adds as much as the team there). The pressing rules hold. Shots, long balls and corners are doubtful, around 55 to 62%.
- I expect 10 to 14 of the 18 to hold.
