# Does following an instruction go with better results?

Every test so far checks that the situation an instruction was written for occurred. None checks whether doing what the instruction says helps. History cannot answer that properly: nobody was given these plans, and teams choose how to play for reasons the data does not show. This is the best available substitute, with its limits stated first.

## Pre-registered (written 2026-11-16, before running)

### What can be tested

Only instructions whose action can be seen in event data. Five of the eighteen:

| Rule | The instruction | "The team did it" means |
|---|---|---|
| press_them | Press high | More final-third pressures per opponent pass than the team's own usual |
| leave_them | Do not chase high | Fewer than its usual |
| pressed_deep | Keep it simple or go over them | A larger share of long forward passes (40 or more along the pitch) than its usual |
| centre_tighter | Do not force it; go round | A larger share of its final-third actions on the flanks than its usual |
| they_come_central | Stop the half-space pass | The opponent played a smaller share of half-space-to-centre passes in the final third than the opponent's own usual |

The other thirteen describe what to expect or ask for something events do not record (who wins second balls, where the first pass after a regain goes). They are not tested and stay as they are.

### The main problem, and what is done about it

A team that is losing presses more and plays longer; a team that is winning sits back. So "did the team press" is partly a result of the score, not a cause of it.

- **Everything is measured only while the score is level**: both what the team did and how the match went. Minutes after one side leads are ignored. A match needs at least 20 level minutes to count.
- **Outcome:** xG difference per 90 level minutes (penalties excluded), minus the call for that same quantity made before the match in the usual way. Positive means the team did better than its own and its opponent's records predicted.
- "Usual" is the team's earlier matches, shrunk as always, measured the same way (level minutes only).

### The comparison

Units are the pooled replay's team-matches. For each rule:

- **In games where the rule fired:** the outcome for teams that did it minus the outcome for teams that did not.
- **In games where it did not fire:** the same difference. This is how much the behaviour goes with a good outcome anyway (a side on top presses higher whatever the plan says).
- **The test statistic is the first minus the second:** is the behaviour worth more in the games where the plan asks for it? Games are weighted by level minutes; 90% interval by resampling whole matches 500 times.

### Reading rules

- **Supported:** interval above 0.
- **Contradicted:** interval below 0. The instruction is cut from the plans.
- **No evidence either way:** interval spans 0. The instruction stays, described as untested for effect.

### What this cannot show

- Cause. Teams that pressed may differ from teams that did not in ways the level-score restriction does not remove (who was available, how the opponent set up that day).
- Anything about the thirteen untested instructions.
- Whether a team told to do it would have done it well.

### Stated expectations

- Most likely result: **no evidence either way for all five.** A rule fires in 10 to 17% of 2,741 team-matches, half of those do it, and single-match xG is noisy. The intervals will be wide.
- The behaviour will go with good outcomes in general (pressing high and getting wide are what sides on top do), which is why the comparison with non-firing games is the statistic.
- If one is supported, my guess is they_come_central, because the lever it rests on is the one denial confirmed league-wide.

## Result (2026-11-16, run exactly as registered): no evidence either way, for all five

2,741 team-matches. The median match has 40 level minutes; 74% have at least 20 and are used. The pre-match call for level-score xG difference removes 21% of the league average's error (90% interval 17 to 25%), so the baseline the outcome is measured against is a real one.

Figures are xG difference per 90 level minutes, against its call: teams that did it minus teams that did not.

| Rule | Fired | Did it | Gap when fired (90% CI) | Gap when not fired (90% CI) | Extra when asked (90% CI) | Verdict |
|---|---|---|---|---|---|---|
| press_them | 204 | 66% | +0.27 (-0.03 to +0.57) | +0.47 (+0.38 to +0.57) | -0.20 (-0.52 to +0.07) | no evidence |
| leave_them | 240 | 81% | -0.67 (-0.96 to -0.38) | -0.42 (-0.51 to -0.32) | -0.26 (-0.57 to +0.07) | no evidence |
| pressed_deep | 274 | 66% | -0.62 (-0.85 to -0.42) | -0.44 (-0.53 to -0.34) | -0.18 (-0.41 to +0.04) | no evidence |
| centre_tighter | 207 | 57% | -0.12 (-0.37 to +0.13) | -0.26 (-0.35 to -0.17) | +0.14 (-0.12 to +0.40) | no evidence |
| they_come_central | 311 | 50% | +0.46 (+0.26 to +0.66) | +0.41 (+0.31 to +0.50) | +0.06 (-0.16 to +0.27) | no evidence |

**What this says.**

- **The registered answer: nothing is supported and nothing is contradicted.** This is the result I expected. With 200 to 300 games per rule and noisy single-match xG, the intervals are about half an xG per 90 wide. The test could only have seen a large effect.
- **The behaviours themselves matter a lot, with or without a plan.** While the score is level, sides that press higher than their usual are 0.47 xG per 90 better off than their records predicted; sides that keep the opponent off the half-space-to-centre pass are 0.41 better off; sides that go longer than usual are 0.44 worse off; sides that end up wider than usual are 0.26 worse off. These are associations: a side that is on top presses higher *because* it is on top.
- **The plan's call adds nothing measurable to that.** Pressing high is worth about the same whether or not the plan said to. Stopping the half-space pass is worth about the same whether or not the plan flagged it.
- **Two instructions point the wrong way, without reaching the bar.** "Do not chase high" (leave_them): teams that pressed less did worse, 0.67 worse in the games where the plan said not to chase. "Go over them" (pressed_deep): teams that went longer did worse, 0.62 worse in the games where the plan said they would be pressed deep. Neither interval for the extra effect excludes 0, so by the rule they are not contradicted. But the action each one recommends goes with worse outcomes everywhere.

**What was changed, and on what authority.**

- By the registered rule, all five instructions stay, described as untested for effect.
- **A judgement after seeing the result, not part of the registration:** the two instructions above are reworded to stop recommending the action. "Do not chase high... hold your shape and wait" becomes a statement that pressing high is less likely to force a mistake from this opponent. "Keep the first phase simple or go over them" drops "or go over them". Their premises, and so the test they passed, are unchanged.
- The report now says that five instructions were checked for effect and none showed any.

**Limits of this result.**

- "No evidence" is not "no effect". An extra 0.2 xG per 90 from pressing when asked would be worth having and would be invisible here.
- Level-score minutes remove the score as a cause of behaviour. They do not remove dominance: a side playing well does all the "good" things at once.
- Thirteen of the eighteen instructions cannot be tested this way at all.
