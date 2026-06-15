"""Map screen plugin for vessel-frame.

Displays vessels over a Mapbox map image inside a broadsheet frame. The screen
is an orchestrator that owns lifecycle + vessel data, delegates map-image
acquisition to MapImageCache (tiles.py) and all drawing to MapLayout (layout.py).
The design is the same for every resolution and orientation, so this is a single
layout rather than a family.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

from vf_core.asset_manager import AssetManager
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import (
    ConfigField,
    ConfigFieldType,
    ConfigSchema,
    RendererPlugin,
    ScreenPlugin,
    require_plugin_args,
)
from vf_core.render_strategies import PeriodicRenderStrategy
from vf_core.vessel_manager import VesselManager

from .bounds import Bounds
from .layout import MapLayout
from .tiles import MapImageCache


class MapScreen:
    """Screen to display a map of vessels which were recently observed."""

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.updated",
        update_interval: float = 300.0,
        bounds: dict | None = None,
        data_dir: Path,
        map_style: str = "mapbox/light-v11",
        mapbox_api_key: str = "",
        **kwargs: Any,
    ) -> None:
        require_plugin_args(bus=bus, renderer=renderer, vm=vm, asset_manager=asset_manager)
        self._logger = logging.getLogger(__name__)

        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None

        if len(mapbox_api_key) == 0:
            self._logger.warning("Mapbox API Key not set. Map backgrounds may be unavailable")

        map_style = map_style.removeprefix("mapbox://styles/")
        self._bounds = Bounds.parse(bounds, self._logger)
        if not self._bounds.valid:
            self._logger.warning(
                "Map bounds are not configured or invalid. Set the bounds field in "
                "config. Vessels will not be drawn until bounds are configured."
            )

        # The layout owns the geometry, so its plate sizes (one per orientation)
        # drive the image dimensions the cache requests.
        self._layout = MapLayout(renderer=renderer, asset_manager=asset_manager, bounds=self._bounds)
        canvas = renderer.canvas
        short_edge, long_edge = min(canvas.width, canvas.height), max(canvas.width, canvas.height)
        self._tiles = MapImageCache(
            cache_dir=data_dir / "map_cache",
            map_style=map_style,
            mapbox_key=mapbox_api_key,
            bounds=self._bounds,
            portrait_plate=self._layout.plate_size(short_edge, long_edge),
            landscape_plate=self._layout.plate_size(long_edge, short_edge),
            logger=self._logger,
        )
        self._tiles.ensure()
        self._tiles.load()

        interval = float(update_interval) if isinstance(update_interval, str) else update_interval
        self._render_strategy = PeriodicRenderStrategy(
            self._render, max(interval, renderer.MIN_RENDER_INTERVAL)
        )

    # --- lifecycle ---------------------------------------------------------
    async def activate(self) -> None:
        """Start listening for updates and enable periodic rendering."""
        if self._task and not self._task.done():
            return
        if not self._tiles.loaded:
            self._tiles.ensure()
            self._tiles.load()

        await self._render_strategy.start()
        self._render_strategy.request_render()
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        """Stop listening for updates and cancel pending work."""
        if self._task and not self._task.done():
            await self._render_strategy.stop()
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        """Internal loop that receives update events and requests renders."""
        try:
            async for _ in self._bus.subscribe(self._in_topic):
                self._render_strategy.request_render()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Update loop crashed")
            raise

    # --- render ------------------------------------------------------------
    async def _render(self) -> None:
        """Render the map of recently observed vessels via the layout."""
        canvas = self._renderer.canvas
        is_portrait = canvas.width < canvas.height
        map_image = self._tiles.current(is_portrait)
        vessels = self._vessel_manager.get_recent_vessels()
        await self._layout.render(map_image, vessels)


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin."""
    return ConfigSchema(
        plugin_name="map_screen",
        plugin_type="screen",
        fields=[
            ConfigField(
                key="update_interval",
                label="Min Update Interval",
                field_type=ConfigFieldType.FLOAT,
                default=300.0,
            ),
            ConfigField(
                key="bounds",
                label="Map Bounds",
                field_type=ConfigFieldType.BBOX,
                default=None,
                required=False,
                description="Geographic bounding box for the map. Requires a Mapbox API key and an active renderer.",
            ),
            ConfigField(
                key="map_style",
                label="Map Style",
                field_type=ConfigFieldType.STRING,
                default="mapbox/light-v11",
                description="Mapbox style for the map tiles. Choose a style matching the panel's colour capability (e.g. Spectra 6 / Gallery 7 / Black & White).",
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system."""
    return MapScreen(**kwargs)
