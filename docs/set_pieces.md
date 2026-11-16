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
