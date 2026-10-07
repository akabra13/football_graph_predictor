"""Team flow graphs on chains small enough to solve by hand."""
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pitchgraph.chains import denial, fingerprint, matchup  # noqa: E402
from pitchgraph.chains.counts import CountStore  # noqa: E402
from pitchgraph.chains.grid import TACTICAL, Grid  # noqa: E402
from pitchgraph.chains.team import Chain, league_chain, select_kappa, shrunk_chain  # noqa: E402


def line_chain() -> Chain:
    """Three zones in a row (nx=3, ny=1): build-up -> middle -> shooting zone.

    zone 0: move to 1 with 0.5, else lose      V0 = 0.5 * V1 = 0.025
    zone 1: move to 2 with 0.5, else lose      V1 = 0.5 * V2 = 0.05
    zone 2: shoot with 0.5 (xG 0.2), else lose V2 = 0.5 * 0.2 = 0.1
    Columns: move to 0, 1, 2, shoot, lose.
    """
    P = np.array([[0, .5, 0, 0, .5],
                  [0, 0, .5, 0, .5],
                  [0, 0, 0, .5, .5]], dtype=float)
    return Chain(P, np.array([0, 0, .2]), np.array([1.0, 0, 0]), Grid.uniform(3, 1))


def fork_chain() -> Chain:
    """nx=3, ny=2: zone index = column * 2 + row. Middle zone 2 can reach
    either of two identical shooting zones (4 and 5)."""
    n = 6
    P = np.zeros((n, n + 2))
    P[0, 2] = 0.6; P[0, n + 1] = 0.4
    P[1, 2] = 0.6; P[1, n + 1] = 0.4
    P[2, 4] = 0.3; P[2, 5] = 0.3; P[2, n + 1] = 0.4
    P[3, n + 1] = 1.0
    for z in (4, 5):
        P[z, n] = 0.5; P[z, n + 1] = 0.5
    g = np.array([0, 0, 0, 0, .2, .2])
    return Chain(P, g, np.array([1.0, 0, 0, 0, 0, 0]), Grid.uniform(3, 2))


def test_chain_values_and_threat_match_the_hand_solution():
    c = line_chain()
    assert c.values == pytest.approx([0.025, 0.05, 0.1])
    assert c.threat == pytest.approx(0.025)


def test_expected_visits():
    assert line_chain().visits() == pytest.approx([1.0, 0.5, 0.25])


def test_denying_the_only_route_to_goal_removes_all_threat_under_both_bounds():
    c = line_chain()
    blocked = np.zeros((3, 3), bool); blocked[1, 2] = True
    assert denial.deny(c, blocked, adapt=False).threat == pytest.approx(0.0)
    # No alternative move exists from zone 1, so adapting cannot help either.
    assert denial.deny(c, blocked, adapt=True).threat == pytest.approx(0.0)


def test_full_adaptation_uses_an_equally_good_alternative():
    c = fork_chain()
    blocked = np.zeros((6, 6), bool); blocked[2, 4] = True
    assert denial.deny(c, blocked, adapt=True).threat == pytest.approx(c.threat)
    assert denial.deny(c, blocked, adapt=False).threat == pytest.approx(c.threat / 2)


def test_denied_chains_stay_row_stochastic():
    c = fork_chain()
    blocked = np.zeros((6, 6), bool); blocked[2, 4] = blocked[0, 2] = True
    for adapt in (True, False):
        assert denial.deny(c, blocked, adapt).P.sum(1) == pytest.approx(np.ones(6))


def test_plan_ranks_the_route_that_matters():
    c = line_chain()
    usage = np.zeros((3, 3)); usage[0, 1] = 10; usage[1, 2] = 5
    out = denial.plan(c, usage, top=3)
    # Both links are on the only path, so each denial removes all threat.
    assert out["links"][0]["drop_no_adapt"] == pytest.approx(1.0)


def _counts():
    league = line_chain()
    C = np.array([[0, 20, 0, 0, 30], [0, 0, 5, 0, 5], [0, 0, 0, 4, 1]], dtype=float)
    return league, C, np.array([0, 0, 1.2]), np.array([50.0, 0, 0])


def test_infinite_shrinkage_returns_the_league_chain():
    league, C, xg, st = _counts()
    team = shrunk_chain(C, xg, st, league, kappa=1e12)
    assert team.P == pytest.approx(league.P, abs=1e-9)


def test_zero_shrinkage_returns_the_raw_team_chain():
    league, C, xg, st = _counts()
    team = shrunk_chain(C, xg, st, league, kappa=0.0)
    assert team.P == pytest.approx(C / C.sum(1, keepdims=True))


def test_fingerprint_distance_is_zero_to_self_and_symmetric():
    a, b = line_chain(), fork_chain()
    assert fingerprint.distance(a, a) == pytest.approx(0.0)
    c = shrunk_chain(np.array([[0, 5, 0, 0, 1], [0, 0, 1, 0, 4], [0, 0, 0, 1, 1]], float),
                     np.zeros(3), np.array([1.0, 0, 0]), a, kappa=1.0)
    assert fingerprint.distance(a, c) == pytest.approx(fingerprint.distance(c, a))
    assert 0 < fingerprint.distance(a, c) <= 1


def test_reidentify_finds_identical_teams():
    base = line_chain()
    teams = [shrunk_chain(np.array([[0, k, 0, 0, 10 - k], [0, 0, 5, 0, 5], [0, 0, 0, 5, 5]], float),
                          np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), base, kappa=0.0)
             for k in (1, 5, 9)]
    out = fingerprint.reidentify(teams, teams)
    assert out["top1"] == 1.0 and out["chance_top1"] == pytest.approx(1 / 3)


