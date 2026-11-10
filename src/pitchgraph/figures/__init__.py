"""Post-ready figures: one style, one pitch, a few chart types.

A post is a small JSON spec (see `posts/` at the repo root) rendered by
`scripts/build_posts.py`. Every image carries the StatsBomb credit (and
their logo when PITCHGRAPH_LOGO points at it), as the open-data licence
asks, plus the handle from POST_HANDLE.
"""
from pitchgraph.figures.posts import render

__all__ = ["render"]
