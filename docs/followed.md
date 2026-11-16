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
