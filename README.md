# PitchGraph

**Scout a football team as a graph.** Pitch regions are nodes; from each one a team moves the ball along an edge, shoots, or loses it. Solving that absorbing Markov chain gives the chance a possession ends in a goal, and operations on the graph answer what a coach asks.

Built on open data only. Every claim is pre-registered or tested, and failures are reported as plainly as successes.

## What it does

| Question | Graph operation |
|---|---|
| How do they play, and who plays like them? | Their flow graph against the league's; a fingerprint distance between graphs |
| How do we stop them? | Remove a link or a player and re-solve: threat lost, as a range from "they adapt" to "they lose the ball" |
| Where are they vulnerable? | The same planner on what opponents do against them |
| What happens when A plays B? | A's habits with B's leakiness, edge by edge |

## Headline results

- **Style is a fingerprint.** Half a team's matches identify its other half among the whole league: 90% (Premier League 15/16), 95% (Serie A 15/16), 75% (Liga F 23/24); chance is 5-9%.
- **Matchups change *where* a team attacks, not *how much*.** Lane predictions improve with the matchup model in four of five leagues; threat volume does not.
- **Player removal is a weak forecast** (r = 0.08 over 781 real absences), so the Library shows "who the threat runs through", not predictions.
- **Pre-match calls hold.** Nine things about a team's next match (share of the ball, giveaways, entries into the central final third, how high it wins the ball, and more), called only from earlier matches, beat the league average for all nine across 2,741 team-matches and 181 teams. Possession calls remove 65% of the error. Lane-by-lane entry calls do not hold and were dropped. See [docs/predictability_audit.md](docs/predictability_audit.md).
- **Result calls hold, roughly.** Expected chance creation for each side (skill 0.30) turned into win, draw and loss chances beats the league's usual rates by 18% over 1,357 matches, with nothing fitted. The chances are off by 4 to 8 points in places, and a one-number correction failed on held-out seasons, so it was not adopted. See [docs/result_calls.md](docs/result_calls.md).
- **Set pieces: volume is knowable, quality is not.** Corners (skill 0.17), set-piece shots (0.11) and set-piece xG (0.07) can be called before kick-off; shots per corner cannot. See [docs/set_pieces.md](docs/set_pieces.md).
- **Instructions are about the opponent, not the team.** Each line in a plan fires when a call differs from a normal week for that team, and the situation it is written for then occurs 63 to 89% of the time (18 of 18 rules hold over 2,741 team-matches). See [docs/strategy.md](docs/strategy.md).
- **Whether following a plan helps is not shown.** Five instructions could be checked against what teams did while the score was level; none showed evidence either way. Pressing high goes with better outcomes whether or not the plan asks for it. See [docs/followed.md](docs/followed.md).
- **The main lever is real, the rest of the plan is not proven.** Passes from a half-space into the centre of the final third are worth 12-14% of a team's threat in real matches, as the planner says; its ranking of smaller links and its team-specific numbers did not pass. See [docs/denial_test.md](docs/denial_test.md).
- **Data:** 80 competition-seasons, 3,960 matches, 13.9M events, refreshed weekly by GitHub Actions.

Full method, tables and history: [docs/lab_notebook.md](docs/lab_notebook.md).

## The programme

| Project | Status |
|---|---|
| **PitchGraph** (this repo) | Flow graphs, denial planner, matchups, Library |
| [dynamic_shift](https://github.com/akabra13/dynamic_shift) | "When did a match change tactically?" Negative result across five feature families; a further identity-aware attempt is pre-registered |
| [rolefit](https://github.com/akabra13/rolefit) | Player traits, how teams use them, what a team needs; men and women kept separate |

## Run it

```bash
pip install -e ".[dev]"
pitchgraph teams --search "arsenal"
pitchgraph report "Leicester City" 2015/16 --stream --out leicester.html
pitchgraph matchup "Arsenal" "Leicester City" 2015/16 --stream
python scripts/season_replay.py "Leicester City" 2015/16 --competition "Premier League" --out out/replay
python -m pytest tests -q
```

`--stream` analyses one competition-season in memory. The full lake lives on Google Drive (`PITCHGRAPH_DATA`) and is built and refreshed by the workflows in `.github/workflows/`; no data is stored in this repo or on a laptop.

> **Data source: StatsBomb.** This project uses [StatsBomb Open Data](https://github.com/statsbomb/open-data). Any published analysis derived from it must credit StatsBomb and display their logo, per the open-data licence.
