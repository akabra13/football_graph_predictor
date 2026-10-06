"""The one interface every analysis module uses to value football actions.

Iteration 1 implements it with an absorbing Markov chain over pitch zones
(`value/markov.py`); iteration 2 replaces it with a graph neural network over
tracking data. Modules depend only on this protocol, so swapping the model
upgrades every report without touching the modules.
"""

from __future__ import annotations

from typing import Protocol

import polars as pl


class ValueModel(Protocol):
    name: str

    def state_value(self, x: pl.Expr, y: pl.Expr) -> pl.Expr:
        """Value of holding the ball at (x, y), in the attacking team's frame."""
        ...

    def add_action_values(self, events: pl.LazyFrame) -> pl.LazyFrame:
        """Add `v_start`, `v_end` and `value` (the action's value added)."""
        ...
