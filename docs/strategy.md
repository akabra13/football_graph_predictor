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
