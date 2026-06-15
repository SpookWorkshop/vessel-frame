from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
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

from .layouts import select_layout

# Layout profile is chosen by the panel's short side (min of width/height, px):
# at/above PROFILE_LARGE_MIN the dense two-column "large" layout is used, below
# PROFILE_COMPACT_MAX the tight single-column "compact" layout, else "standard".
PROFILE_LARGE_MIN = 1000
PROFILE_STANDARD_MIN = 480

# Upper bound on vessels pulled per render. The layout shows as many as fit.
FETCH_LIMIT = 500


class TableScreen:
    """Screen showing a broadsheet table of recently observed vessels.

    The screen class is an orchestrator that tracks the current vessel and on each
    render, picks the layout for the panel's (orientation, density) coordinate
    and delegates drawing to it.
    """

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.updated",
        update_interval: float = 30.0,
        **kwargs: Any,
    ) -> None:
        require_plugin_args(bus=bus, renderer=renderer, vm=vm, asset_manager=asset_manager)
        self._logger = logging.getLogger(__name__)

        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._asset_manager = asset_manager
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None
        self._palette = renderer.palette

        interval = float(update_interval) if isinstance(update_interval, str) else update_interval
        self._render_strategy = PeriodicRenderStrategy(
            self._render, max(interval, renderer.MIN_RENDER_INTERVAL)
        )

        canvas_w, canvas_h = renderer.canvas.size
        self._orientation = "landscape" if canvas_w > canvas_h else "portrait"
        self._profile = self._select_profile(canvas_w, canvas_h)
        self._layout = None
        self._scale = 0.0

    def _select_profile(self, w: int, h: int) -> str:
        """Pick a layout profile from the panel's short side."""
        cross = min(w, h)
        if cross >= PROFILE_LARGE_MIN:
            return "large"
        if cross < PROFILE_STANDARD_MIN:
            return "compact"
        return "standard"

    # --- lifecycle ---------------------------------------------------------
    async def activate(self) -> None:
        """Start listening for updates and enable periodic rendering."""
        if self._task and not self._task.done():
            return

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

    # --- render driver -----------------------------------------------------
    def _make_layout(self):
        cls = select_layout(self._orientation, self._profile)
        return cls(
            renderer=self._renderer,
            asset_manager=self._asset_manager,
            profile=self._profile,
            orientation=self._orientation,
        )

    async def _render(self) -> None:
        """Render the table of most recently observed vessels via the layout."""
        vessels = self._vessel_manager.get_recent_vessels(limit=FETCH_LIMIT)
        total = len(vessels)
        layout = self._make_layout()
        await layout.render(vessels, total)
        self._layout = layout
        self._scale = layout._scale


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin.

    Defines editable fields for the admin panel.

    Returns:
        ConfigSchema: Schema describing this plugin's configuration options.
    """
    return ConfigSchema(
        plugin_name="table_screen",
        plugin_type="screen",
        fields=[
            ConfigField(
                key="update_interval",
                label="Min Update Interval",
                field_type=ConfigFieldType.FLOAT,
                default=300.0
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system"""
    return TableScreen(**kwargs)
