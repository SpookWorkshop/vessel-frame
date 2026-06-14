"""Table-screen layouts, one class per (orientation, density) combo.

select_layout maps the orientation & density profile chosen by the orchestrator
to a layout class. Compact and standard share one list class per
orientation, large has its own broadsheet class per orientation.
"""
from __future__ import annotations

from .base import TableLayout
from .portrait_standard import PortraitStandard
from .portrait_large import PortraitLarge
from .landscape_base import LandscapeTableLayout
from .landscape_standard import LandscapeStandard
from .landscape_large import LandscapeLarge

__all__ = [
    "TableLayout", "LandscapeTableLayout", "select_layout",
    "PortraitStandard", "PortraitLarge",
    "LandscapeStandard", "LandscapeLarge",
]


def select_layout(orientation: str, profile: str) -> type[TableLayout]:
    """Return the layout class for an (orientation, density) combo."""
    if orientation == "landscape":
        return LandscapeLarge if profile == "large" else LandscapeStandard
    return PortraitLarge if profile == "large" else PortraitStandard
