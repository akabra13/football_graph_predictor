# football_graph_predictor — PitchGraph

Scouting football teams with graph theory, on open data. Every team is a **flow
graph**: pitch regions are the nodes, and from each one a team moves the ball
along an edge, shoots, or loses it. Solving that absorbing Markov chain gives the
chance a possession ends in a goal, and operations on the graph answer the
questions a coach actually asks:

| Question | Graph operation |
|---|---|
| **How do they play, and who plays like them?** | Their flow graph against the league's; a fingerprint distance between graphs |
| **How do we stop them?** | Remove a link or a player from the graph and re-solve: the threat that disappears, as a range from "they adapt" to "they lose the ball" |
| **Where are they vulnerable?** | The same planner on what opponents do against them |
| **What happens when A plays B?** | A's habits with B's leakiness applied edge by edge |

The results are browsable in the **PitchGraph Library**: search any team,
open its report, plan a matchup, or explore the style map.

> **Data source: StatsBomb.** This project uses
> [StatsBomb Open Data](https://github.com/statsbomb/open-data). Any published
> analysis derived from it must credit StatsBomb and display their logo, per the
> open-data licence.

## What has been validated

Every claim the Library makes is tested, and the results are reported whichever
way they came out. The numbers below come from leagues streamed during
development; `notebooks/02_library.ipynb` reruns everything on all 12 complete
league seasons and writes the results into the Library's Method page.

**Style is real.** A team's flow graph from half its matches identifies its own
other half among every team in the league:

| League | Identified | Chance |
|---|---|---|
| Premier League 2015/16 | 90% | 5% |
| Serie A 2015/16 | 95% | 5% |
| Liga F 2023/24 | 75% | 6% |
| WSL 2018/19 | 64% | 9% |
| WSL 2020/21 | 50% | 8% |

The grid behind this was chosen on evidence: a 12×8 grid fitted noise (25%
re-identification, almost no held-out gain over the league average), while a
coarse grid aligned with the five tactical lanes generalises. How strongly each
team is pulled toward its league (κ) is chosen by held-out likelihood, never by
the re-identification test, and came out at 1000 in every league.

**Matchups change *where* a team attacks, not *how much*.** Each match is
predicted from the other matches only. Ranges are 90% intervals over matches;
positive means the matchup model beat the comparison:

| League | Lanes: matchup vs own habits | Threat volume: matchup vs strength alone |
|---|---|---|
| Premier League 15/16 | +0.0014 to +0.0027 | −0.0008 to +0.0021 |
| Serie A 15/16 | +0.0007 to +0.0021 | −0.0034 to −0.0001 |
| WSL 20/21 | +0.0002 to +0.0028 | −0.0051 to +0.0002 |
| WSL 18/19 | +0.0012 to +0.0029 | −0.0086 to +0.0002 |
| Liga F 23/24 | −0.0004 to +0.0013 | −0.0023 to +0.0050 |

How much threat a team creates is attack strength × how much the defence
concedes; the edge-by-edge interaction adds nothing to that. Where it comes from
does shift with the opponent's defensive pattern, modestly but consistently. This
is the first properly powered test of the idea the project started from (v1's
test had 32 teams and found nothing). The Library's matchup view follows the
result: lanes from the matchup model, volume from strength alone.

**Player effects are weak.** Removing a player from the player-level flow graph
predicts how much threat the team loses without them. Across 781 real absences
(Premier League and Serie A 2015/16, opponent-adjusted), predicted and observed
drops agree only weakly: r = 0.08, p = 0.01. The Library presents player levers
as "who the threat runs through", not as forecasts.

**The possession value model** (absorbing chain over a 16×12 grid, fitted on all
competitions) ranks situations as well as the direct per-zone estimate when data
is plentiful, and better when it is thin (correlation 0.219 vs 0.189 on 5
training matches), across men's and women's leagues held out whole.

## Using it

**The Library** (Colab + Drive): run `notebooks/01_ingest.ipynb` once to build the
data lake, then `notebooks/02_library.ipynb` to validate and build the Library.

**From the command line**, by team name:

```bash
pip install -e ".[dev]"
pitchgraph teams --search "arsenal"
pitchgraph report "Leicester City" 2015/16 --stream --out leicester.html
pitchgraph matchup "Arsenal" "Leicester City" 2015/16 --stream
```

`--stream` analyses one competition-season in memory; without it, commands use
the Drive lake (needs `PITCHGRAPH_DATA`). A full season takes about 30 seconds.

**Tests:** `python -m pytest tests -q` (synthetic fixtures; no data needed).

## No data is stored on the local machine

The repo holds code only. Data lives on **Google Drive** and heavy work runs in
**Colab**. One setting names the data root:

```
PITCHGRAPH_DATA=/content/drive/MyDrive/pitchgraph   # Colab + Drive (normal)
PITCHGRAPH_DATA=E:/pitchgraph                        # a USB drive, later
```

With it unset, nothing is written anywhere: downloads stay in memory, and anything
that needs the lake refuses to run (`tests/test_storage.py` enforces this). The
lake is ~1.7 GB of Parquet; raw JSON is streamed straight into it and never saved.

## Layout

```
src/pitchgraph/
  config.py              where data lives (nowhere locally by default)
  cli.py                 pitchgraph teams | report | matchup | library
  data/                  open-data reader, lake ingest, 360 frames, possessions
  value/                 absorbing-Markov possession value + its evaluation
  chains/                team flow graphs: grid, counts, shrinkage, denial,
                         fingerprint, matchup, player chains, validation suite
  analysis/              per-match ledger, league-relative claims with bootstrap
                         confidence, report sections, Season (one league, analysed once)
  library/               JSON build, the browsable app, report packaging
  graphs/                descriptive graphs: passing, co-pressing, routes
  geometry/              v1: fitted pass/shot models, defensive-shape features
  legacy/                v1 routing and ability code (documented negative results)
notebooks/               01_ingest, 02_library (Colab)
tests/
```

## Roadmap

1. **PitchGraph v3** (this release): flow graphs, the denial planner, matchups,
   the Library.
2. **TurningPoint**: when did a match change, what changed, and what probably
   caused it. Online change-point detection on each team's flow graph, validated
   against ~2,000 genuine formation changes (StatsBomb Tactical Shift events).
3. **RoleFit**: who plays a player's role, and who could do it in another
   system. Validated by recognising the same player across club and country.

## History

**v1 (vulnerability engine, StatsBomb 360).** Geometric features of the defensive
shape lifted shot prediction over ball position (AUC 0.793 → 0.807, grouped by
match), and the fitted pass model reached AUC 0.882 on 20,354 passes. Two headline
ideas failed. Min-cost routing through a "resistance graph" predicted nothing beyond
ball position (residual AUC 0.493). The vulnerability × ability interaction test
on the 2022 World Cup found nothing once significance used the correct
team-level null: an apparent p = 0.016 became p = 0.085, because 95,160 snapshots
carry only 32 independent team profiles.

**v2 (opposition report).** League-relative claims with bootstrap-by-match
confidence. Bugs caught by tests and checks along the way: a null-unsafe filter
that silently dropped 92% of passes; bootstrap intervals that excluded their own
estimate, because resampled matches were not relabelled; and a build-up success
rate inflated by only counting possessions that had already left the defensive
third. v3's ledger fixes the last one, so v2's published Leicester figure (53.8%)
was too high.

**Data facts that shaped the design** (verified against the data): 360 freeze-frame
players are anonymous, so shape is measurable but motion is not. Coordinates are
relative to the *event* team, and ~19% of events are made by the team out of
possession, so frames must be mirrored (`tests/test_frames.py`). Freeze-frame
visibility follows the broadcast camera, so off-camera means unobserved, not
empty. `play_pattern` labels how a possession began, not what an event is.

## Method commitments

- **Every number is compared with its league.** Claims are ranked against every
  team in the same competition-season, with 90% intervals from resampling whole
  matches and a confidence label from interval and split-half agreement.
- **Predictions are made only from data the prediction could have had.** Halves
  are disjoint; matchups, absences and shrinkage weights are leave-one-match-out.
- **Bounds instead of point guesses when behaviour is unknown.** Denials report
  "they adapt" to "they lose the ball", because the data cannot say which.
- **Negative results are reported as plainly as positive ones.**
