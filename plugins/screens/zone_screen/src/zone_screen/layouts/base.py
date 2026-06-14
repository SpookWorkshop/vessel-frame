"""Base class for zone-screen layouts.

A layout is a self-contained renderer for one (orientation, density) coordinate.
It holds the render context the layouts share and the TextRenderingMixin drawing
helpers; concrete layouts implement render(). The orchestrator (ZoneScreen)
selects one layout per panel and delegates drawing to it — see select_layout().
"""
from __future__ import annotations

from typing import Any

from vf_core.text_utils import TextRenderingMixin


class ZoneLayout(TextRenderingMixin):
    """Render context + drawing helpers shared by every zone layout.

    TextRenderingMixin requires ``self._palette`` and ``self._asset_manager``,
    both set here, so subclasses can use the anchored-text/font helpers directly.
    """

    def __init__(
        self,
        *,
        renderer: Any,
        asset_manager: Any,
        zone_name: str,
        zone_lat: float,
        zone_lon: float,
        heading_offset: float,
        profile: str,
    ) -> None:
        self._renderer = renderer
        self._asset_manager = asset_manager
        self._palette = renderer.palette
        self._zone_name = zone_name
        self._zone_lat = zone_lat
        self._zone_lon = zone_lon
        self._heading_offset = heading_offset
        self._profile = profile
        self._current_vessel: dict[str, Any] | None = None

    async def render(self) -> None:
        """Draw the current vessel (``self._current_vessel``) to the canvas."""
        raise NotImplementedError

    def min_height(self) -> int:
        """Minimum pixels this layout needs; overridden where a fit-guard applies."""
        return 0
