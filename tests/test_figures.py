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
