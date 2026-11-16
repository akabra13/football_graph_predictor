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
