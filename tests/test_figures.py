"""Post figures render at Twitter sizes, every kind, with no data needed."""
import json
from pathlib import Path

import matplotlib.image as mpimg
import pytest

from pitchgraph.figures import render

POSTS = Path(__file__).resolve().parents[1] / "posts"


@pytest.mark.parametrize("spec_path", sorted(POSTS.glob("*.json")), ids=lambda p: p.stem)
def test_every_post_spec_renders_at_16_9(spec_path, tmp_path):
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    for key in ("id", "kind", "title", "note", "caption"):
        assert spec.get(key), f"{spec_path.name} needs a {key}"
    out = render(spec, tmp_path)
    h, w = mpimg.imread(out).shape[:2]
    assert (w, h) == (1600, 900)


def test_pitch_shapes_square(tmp_path):
    spec = {"id": "shape", "kind": "pitch_shapes", "size": "square", "title": "t",
            "shapes": [{"label": "back four", "points": [[20, y, ""] for y in (10, 30, 50, 70)]},
                       {"label": "back three", "points": [[25, y, "CB"] for y in (20, 40, 60)]}]}
    h, w = mpimg.imread(render(spec, tmp_path)).shape[:2]
    assert (w, h) == (1200, 1200)


def test_unknown_kind_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        render({"id": "x", "kind": "pie", "title": "t"}, tmp_path)


def test_flow_map_from_a_chain(tmp_path):
    import numpy as np

    from pitchgraph.chains.grid import TACTICAL
    from pitchgraph.chains.team import league_chain, shrunk_chain
    from pitchgraph.figures.flow import flow_data, flow_map

    rng = np.random.default_rng(0)
    n = TACTICAL.n
    c = TACTICAL.centres()
    C = rng.poisson(20, size=(n, n + 2)).astype(float)
    C[:, n] = (c[:, 0] > 100) * 10
    T = C.copy()
    T[:, np.flatnonzero(c[:, 1] < 18)] *= 3                      # this team overuses its left flank
    xg, st = C[:, n] * 0.1, np.ones(n)
    league = league_chain(C, xg, st, TACTICAL)
    team = shrunk_chain(T, T[:, n] * 0.1, st, league, 10.0)
    data = flow_data(team, league, T[:, :n])
    assert len(data["links"]) == 3 and len(data["zone_vs_league"]) == n
    for k in data["links"]:
        assert 0 <= k["lo"] <= k["hi"] <= 1      # adapting can never hurt more than losing the ball
    h, w = mpimg.imread(flow_map(data, tmp_path / "f.png", "t")).shape[:2]
    assert (w, h) == (1600, 900)