def test_matchup_against_an_average_defence_is_the_attack_itself():
    a, league = fork_chain(), fork_chain()
    m = matchup.matchup_chain(a, league, league)
    assert m.P == pytest.approx(a.P) and m.threat == pytest.approx(a.threat)


def test_matchup_against_a_leaky_defence_raises_threat():
    a, league = fork_chain(), fork_chain()
    leaky = league.with_P(league.P.copy())
    leaky.P[2, 4] *= 2; leaky.P[2, 5] *= 2; leaky.P[2, 7] = 1 - leaky.P[2, :7].sum()
    assert matchup.matchup_chain(a, leaky, league).threat > a.threat


def test_entry_lanes_are_a_distribution():
    shares = matchup.entry_lanes(fork_chain())
    assert shares.sum() == pytest.approx(1.0) and (shares >= 0).all()


def _events():
    """Two matches, two teams, on a 3x1 grid, as Lake.events() would supply."""
    rows = []
    for m in (1, 2):
        for team, opp, poss in ((10, 20, 1), (20, 10, 2)):
            base = dict(match_id=m, team_id=team, possession_team_id=team, possession=poss,
                        home_team_id=10, away_team_id=20, period=1, play_pattern="Regular Play",
                        outcome=None, xg=None, sub_type=None, end_y=40.0, y=40.0)
            rows += [
                {**base, "idx": 1, "type": "Pass", "x": 20.0, "end_x": 60.0},
                {**base, "idx": 2, "type": "Carry", "x": 60.0, "end_x": 100.0},
                {**base, "idx": 3, "type": "Shot", "x": 100.0, "end_x": None, "xg": 0.3},
            ]
    return pl.DataFrame(rows, infer_schema_length=None).lazy()


def test_count_store_keeps_matches_separate_and_sides_consistent():
    store = CountStore.from_events(_events(), Grid.uniform(3, 1))
    att = store.team(10, "attack")
    assert list(att.match_ids) == [1, 2]
    C, xg, st = att.total()
    assert C[0, 1] == 2 and C[1, 2] == 2 and C[2, 3] == 2 and xg[2] == pytest.approx(0.6)
    assert st[0] == 2
    # Team 10's conceded counts are team 20's attacking counts.
    assert np.array_equal(store.team(10, "conceded").C, store.team(20, "attack").C)


def test_select_kappa_returns_a_grid_value():
    store = CountStore.from_events(_events(), Grid.uniform(3, 1))
    C, xg, st = store.league_total()
    prior = league_chain(C, xg, st, store.grid)
    k, scores = select_kappa([store.team(10), store.team(20)], prior, grid=(1.0, 10.0))
    assert k in (1.0, 10.0) and all(np.isfinite(v) for v in scores.values())


def test_tactical_grid_rows_are_the_five_lanes_and_index_paths_agree():
    from pitchgraph.graphs.routes import LANE_EDGES
    assert TACTICAL.n == 30 and TACTICAL.ny == 5
    xs = np.array([5.0, 25, 45, 65, 85, 105, 119, 79.9, 80.0])
    ys = np.array([5.0, 20, 40, 55, 70, 29.9, 30.0, 61.9, 62.0])
    np_idx = TACTICAL.index(xs, ys)
    pl_idx = pl.DataFrame({"x": xs, "y": ys}).select(
        TACTICAL.index_expr(pl.col("x"), pl.col("y"))).to_series().to_numpy()
    assert np.array_equal(np_idx, pl_idx)
    lanes = np_idx % TACTICAL.ny
    assert list(lanes) == list(np.searchsorted(LANE_EDGES, ys, side="right"))


def test_denial_regions_on_the_tactical_grid_cover_thirds_and_lanes():
    regions = denial.zone_regions(TACTICAL)
    assert sorted(set(regions.tolist())) == list(range(15))
    assert denial.region_name(int(regions[-1])) == "right flank, final third"


def test_plan_flags_unusual_dependencies_against_the_league():
    """The team reaches goal only via 0 -> 2 -> 4; the league also has a second
    route 0 -> 3 -> 5, so both links on the team's only route are unusual
    dependencies."""
    n = 6

    def chain(routes):
        P = np.zeros((n, n + 2))
        for (a, b), p in routes.items():
            P[a, b] = p
        for z in (4, 5):
            P[z, n] = 0.5
        P[:, n + 1] = 1 - P.sum(1)
        return Chain(P, np.array([0, 0, 0, 0, .2, .2]), np.array([1.0, 0, 0, 0, 0, 0]),
                     Grid.uniform(3, 2))

    team = chain({(0, 2): 0.6, (2, 4): 0.6})
    league = chain({(0, 2): 0.3, (0, 3): 0.3, (2, 4): 0.6, (3, 5): 0.6})
    usage = np.zeros((n, n)); usage[0, 2] = usage[2, 4] = 10
    out = denial.plan(team, usage, reference=league, min_usage=0.0)
    assert set(out["links"][0]) >= {"league_drop_adapt", "league_drop_no_adapt", "excess"}
    first, second = out["unusual_links"][:2]
    # 0 -> 2 is the most unusual: an average team simply reroutes via zone 3
    # (no loss under full adaptation), while this team loses everything.
    # Excess = midpoint(1.0, 1.0) - midpoint(0.0, 0.5) = 0.75.
    assert first["from"] == denial.region_name(int(denial.zone_regions(team.grid)[0]))
    assert first["excess"] == pytest.approx(0.75)
    # 2 -> 4: the league has no alternative from zone 2 either, but only half
    # its threat goes that way. Excess = 1.0 - 0.5 = 0.5.
    assert second["league_drop_adapt"] == pytest.approx(0.5)
    assert second["excess"] == pytest.approx(0.5)