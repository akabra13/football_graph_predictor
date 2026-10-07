"""Build the PitchGraph Library: one JSON file per competition-season plus an index.

    library/
      index.json             every season and team, the global style map
      seasons/<key>.json     team pages and all matchups for one season

The value model is fitted once on every competition in the lake, then each
competition-season is analysed on its own and written immediately, so memory
stays bounded by the largest season and a dropped Colab session resumes where
it stopped (existing season files are skipped unless `force`).

Only competition-seasons where at least MIN_TEAMS teams have MIN_MATCHES
matches are included: league comparisons need a league. That keeps every
complete league and the later stages of tournaments, and leaves out the
single-club seasons (e.g. Barcelona's matches only), where "rank among the
league" would mean nothing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import polars as pl

from pitchgraph.analysis.context import prepare
from pitchgraph.analysis.season import MIN_MATCHES, Season
from pitchgraph.chains import fingerprint
from pitchgraph.data.lake import Lake
from pitchgraph.value.markov import MarkovValue

MIN_TEAMS = 4


def eligible_seasons(lake: Lake) -> pl.DataFrame:
    m = lake.matches()
    long = pl.concat([
        m.select("competition_id", "season_id", "competition", "season", "gender",
                 pl.col("home_team_id").alias("team_id")),
        m.select("competition_id", "season_id", "competition", "season", "gender",
                 pl.col("away_team_id").alias("team_id")),
    ])
    per_team = long.group_by("competition_id", "season_id", "competition", "season", "gender",
                             "team_id").len()
    return (per_team.filter(pl.col("len") >= MIN_MATCHES)
                    .group_by("competition_id", "season_id", "competition", "season", "gender")
                    .agg(teams=pl.len())
                    .filter(pl.col("teams") >= MIN_TEAMS)
                    .with_columns(key=pl.concat_str(["competition_id", "season_id"], separator="_"))
                    .sort("competition", "season"))


def player_names(lake: Lake) -> dict:
    if not lake.has("lineups"):
        return {}
    lu = lake.scan("lineups").select("player_id", "nickname").drop_nulls().unique("player_id").collect()
    return dict(lu.iter_rows())


def fit_value_model(lake: Lake) -> MarkovValue:
    events = lake.events()
    return MarkovValue().fit(events.filter(pl.col("team_id") == pl.col("possession_team_id")))


def build_season(lake: Lake, row: dict, model: MarkovValue, names: dict) -> tuple[dict, Season]:
    cid, sid = row["competition_id"], row["season_id"]
    events = lake.events().filter((pl.col("competition_id") == cid) & (pl.col("season_id") == sid))
    ev = prepare(events, model)
    lineups = None
    if lake.has("lineups"):
        ids = ev["match_id"].unique()
        lineups = lake.scan("lineups").filter(pl.col("match_id").is_in(ids)).collect()
    meta = {k: row[k] for k in ("key", "competition", "season", "gender")}
    season = Season(ev, meta, names, lineups)
    return season.to_json(), season


def _dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str),
                   encoding="utf-8")
    tmp.replace(path)


def build_all(lake: Lake, out: Path, keys: list[str] | None = None, force: bool = False,
              log=print) -> dict:
    t0 = time.time()
    seasons = eligible_seasons(lake)
    if keys:
        seasons = seasons.filter(pl.col("key").is_in(keys))
    log(f"{seasons.height} competition-seasons; fitting the value model on everything")
    model = fit_value_model(lake)
    names = player_names(lake)

    index_path = out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"seasons": {}}
    for row in seasons.iter_rows(named=True):
        path = out / "seasons" / f"{row['key']}.json"
        if path.exists() and not force and row["key"] in index["seasons"]:
            log(f"  {row['competition']} {row['season']}: already built")
            continue
        t = time.time()
        js, season = build_season(lake, row, model, names)
        _dump(js, path)
        index["seasons"][row["key"]] = {
            "key": row["key"], "competition": row["competition"], "season": row["season"],
            "gender": row["gender"], "kappa": js["kappa"],
            "teams": [{"id": int(tid), "name": p["name"], "matches": p["matches"],
                       "small_sample": p["small_sample"]} for tid, p in js["teams"].items()],
        }
        save_chains(season, out / "chains" / f"{row['key']}.npz")
        _dump(index, index_path)
        log(f"  {row['competition']} {row['season']}: {len(js['teams'])} teams "
            f"({time.time() - t:.0f}s, {path.stat().st_size / 1024:.0f} KB)")

    # Built from every season's saved chains, so a resumed run still maps all.
    chains = load_chains(out / "chains")
    if chains:
        index["style_map"] = style_map(chains)
    index["built"] = time.strftime("%Y-%m-%d")
    index["value_model"] = f"{model.name}, {model.nx}x{model.ny} zones"
    _dump(index, index_path)
    log(f"done in {time.time() - t0:.0f}s")
    return index


def save_chains(season: Season, path: Path):
    """Each team's attacking flow graph, so the style map can be rebuilt later."""
    ids = season.eligible
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path, team_ids=np.array(ids), names=np.array([season.teams[t] for t in ids]),
        P=np.stack([season.attack[t].P for t in ids]), g=np.stack([season.attack[t].g for t in ids]),
        start=np.stack([season.attack[t].start for t in ids]),
        x_edges=np.array(season.grid.x_edges), y_edges=np.array(season.grid.y_edges))


def load_chains(folder: Path) -> dict:
    from pitchgraph.chains.grid import Grid
    from pitchgraph.chains.team import Chain
    out = {}
    for f in sorted(folder.glob("*.npz")):
        d = np.load(f, allow_pickle=False)
        grid = Grid(tuple(d["x_edges"].tolist()), tuple(d["y_edges"].tolist()))
        for k, tid in enumerate(d["team_ids"].tolist()):
            out[(f.stem, tid)] = (str(d["names"][k]), Chain(d["P"][k], d["g"][k], d["start"][k], grid))
    return out


def style_map(chains: dict) -> dict:
    """Every team-season on one map, by flow-graph distance.

    Exploratory: fingerprints are validated WITHIN a season (re-identification),
    while distances across leagues and eras also carry league-wide differences.
    """
    keys = list(chains)
    D = fingerprint.distance_matrix([chains[k][1] for k in keys])
    xy = fingerprint.mds(D)
    points, nearest = [], {}
    for i, (season, tid) in enumerate(keys):
        points.append({"season": season, "team_id": tid, "name": chains[keys[i]][0],
                       "x": round(float(xy[i, 0]), 5), "y": round(float(xy[i, 1]), 5)})
        order = [j for j in np.argsort(D[i]) if j != i][:5]
        nearest[f"{season}:{tid}"] = [{"season": keys[j][0], "team_id": keys[j][1],
                                       "name": chains[keys[j]][0], "distance": round(float(D[i, j]), 5)}
                                      for j in order]
    return {"points": points, "nearest": nearest}
