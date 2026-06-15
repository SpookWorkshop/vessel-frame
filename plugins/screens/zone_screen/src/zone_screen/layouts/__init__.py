"""Zone-screen layouts, one class per (orientation, density) combo.

select_layout maps the orientation & density profile chosen by the orchestrator
to a layout class. Portrait's compact and standard tiers share one scaled class.
Landscape's three densities have a class for each.
"""
from __future__ import annotations

from .base import ZoneLayout
from .landscape_base import LandscapeLayout
from .landscape_compact import LandscapeCompact
from .landscape_large import LandscapeLarge
from .landscape_standard import LandscapeStandard
from .portrait_large import PortraitLarge
from .portrait_standard import PortraitStandard

__all__ = [
    "ZoneLayout", "LandscapeLayout", "select_layout",
    "PortraitStandard", "PortraitLarge",
    "LandscapeCompact", "LandscapeStandard", "LandscapeLarge",
]

_LANDSCAPE = {
    "compact": LandscapeCompact,
    "standard": LandscapeStandard,
    "large": LandscapeLarge,
}


def select_layout(orientation: str, profile: str) -> type[ZoneLayout]:
    """Return the layout class for an (orientation, density) coordinate."""
    if orientation == "landscape":
        return _LANDSCAPE[profile]
    # Portrait, compact + standard share the scaled single-column layout.
    return PortraitLarge if profile == "large" else PortraitStandard
