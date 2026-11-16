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

## Result (2026-11-15, run exactly as registered): both calls HOLD; chances are too cautious at the extremes

13 competition-seasons, 2,741 team-matches for the threat call, 1,357 matches for the result call.

### Threat call

| Fed with | Skill (90% CI) | Team only | Opponent adds | Closer than league |
|---|---|---|---|---|
| **xG** | **0.296** (0.268 to 0.323) | 0.210 | +0.086 | 60% |
| Goals | 0.178 (0.150 to 0.204) | 0.125 | +0.053 | 59% |

The threat call holds, about level with shots per possession (0.283) and slightly above what I expected. Goals themselves are much less knowable than chance creation, as they should be.

### Result call

Home win, draw and away win happened in 45%, 24% and 32% of matches.

| Chances from | RPS | Gain over base rates (90% CI) | Relative | Most likely result was right |
|---|---|---|---|---|
| **xG (the registered call)** | **0.1896** | +0.0425 (+0.0370 to +0.0481) | 18% | 56% |
| Goals | 0.1925 | +0.0395 | 17% | 54% |
| Even blend | 0.1891 | +0.0430 | 19% | 55% |
| Base rates | 0.2321 | 0 | 0% | 44% |

- The result call holds, by much more than the 5% I expected. Part of that is the data: these leagues include very unequal ones (women's leagues, La Liga 2015/16), where strength gaps are large and easy to see.
- xG-fed against goals-fed: +0.0030 (-0.0001 to +0.0060). xG is probably slightly better; the interval just touches 0.
- Draws: given 23% on average, happened 24%. The known Poisson draw problem is small here.

### Calibration

| Chance given | Predictions | Average given | Happened |
|---|---|---|---|
| under 20% | 684 | 13.8% | 9.2% |
| 20 to 30% | 1,598 | 25.0% | 25.6% |
| 30 to 40% | 623 | 34.8% | 31.3% |
| 40 to 50% | 488 | 44.8% | 47.1% |
| 50 to 60% | 347 | 54.6% | 56.8% |
| over 60% | 331 | 72.0% | 79.5% |

Worst gap 7.5 points, above the 5-point line. **The chances are too cautious at both ends:** strong favourites win more often than stated (80% against 72%) and long shots come in less often (9% against 14%). The cause is the shrinkage: 5 pseudo-matches pull every team toward the league, which is right for a single call's squared error but leaves strength gaps understated. By the registered rule, plans show the chances with this stated.

### Decision

- Plans show expected goals for both sides and the three chances, with the note that big favourites are understated.
- Not done: re-tuning the shrinkage to fix calibration. That would be fitting on the data just used for the test; it needs its own registered test on held-out seasons.
- Not done: any comparison with bookmaker odds.

## Pre-registered: fixing the too-cautious chances (written 2026-11-16, before running)

**The fix, one number.** Before the threat calls are turned into chances, each side's departure from the league average is stretched: threat used = league + s x (threat call - league), with s at least 1. Nothing else changes. The threat call shown in plans and its skill are untouched; only the chances move.

**Held-out design.**

- Each competition-season is assigned by a hash of its key ("competitionid_seasonid"): md5 as a number, even = lockbox, odd = tuning. Fixed by the hash, not by me.
- s is chosen on the tuning seasons only, from the grid 1.0, 1.1, ..., 2.0, as the value with the lowest RPS.
- The lockbox seasons are then scored once with that s, against s = 1.

**Bars, on the lockbox only.**

1. **Sharper:** RPS with the chosen s is below RPS with s = 1, with the 90% interval of the difference above 0 (resampling whole matches 500 times).
2. **Calibrated:** no bin with at least 100 predictions is off by more than 5 points.

**Decision rule.** Plans adopt s only if bar 1 passes. The "too cautious" note in plans is removed only if bar 2 also passes. If the chosen s is 1.0, or the lockbox has fewer than 300 matches, nothing changes and the result is reported as it is.

**Disclosure.** The problem itself was seen on all 13 seasons, lockbox included, so the direction of the fix is not blind. Its size is.

**Stated expectation:** s between 1.2 and 1.5; bar 1 passes narrowly; bar 2 uncertain, because the lockbox bins are small.

### Result (2026-11-16, run exactly as registered): the fix FAILS on the lockbox; nothing changes

Tuning: 7 seasons (WSL 2019/20 and 2023/24, Indian Super League 2021/22, La Liga, Premier League and Serie A 2015/16, Serie A Women 2023/24). Lockbox: 6 seasons, 558 matches (WSL 2018/19 and 2020/21, Frauen Bundesliga, Liga F and NWSL 2023, Ligue 1 2015/16).

- **Tuning chose s = 1.4**, inside the range I expected. But the gain there was small: RPS 0.1895 to 0.1870.
- **Lockbox, bar 1 (sharper): fail.** RPS 0.1896 without the stretch, 0.1913 with it; difference -0.0017 (-0.0045 to +0.0011). The stretch made the chances slightly worse, not better.
- **Lockbox, bar 2 (calibrated): fail.** Worst gap 8.1 points without the stretch, 14.7 with it.

| Chance given | Without: given | Without: happened | With s = 1.4: given | With: happened |
|---|---|---|---|---|
| under 20% | 12.5% | 8.6% | 10.2% | 12.7% |
| 20 to 30% | 25.1% | 27.8% | 24.9% | 28.9% |
| 30 to 40% | 34.6% | 32.2% | 34.6% | 30.9% |
| 40 to 50% | 44.8% | 44.0% | 45.2% | 47.3% |
| 50 to 60% | 54.5% | 47.1% | 54.8% | 40.2% |
| over 60% | 74.6% | 82.6% | 79.3% | 75.0% |

**Reading.**

- By the registered rule the plans keep s = 1 and keep their note.
- The miscalibration is real in size (gaps of 4 to 8 points) but **not a simple, stable "too cautious" pattern**. In the lockbox, strong favourites are understated (75% given, 83% happened) while moderate favourites are overstated (55% given, 47% happened). One stretch cannot fix both, and it overshoots at the top.
- My explanation for the first result (shrinkage understates every gap) was too simple. More likely the leagues differ: a number that fits unequal leagues is wrong for even ones.
- **What the chances are good for:** ranking outcomes and beating base rates by 18%. **What they are not good for:** being read as exact to within 5 to 8 points.
- Stopping here. No second attempt on this lockbox; a better model (per-league spread, or a rating that updates) would need new held-out data.
