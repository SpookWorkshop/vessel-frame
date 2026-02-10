"""Map screen plugin for vessel-frame.

Displays vessels over a map image. Downloads maps from Mapbox and caches locally
"""

from __future__ import annotations

import asyncio
import datetime
import math
import os
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Any

import logging
from PIL import Image, ImageDraw, ImageFont

from vf_core.asset_manager import AssetManager
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import (
    ConfigField,
    ConfigFieldType,
    ConfigSchema,
    RendererPlugin,
    ScreenPlugin,
)
from vf_core.render_strategies import PeriodicRenderStrategy
from vf_core.vessel_manager import VesselManager


class MapScreen(ScreenPlugin):
    """Screen to display a map of vessels which were recently observed."""

    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20
    HEADER_HEIGHT = 70

    # Ship shape rendering thresholds (in metres per pixel)
    # Below MIN: too zoomed in, ships would be too large
    # Above MAX: too zoomed out, ships would be too small to see any detail
    SHAPE_MIN_SCALE = 1.0
    SHAPE_MAX_SCALE = 50.0

    # Ship size constraints in pixels
    SHIP_MIN_LENGTH_PX = 15
    SHIP_MAX_LENGTH_PX = 80
    SHIP_MIN_BEAM_PX = 6
    SHIP_MAX_BEAM_PX = 30

    # Marker size when drawing dots
    DOT_RADIUS = 5

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.updated",
        update_interval: float = 300.0,
        min_lat: float = 0.0,
        max_lat: float = 0.0,
        min_lon: float = 0.0,
        max_lon: float = 0.0,
        cache_dir: str = "data",
        map_style: str = "mapbox/light-v11",
        mapbox_api_key: str = "",
        vessel_fill_colour: str = "#FF0000",
        vessel_outline_colour: str = "#000000",
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

        # Vessel colours
        self._vessel_fill = vessel_fill_colour
        self._vessel_outline = vessel_outline_colour

        # Parse bounds - handle string values from config
        self._min_lat = float(min_lat) if isinstance(min_lat, str) else min_lat
        self._max_lat = float(max_lat) if isinstance(max_lat, str) else max_lat
        self._min_lon = float(min_lon) if isinstance(min_lon, str) else min_lon
        self._max_lon = float(max_lon) if isinstance(max_lon, str) else max_lon

        # Ensure cache directory exists and download map images
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_map_images()

        self._map_portrait = self._load_map_image("map_portrait")
        self._map_landscape = self._load_map_image("map_landscape")

        # Parse update interval
        interval = float(update_interval) if isinstance(update_interval, str) else update_interval

        self._fonts: dict[str, ImageFont.FreeTypeFont] = {
            "small": self._asset_manager.get_font("default", "SemiBold", 14),
            "medium": self._asset_manager.get_font("default", "SemiBold", 20),
            "vessel": self._asset_manager.get_font("default", "SemiBold", 10),
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
            ("map_portrait", canvas.width, canvas.height),
            ("map_landscape", canvas.height, canvas.width),
        ]

        for name, width, height in orientations:
            img_path = self._cache_dir / name
            
            if img_path.exists():
                continue

            if len(self._mapbox_key) == 0:
                self._logger.error("No Mapbox Key set - unable to download image")
                continue

            self._logger.info(f"Downloading map image: {name}")
            try:
                # Use bounds format for Mapbox API
                bounds = (
                    f"[{self._min_lon},{self._min_lat},"
                    f"{self._max_lon},{self._max_lat}]"
                )
                url = (
                    f"https://api.mapbox.com/styles/v1/{self._map_style}/static/"
                    f"{bounds}/{width}x{height}?access_token={self._mapbox_key}"
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

        # Calculate current scale for ship rendering decisions
        metres_per_pixel = self._calculate_scale(width, height)
        use_shapes = self.SHAPE_MIN_SCALE <= metres_per_pixel <= self.SHAPE_MAX_SCALE

        self._renderer.clear()

        # Draw the map background
        current_map = self._get_current_map()
        if current_map:
            canvas.paste(current_map)

        # Draw vessels
        for vessel in vessels:
            self._draw_vessel(draw, vessel, width, height, metres_per_pixel, use_shapes)

        # Header drawn last so it's on top of everything
        self._draw_header_container(draw, width)
        text_x = self.SCREEN_PADDING + self.CONTAINER_PADDING_HORZ
        text_y = self.CONTAINER_PADDING_VERT
        self._draw_header(draw, text_x, text_y)

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
        date_format = os.getenv("DATE_FORMAT", "%d/%m/%y")
        subtitle_text = datetime.datetime.now().strftime(f"%A - {date_format} %H:%M")
        
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
        metres_per_pixel: float,
        use_shapes: bool,
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
        
        ship_stern = vessel.get("stern", 0)
        ship_bow = vessel.get("bow", 0)
        ship_port = vessel.get("port", 0)
        ship_starboard = vessel.get("starboard", 0)

        length = ship_stern + ship_bow
        beam = ship_port + ship_starboard

        use_shapes = use_shapes and length > 0 and beam > 0

        # Convert geographic coordinates to pixel position
        x = ((lon - self._min_lon) / (self._max_lon - self._min_lon)) * width
        y = height - (((lat - self._min_lat) / (self._max_lat - self._min_lat)) * height)

        # Get heading (prefer true heading, fall back to COG)
        heading = vessel.get("true_heading") or vessel.get("heading")
        if heading is None or heading == 511:  # 511 is a special value meaning the ship can't provide that data
            heading = vessel.get("cog")

        # Determine whether to draw shape or dot
        # Use shape only if within scale threshold AND we have valid heading
        has_valid_heading = heading is not None and heading != 360  # 360 = not available
        
        if use_shapes and has_valid_heading:
            self._draw_vessel_shape(draw, x, y, length, beam, heading, metres_per_pixel)
        else:
            self._draw_vessel_dot(draw, x, y)

        # Draw vessel name
        self._draw_vessel_label(draw, vessel, x, y, width, height)

    def _draw_vessel_dot(self, draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
        """Draw a vessel as a dot."""
        draw.ellipse(
            [
                x - self.DOT_RADIUS,
                y - self.DOT_RADIUS,
                x + self.DOT_RADIUS,
                y + self.DOT_RADIUS,
            ],
            fill=self._vessel_fill,
            outline=self._vessel_outline,
            width=2,
        )

    def _draw_vessel_shape(
        self,
        draw: ImageDraw.ImageDraw,
        x: float,
        y: float,
        length: int,
        beam: int,
        heading: float,
        metres_per_pixel: float,
    ) -> None:
        """Draw a vessel as a pointed rectangle orientated by heading."""
        # Convert to pixels
        length_px = length / metres_per_pixel
        beam_px = beam / metres_per_pixel

        # Clamp to reasonable pixel sizes
        length_px = max(self.SHIP_MIN_LENGTH_PX, min(self.SHIP_MAX_LENGTH_PX, length_px))
        beam_px = max(self.SHIP_MIN_BEAM_PX, min(self.SHIP_MAX_BEAM_PX, beam_px))

        # Centre ship at origin, bow pointing up (north = 0 degrees)
        # The bow point is at the top, stern is flat at the bottom
        half_length = length_px / 2
        half_beam = beam_px / 2
        bow_length = length_px * 0.25

        points = [
            (0, -half_length),
            (-half_beam, -half_length + bow_length),
            (-half_beam, half_length),
            (half_beam, half_length),
            (half_beam, -half_length + bow_length),
        ]

        # Rotate points by heading
        heading_rad = math.radians(heading)
        rotated_points = []
        for px, py in points:
            rx = px * math.cos(heading_rad) - py * math.sin(heading_rad)
            ry = px * math.sin(heading_rad) + py * math.cos(heading_rad)
            rotated_points.append((x + rx, y + ry))

        # Draw the ship
        draw.polygon(
            rotated_points,
            fill=self._vessel_fill,
            outline=self._vessel_outline,
            width=2,
        )

    def _draw_vessel_label(
        self,
        draw: ImageDraw.ImageDraw,
        vessel: dict[str, Any],
        x: float,
        y: float,
        width: int,
        height: int,
    ) -> None:
        """Draw the vessel name near its marker."""
        name = vessel.get("name")
        if not name or name == "Unknown":
            # Fall back to MMSI if no name
            mmsi = vessel.get("mmsi")
            if mmsi:
                name = str(mmsi)
            else:
                return
            
        font = self._fonts["vessel"]
        
        # Get text dimensions
        bbox = font.getbbox(name)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Position label to the right of the marker by default
        label_x = x + self.DOT_RADIUS + 4
        label_y = y - text_height / 2

        # Adjust if label would go off the right edge
        if label_x + text_width > width - self.SCREEN_PADDING:
            label_x = x - self.DOT_RADIUS - 4 - text_width

        # Adjust if label would go off top or bottom
        if label_y < self.SCREEN_PADDING + self.HEADER_HEIGHT:
            label_y = self.SCREEN_PADDING + self.HEADER_HEIGHT
        elif label_y + text_height > height - self.SCREEN_PADDING:
            label_y = height - self.SCREEN_PADDING - text_height

        # Draw text with halo for readability
        halo_colour = self._palette.get("foreground", "#FFFFFF")
        for dx, dy in [(-1, -1),(-1, 1),(1, -1),(1, 1),(-1, 0),(1, 0),(0, -1),(0, 1),]:
            draw.text((label_x + dx, label_y + dy), name, fill=halo_colour, font=font)

        draw.text((label_x, label_y), name, fill=self._vessel_outline, font=font)

    def _calculate_scale(self, width: int, height: int) -> float:
        """Calculate metres per pixel based on bounds and canvas dimensions.

        Uses the centre latitude for the calculation.

        Returns:
            Metres per pixel for the current view.
        """
        # Approximate metres per degree
        metres_per_degree_lat = 111_320
        centre_lat = (self._min_lat + self._max_lat) / 2
        metres_per_degree_lon = metres_per_degree_lat * math.cos(math.radians(centre_lat))

        # Calculate the geographic span in metres
        lat_range_metres = (self._max_lat - self._min_lat) * metres_per_degree_lat
        lon_range_metres = (self._max_lon - self._min_lon) * metres_per_degree_lon

        # Use the larger scale (more metres per pixel = more zoomed out)
        # This ensures ship shapes don't get too large
        scale_from_lat = lat_range_metres / height
        scale_from_lon = lon_range_metres / width

        return max(scale_from_lat, scale_from_lon)

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
                key="min_lat",
                label="Minimum Latitude",
                field_type=ConfigFieldType.FLOAT,
                default=53.35,
            ),
            ConfigField(
                key="max_lat",
                label="Maximum Latitude",
                field_type=ConfigFieldType.FLOAT,
                default=53.47,
            ),
            ConfigField(
                key="min_lon",
                label="Minimum Longitude",
                field_type=ConfigFieldType.FLOAT,
                default=-3.10,
            ),
            ConfigField(
                key="max_lon",
                label="Maximum Longitude",
                field_type=ConfigFieldType.FLOAT,
                default=-2.90,
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
            ConfigField(
                key="vessel_fill_colour",
                label="Vessel Fill Colour",
                field_type=ConfigFieldType.COLOUR,
                default="#FF0000",
            ),
            ConfigField(
                key="vessel_outline_colour",
                label="Vessel Outline Colour",
                field_type=ConfigFieldType.COLOUR,
                default="#000000",
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system."""
    return MapScreen(**kwargs)