from __future__ import annotations
import asyncio
from typing import Any
from contextlib import suppress
import logging

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import ConfigField, ConfigFieldType, ConfigSchema, ScreenPlugin, RendererPlugin, require_plugin_args
from vf_core.vessel_manager import VesselManager
from vf_core.asset_manager import AssetManager
from vf_core.render_strategies import PeriodicRenderStrategy

from .layouts import select_layout

# Layout profile is chosen by the panel's short side (min of width/height, px):
# at/above PROFILE_LARGE_MIN the dense two-column "large" layout is used; below
# PROFILE_COMPACT_MAX the tight single-column "compact" layout; else "standard".
PROFILE_LARGE_MIN = 1000
PROFILE_COMPACT_MAX = 480


class ZoneScreen(ScreenPlugin):
    """Screen to display detailed information about a vessel in a zone.

    The screen is an orchestrator: it tracks the current vessel and, on each
    render, picks the layout for the panel's (orientation, density) coordinate
    and delegates drawing to it. Each layout is self-sizing — see the layouts
    package.
    """

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.zone_entered",
        update_interval: float = 10.0,
        zone_name: str = "Unknown",
        zone: dict | None = None,
        heading_offset: float = 0.0,
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
        self._current_vessel: dict[str, Any] | None = None
        self._render_strategy = PeriodicRenderStrategy(
            self._render, renderer.MIN_RENDER_INTERVAL + update_interval
        )

        lat = float(zone["lat"]) if zone else 0.0
        lon = float(zone["lon"]) if zone else 0.0
        rad = float(zone["rad"]) if zone else 0.0
        self._zone_name = zone_name
        self._zone_lat = lat
        self._zone_lon = lon
        self._heading_offset = float(heading_offset)
        self._vessel_manager.register_zone(zone_name, lat, lon, rad)

        canvas_w, canvas_h = self._renderer.canvas.size
        self._orientation = "landscape" if canvas_w > canvas_h else "portrait"
        self._profile = self._select_profile(canvas_w, canvas_h)
        self._layout = None
        self._scale = 0.0

    def _select_profile(self, w: int, h: int) -> str:
        """Pick a layout profile from the canvas size.

        Density is chosen from the cross-axis.
        """
        cross = min(w, h)
        if cross >= PROFILE_LARGE_MIN:
            return "large"
        if cross < PROFILE_COMPACT_MAX:
            return "compact"
        return "standard"

    # --- lifecycle ---------------------------------------------------------
    async def activate(self) -> None:
        """Start listening for zone events and enable periodic rendering."""
        if self._task and not self._task.done():
            return

        await self._render_strategy.start()
        self._render_strategy.request_render()
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        """Stop listening and cancel background work."""
        if self._task and not self._task.done():
            await self._render_strategy.stop()

            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        """Internal loop that receives zone events and requests renders."""
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                vessel = msg.get("vessel")
                self._logger.info("Zone Screen Update")

                if vessel and self._is_valid_vessel(vessel):
                    self._current_vessel = vessel
                    self._render_strategy.request_render()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Update loop crashed")
            raise

    def _is_valid_vessel(self, vessel: dict[str, Any]) -> bool:
        """Return True if the vessel has MMSI, a valid name and complete dimensions."""
        if not vessel:
            return False

        if not vessel.get("identifier"):
            return False

        name = vessel.get("name")
        if not name or name == "Unknown":
            return False

        length = vessel.get("bow", 0) + vessel.get("stern", 0)
        width = vessel.get("port", 0) + vessel.get("starboard", 0)
        if length == 0 or width == 0:
            return False

        return True

    # --- render driver -----------------------------------------------------
    def _make_layout(self):
        cls = select_layout(self._orientation, self._profile)
        return cls(
            renderer=self._renderer,
            asset_manager=self._asset_manager,
            zone_name=self._zone_name,
            zone_lat=self._zone_lat,
            zone_lon=self._zone_lon,
            heading_offset=self._heading_offset,
            profile=self._profile,
        )

    async def _render(self) -> None:
        """Render the current vessel via the layout for this panel."""
        layout = self._make_layout()
        layout._current_vessel = self._current_vessel
        await layout.render()
        self._layout = layout
        self._scale = getattr(layout, "_scale", 0.0)

    def _min_layout_height(self) -> int:
        """Delegate to the last-rendered layout's minimum (used by the survey)."""
        if self._layout is not None:
            return self._layout.min_height()
        return 0


def get_config_schema() -> ConfigSchema:
    return ConfigSchema(
        plugin_name="zone_screen",
        plugin_type="screen",
        fields=[
            ConfigField(
                key="zone_name",
                label="Zone Name",
                field_type=ConfigFieldType.STRING,
                default="zone"
            ),
            ConfigField(
                key="zone",
                label="Zone",
                field_type=ConfigFieldType.ZONE,
                default=None,
                required=False,
                description="Centre position and radius of the monitoring zone",
            ),
            ConfigField(
                key="heading_offset",
                label="Heading Offset",
                field_type=ConfigFieldType.INTEGER,
                default=0,
                required=False,
                description="Degrees to rotate the 13\" landscape compass rose so its "
                            "orientation matches how the frame physically faces.",
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    return ZoneScreen(**kwargs)
