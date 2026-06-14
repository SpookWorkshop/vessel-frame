"""Shared base for the landscape table layouts.

Landscape shows a split acrolls multiple columns to compensate for the short height.
Both landscape tiers split the vessel list across columns the same way.
"""
from __future__ import annotations

import math

from .base import TableLayout

COLS = 2  # 2 columns for all sizes. Outline stays a large-tier feature


class LandscapeTableLayout(TableLayout):
    """Common landscape helper: balanced, column-major chunking."""

    def _balanced_chunks(self, vessels: list[dict], capacity: int) -> tuple[list[list[dict]], int]:
        """Split vessels across COLS columns, balanced (equal height) and
        column-major (most-recent down the first column, then the next).

        capacity is how many rows fit in one column. Returns (chunks, shown).
        """
        shown = min(len(vessels), capacity * COLS)
        if shown == 0:
            return [[] for _ in range(COLS)], 0
        per_col = math.ceil(shown / COLS)
        return [vessels[i * per_col:(i + 1) * per_col] for i in range(COLS)], shown
