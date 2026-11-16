# Set pieces

Every call and instruction in a plan so far is about open play. Set pieces are a large share of chances and the part of a match a coach can rehearse most directly, so a pre-match plan that ignores them has a hole. This asks first what about set pieces is knowable before kick-off, then adds only that.

## Pre-registered: set-piece audit (written 2026-11-16, before running)

### Candidate calls (fixed now), per team per match

| Call | Definition |
|---|---|
| Corners | Corners taken |
| Attacking free kicks | Free kicks (pass or shot) taken in the final third |
| Set-piece shots | Shots in possessions that began with a corner or free kick; penalties excluded |
| Set-piece xG | xG of those shots |
| Set-piece share of threat | Set-piece xG / all non-penalty xG |
| Shots per corner | Shots in possessions that began with a corner / corners taken |

Each is called for the team (what it will do) and, read from the opponent's row, for what it will concede.

### Method

Identical to the pooled replay (docs/predictability_audit.md): the same competition-seasons and team-matches, calls from earlier dates only, 5 pseudo-matches of shrinkage, team's own record plus what earlier opponents did against this opponent. Skill = share of the league average's squared error removed, 90% interval by resampling whole matches 500 times.

### Reading rules

- A call **holds** if its interval is above 0.
- A call **goes into the plans** if it holds and its skill is at least 0.05 (the audit's "usable" line).
- A call that does not hold is reported and left out.

### Stated expectations

- Corners hold, around 0.10 to 0.20: they follow territory and possession, which are knowable.
- Attacking free kicks hold weakly.
- Set-piece shots and xG hold weakly at best (under 0.05): few events per match.
- Shots per corner and set-piece share of threat do not hold: ratios of small counts.

If only corners and free kicks hold, the honest set-piece section of a plan is short: how many to expect each way and who takes and attacks them, with no claim about how dangerous they will be.

## Result (2026-11-16, run exactly as registered): three calls go into the plans

13 competition-seasons, 2,741 team-matches.

| Call | Per match | Skill (90% CI) | Team only | Opponent adds | Verdict |
|---|---|---|---|---|---|
| Corners | 4.95 | **0.167** (0.141 to 0.194) | 0.097 | +0.069 | into plans |
| Shots from set pieces | 4.49 | **0.106** (0.080 to 0.128) | 0.047 | +0.059 | into plans |
| xG from set pieces | 0.40 | **0.072** (0.051 to 0.092) | 0.048 | +0.024 | into plans |
| Free kicks in the final third | 2.38 | 0.039 (0.016 to 0.060) | 0.008 | +0.031 | holds, too weak |
| Shots per corner | 0.42 | -0.031 (-0.049 to -0.013) | | | does not hold |
| Set-piece share of threat | 0.34 | -0.035 (-0.052 to -0.016) | | | does not hold |

- **How many set pieces a side gets is knowable; how good it is at them is not.** Corners and set-piece shots follow territory. Shots per corner, the nearest thing here to set-piece quality, is worse than guessing the league average: with about five corners a match, a team's record is noise.
- **The opponent matters as much as the team.** For set-piece shots the opponent adds more skill (+0.059) than the team's own record gives (0.047): who you play decides how many set pieces you defend.
- **Against my expectation:** set-piece shots and xG cleared the 0.05 line; I expected them under it.
- These skills are low next to the open-play calls (possession 0.65, giveaways 0.50). They belong in a plan as a rough expectation.
- A third of all non-penalty xG comes in possessions that began with a corner or free kick. That definition is wide: it counts a shot late in a long possession that started with a free kick in a team's own half.

### What plans now show

- The three calls for both sides, scored after the match like every other call.
- Who takes each side's corners and who shoots from set pieces, from earlier matches, starters only.
- **No instruction is built on these yet.** An instruction needs its own premise test (docs/strategy.md), and nothing here says how to defend a set piece, only how many to expect and from whom.

## Pre-registered: set-piece instructions (written 2026-11-16, before running)

Same idea and same test as the open-play strategy lines (docs/strategy.md): an instruction rests on one call that departs at least 0.5 league standard deviations from the league mean, and its premise is checked by whether the real value landed on the called side of the league mean.

| Rule | Premise: call at least 0.5 SD above league | Instruction |
|---|---|---|
| defend_corners | their corners | Expect many corners to defend; named takers and targets |
| win_corners | our corners | You will win corners; rehearse them, named takers and targets |
| defend_set_pieces | their shots from set pieces | Cut out cheap fouls and corners; named targets |
| attack_set_pieces | our shots from set pieces | Set pieces are a route to goal today; named targets |

- **Units, threshold, score and bar per rule:** exactly as docs/strategy.md. A premise holds if it occurs in at least 60% of the games where the rule fires, with the 90% interval above 50%, and the rule fires at least 100 times.
- **Decision rule:** each rule is judged alone. Only rules that hold go into plans.
- **Stated expectation:** closer to the line than the open-play rules (which held 76 to 94%), because these calls are weaker. Corners rules around 65 to 70%; set-piece shot rules around 60 to 65%, and one of them may fail.
- As before, a held premise means the situation occurred, not that the instruction works.
