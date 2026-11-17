# Blind test: the frozen version on data nobody has seen

Every result in this repository comes from the same 80 competition-seasons, and every design choice was made while looking at them. Pre-registration limits that; it does not remove it. The only clean test is data that did not exist when the code was written.

StatsBomb adds competition-seasons to its open data from time to time. This fixes the code now, so that whatever arrives next is scored by a version that could not have been shaped by it.

## Pre-registered (written 2026-11-16, before any unseen data exists)

### What is frozen

- **The code:** git tag `prematch-v1`. The blind test always runs that tag, whatever has changed on `main` since.
- **What counts as seen:** the 80 competition-seasons in StatsBomb's list on 2026-11-16, recorded in [frozen_seasons.json](frozen_seasons.json). Anything not in that list is unseen.
- A later version (`prematch-v2`, ...) carries its own list. It is blind only for seasons released after its own tag.

### What is scored

The unseen competition-seasons that pass the pooled replay's rule (at least 8 teams with 10 matches), pooled together. Same units as always: the later half of each team's fixtures, at least 5 earlier matches, earlier dates only.

Three claims, each with the bar it passed on seen data:

| Claim | Bar | On seen data |
|---|---|---|
| **Threat call** (non-penalty xG) | Skill against the league average has a 90% interval above 0 | 0.296 (0.268 to 0.323) |
| **Result call** (home / draw / away chances) | RPS below the base rates', 90% interval of the difference above 0 | 0.1896 against 0.2321 |
| **Instructions** (all 18 opponent-specific rules together) | Of every instruction issued, the situation occurred in at least 60%, with the 90% interval above 50% | 63 to 89% by rule |

Intervals by resampling whole matches 500 times.

Reported without a verdict: each of the twelve tactical and set-piece calls shown in a plan, each rule on its own, and calibration of the chances. A single new season is too small to judge these one at a time (a call needs about 1,000 team-matches, a rule 100 fires).

### Reading rules

- **No verdict below 300 scored team-matches** (about one and a half league seasons). Smaller releases are reported and kept; unseen seasons accumulate, and the verdict is read the first time the pooled total reaches 300. Later runs are reported as updates, not as second attempts.
- **A claim that fails is withdrawn** from the README's headline until a later frozen version passes on data released after its own tag.
- **Nothing is tuned on unseen seasons before their blind result is recorded here.** After that they join the seen set for the next version.
- Tournaments and single-club releases fail the 8-teams rule and are skipped. They are listed, not scored.

### Stated expectations

- All three hold. The method has no fitted parameters beyond a shrinkage constant, so there is little to overfit.
- Threat skill between 0.15 and 0.40: it ranged widely by league on seen data, and one new league could sit anywhere in that.
- Result call 10 to 20% better than base rates; favourites still given a few points too little.
- Instructions occur 65 to 75% of the time.
- The most likely way to be wrong: a league unlike any seen one (very lopsided, or very even), where the league-average baseline behaves differently.
- This may take a long time. StatsBomb's recent releases have mostly been tournaments, which cannot be scored.

### How it runs

`.github/workflows/blind_test.yml` runs weekly, after the ingest. It checks out `prematch-v1`, compares StatsBomb's list with the frozen one, and scores what is new with `scripts/blind_test.py`. When it scores something it opens an issue on this repository with the output. Nothing is stored anywhere else.

`--rehearse` treats seasons already seen as new, to check that the script runs. Its output is marked as a rehearsal and says nothing about unseen data.

## Rehearsal (2026-11-16, on seen data, not a result)

Pending.

## Results

None yet. No competition-season has been released since the freeze.
