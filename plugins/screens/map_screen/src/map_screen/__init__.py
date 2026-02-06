from __future__ import annotations
import asyncio
import datetime
from typing import Any
from contextlib import suppress
from PIL import Image, ImageDraw, ImageFont
import logging
from pathlib import Path
import urllib.request

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import (
    ConfigField,
    ConfigFieldType,
    ConfigSchema,
    ScreenPlugin,
    RendererPlugin,
)
from vf_core.vessel_manager import VesselManager
from vf_core.asset_manager import AssetManager
from vf_core.render_strategies import PeriodicRenderStrategy

class MapScreen(ScreenPlugin):
    """Screen to display a map of vessels which were recently observed."""

    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20
    HEADER_HEIGHT = 70

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.updated",
        update_interval: float = 300.0,
        bounds_tl_lat: float = 0.0,
        bounds_tl_lon: float = 0.0,
        bounds_br_lat: float = 0.0,
        bounds_br_lon: float = 0.0,
        cache_dir: str = "data",
        map_style: str = "mapbox/light-v11",
        mapbox_api_key: str = ""
    ) -> None:
        self._logger = logging.getLogger(__name__)

        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._asset_manager = asset_manager
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None
        self._palette = renderer.palette
        self._map_style = map_style
        self._cache_dir = Path(cache_dir)
        self._mapbox_key = mapbox_api_key

        if len(self._mapbox_key) == 0:
            self._logger.warning("Mapbox API Key not set. Map backgrounds may be unavailable")

        # Store bounds as min/max for clarity since MapBox uses this terminology
        # Top-left = (max_lat, min_lon), Bottom-right = (min_lat, max_lon)
        self._max_lat = float(bounds_tl_lat) if isinstance(bounds_tl_lat, str) else bounds_tl_lat  # Northern boundary
        self._min_lon = float(bounds_tl_lon) if isinstance(bounds_tl_lon, str) else bounds_tl_lon  # Western boundary
        self._min_lat = float(bounds_br_lat) if isinstance(bounds_br_lat, str) else bounds_br_lat  # Southern boundary
        self._max_lon = float(bounds_br_lon) if isinstance(bounds_br_lon, str) else bounds_br_lon  # Eastern boundary

        # Ensure cache directory exists and download map images
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_map_images()

        self._map_portrait = self._load_map_image("map_portrait")
        self._map_landscape = self._load_map_image("map_landscape")

        interval = float(update_interval) if isinstance(update_interval, str) else update_interval

        self._fonts: dict[str, ImageFont.FreeTypeFont] = {
            "small": self._asset_manager.get_font("default", "SemiBold", 14),
            "medium": self._asset_manager.get_font("default", "SemiBold", 20),
        }

        self._icons: dict[str, Image.Image] = {
            "vessel": self._asset_manager.get_icon("vessel", 40, self._palette["icon"]),
        }

        self._render_strategy = PeriodicRenderStrategy(
            self._render, max(interval, renderer.MIN_RENDER_INTERVAL)
        )

    def _ensure_map_images(self) -> None:
        """Download map images for both orientations if they don't exist."""
        canvas = self._renderer.canvas

        orientations = [
            ("map_portrait", f"{canvas.width}x{canvas.height}"),
            ("map_landscape", f"{canvas.height}x{canvas.width}"),
        ]

        bbox = f"[{self._min_lon},{self._min_lat},{self._max_lon},{self._max_lat}]"

        for name, dimensions in orientations:
            img_path = self._cache_dir / name
            if img_path.exists():
                continue

            if len(self._mapbox_key) == 0:
                self._logger.error("No Mapbox Key set - unable to download image")
                continue

            self._logger.info(f"Downloading map image: {name}")
            try:
                url = (
                    f"https://api.mapbox.com/styles/v1/{self._map_style}/static/"
                    f"{bbox}/{dimensions}?access_token={self._mapbox_key}"
                )
                self._logger.debug(f"Mapbox URL: {url}")
                urllib.request.urlretrieve(url, img_path)
                self._logger.info(f"Downloaded map image: {img_path}")
            except Exception:
                self._logger.exception(f"Failed to download map image: {name}")

    def _load_map_image(self, name: str) -> Image.Image | None:
        """Load a map image from the cache directory."""
        path = self._cache_dir / name

        if path.exists():
            return Image.open(path)

        self._logger.warning(f"Map image not found: {path}")
        return None

    def _get_current_map(self) -> Image.Image | None:
        """Get the appropriate map image for the current canvas orientation."""
        canvas = self._renderer.canvas
        is_portrait = canvas.width < canvas.height

        return self._map_portrait if is_portrait else self._map_landscape

    async def activate(self) -> None:
        """Start listening for updates and enable periodic rendering."""
        if self._task and not self._task.done():
            return

        await self._render_strategy.start()
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
                await self._render_strategy.request_render()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Update loop crashed")
            raise

    async def _render(self) -> None:
        """Render the map of recently observed vessels."""
        vessels = self._vessel_manager.get_recent_vessels()
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size

        self._renderer.clear()

        # Draw the map background
        current_map = self._get_current_map()
        if current_map:
            canvas.paste(current_map)

        # Draw header bar
        self._draw_header_container(draw, width)

        # Draw header content
        text_x = self.SCREEN_PADDING + self.CONTAINER_PADDING_HORZ
        text_y = self.SCREEN_PADDING + self.CONTAINER_PADDING_VERT
        self._draw_header(draw, text_x, text_y)

        # Draw vessel markers
        for vessel in vessels:
            self._draw_vessel(draw, vessel, width, height)

        await self._renderer.flush()

    def _draw_header_container(self, draw: ImageDraw.ImageDraw, width: int) -> None:
        """Draw the header bar container."""
        draw.rounded_rectangle(
            [
                (self.SCREEN_PADDING, self.SCREEN_PADDING),
                (width - self.SCREEN_PADDING, self.SCREEN_PADDING + self.HEADER_HEIGHT),
            ],
            radius=8,
            fill=self._palette["foreground"],
        )

    def _draw_header(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        """Draw the title and timestamp header."""
        title_font = self._fonts["medium"]
        title_text = "Ship Tracker"

        subtitle_font = self._fonts["small"]
        subtitle_text = datetime.datetime.now().strftime("%A - %d/%m/%y %H:%M")

        icon = self._icons["vessel"]
        self._renderer.canvas.paste(icon, (x, y), icon)
        x += icon.size[0] + 20

        draw.text((x, y), title_text, fill=self._palette["text"], font=title_font)
        y += self._get_text_height(title_font, title_text) + 4
        draw.text((x, y), subtitle_text, fill=self._palette["text"], font=subtitle_font)

    def _draw_vessel(
        self,
        draw: ImageDraw.ImageDraw,
        vessel: dict[str, Any],
        width: int,
        height: int,
    ) -> None:
        """Draw a single vessel marker at its geographic position."""
        lat = vessel.get("lat")
        lon = vessel.get("lon")

        # Skip vessels without position data
        if lat is None or lon is None:
            return

        # Skip vessels outside the map bounds
        if not (self._min_lat <= lat <= self._max_lat):
            return
        if not (self._min_lon <= lon <= self._max_lon):
            return

        # Convert geographic coordinates to pixel position
        # x increases west to east (min_lon to max_lon)
        # y increases north to south (max_lat to min_lat)
        x = ((lon - self._min_lon) / (self._max_lon - self._min_lon)) * width
        y = ((self._max_lat - lat) / (self._max_lat - self._min_lat)) * height

        # Draw marker
        point_radius = 5
        draw.ellipse(
            [
                x - point_radius,
                y - point_radius,
                x + point_radius,
                y + point_radius,
            ],
            fill=self._palette["text"],
        )

    def _get_text_height(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Calculate the pixel height of the given text with the provided font."""
        bbox = font.getbbox(text)
        return bbox[3] - bbox[1]


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
                key="bounds_tl_lat",
                label="Top-Left Latitude (North)",
                field_type=ConfigFieldType.FLOAT,
                default=0.0,
            ),
            ConfigField(
                key="bounds_tl_lon",
                label="Top-Left Longitude (West)",
                field_type=ConfigFieldType.FLOAT,
                default=0.0,
            ),
            ConfigField(
                key="bounds_br_lat",
                label="Bottom-Right Latitude (South)",
                field_type=ConfigFieldType.FLOAT,
                default=0.0,
            ),
            ConfigField(
                key="bounds_br_lon",
                label="Bottom-Right Longitude (East)",
                field_type=ConfigFieldType.FLOAT,
                default=0.0,
            ),
            ConfigField(
                key="map_style",
                label="Map Style",
                field_type=ConfigFieldType.STRING,
                default="mapbox/light-v11",
            ),
            ConfigField(
                key="cache_dir",
                label="Map Cache Directory",
                field_type=ConfigFieldType.STRING,
                default="data",
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system."""
    return MapScreen(**kwargs)