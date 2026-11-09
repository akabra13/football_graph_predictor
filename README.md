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
python -m pytest tests -q
```

`--stream` analyses one competition-season in memory. The full lake lives on Google Drive (`PITCHGRAPH_DATA`) and is built and refreshed by the workflows in `.github/workflows/`; no data is stored in this repo or on a laptop.

> **Data source: StatsBomb.** This project uses [StatsBomb Open Data](https://github.com/statsbomb/open-data). Any published analysis derived from it must credit StatsBomb and display their logo, per the open-data licence.
