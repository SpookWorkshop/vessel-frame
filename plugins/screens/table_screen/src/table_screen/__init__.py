from __future__ import annotations
import asyncio
import datetime
import math
from typing import Any
from contextlib import suppress
from PIL import Image, ImageDraw, ImageFont
import logging

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import ConfigField, ConfigFieldType, ConfigSchema, ScreenPlugin, RendererPlugin
from vf_core.vessel_manager import VesselManager
from vf_core.asset_manager import AssetManager
from vf_core.ais_utils import get_vessel_full_type_name
from vf_core.render_strategies import PeriodicRenderStrategy


class TableScreen(ScreenPlugin):
    """
    Screen to display a table of vessels which were recently observed
    """

    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20
    ROW_SPACING = 10
    COLUMN_GAP_DIVISOR = 2
    HEADER_LABELS = {"name": "Ship Name", "type": "Ship Type", "time": "Last Seen"}

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.updated",
        update_interval: float = 30.0,
    ) -> None:
        self._logger = logging.getLogger(__name__)

        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._asset_manager = asset_manager
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None
        self._palette = renderer.palette

        interval = float(update_interval) if isinstance(update_interval, str) else update_interval

        self._fonts: dict[str,ImageFont.FreeTypeFont] = {}
        self._fonts["small"] = self._asset_manager.get_font("default", "SemiBold", 14)
        self._fonts["medium"] = self._asset_manager.get_font("default", "SemiBold", 20)

        self._icons: dict[str,Image.Image] = {}
        self._icons["vessel"] = self._asset_manager.get_icon("vessel", 40)

        self._render_strategy = PeriodicRenderStrategy(
            self._render, max(interval, renderer.MIN_RENDER_INTERVAL)
        )

    async def activate(self) -> None:
        """
        Start listening for updates and enable periodic rendering.

        Safe to call multiple times.
        """
        if self._task and not self._task.done():
            return

        await self._render_strategy.start()
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        """
        Stop listening for updates and cancel pending work.

        Waits for a clean shutdown of the background task.
        """
        if self._task and not self._task.done():
            await self._render_strategy.stop()

            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        """Internal loop that receives update events and requests renders."""

        try:
            async for msg in self._bus.subscribe(self._in_topic):
                await self._render_strategy.request_render()
        except asyncio.CancelledError:
            # Expected on deactivate
            raise
        except Exception as e:
            self._logger.exception("Update loop crashed")
            raise

    async def _render(self) -> None:
        """Render the table of most recently observed vessels."""

        vessels = self._vessel_manager.get_recent_vessels()

        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size

        self._renderer.clear()
        self._draw_container(draw, width, height)

        text_x = self.SCREEN_PADDING + self.CONTAINER_PADDING_HORZ
        text_y = self.SCREEN_PADDING + self.CONTAINER_PADDING_VERT

        text_y = self._draw_header(draw, text_x, text_y)
        text_y += 35

        self._draw_table(draw, vessels, text_x, text_y, width)

        await self._renderer.flush()

    def _draw_container(
        self, draw: ImageDraw.ImageDraw, width: int, height: int
    ) -> None:
        """Draw the card-like container for the table."""

        draw.rounded_rectangle(
            [
                (self.SCREEN_PADDING, self.SCREEN_PADDING),
                (width - self.SCREEN_PADDING, height - self.SCREEN_PADDING),
            ],
            radius=8,
            fill=self._palette["foreground"],
        )

    def _draw_header(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
    ) -> int:
        """
        Draw the title and timestamp header.

        Returns:
            int: Updated y-position after drawing.
        """

        title_font = self._fonts["medium"]
        title_text = "Ship Tracker"

        subtitle_font = self._fonts["small"]
        subtitle_text = datetime.datetime.now().strftime("%A - %d/%m/%y %H:%M")

        icon = self._icons["vessel"]
        self._renderer.canvas.paste(icon, (x,y), icon)
        x += icon.size[0] + 20

        draw.text((x, y), title_text, fill=self._palette["text"], font=title_font)
        y += self._get_text_height(title_font, title_text) + 4
        draw.text((x, y), subtitle_text, fill=self._palette["text"], font=subtitle_font)

        return y

    def _draw_table(
        self,
        draw: ImageDraw.ImageDraw,
        vessels: list[dict[str, Any]],
        x: int,
        y: int,
        width: int,
    ) -> None:
        """Draw the table headers and rows for the provided vessels."""

        body_font = self._fonts["small"]

        col_widths = self._calculate_column_widths(body_font, vessels)
        gap = self._calculate_column_gap(x, width, col_widths)

        y = self._draw_table_headers(draw, body_font, x, y, width, col_widths, gap)

        for vessel in vessels:
            y = self._draw_table_row(
                draw, body_font, vessel, x, y, width, col_widths, gap
            )

    def _draw_table_headers(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        x: int,
        y: int,
        width: int,
        col_widths: dict[str, int],
        gap: int,
    ) -> int:
        """Draw column headers and a divider line.

        Returns:
            int: Updated y-position after headers and divider.
        """

        draw.text(
            (x, y), self.HEADER_LABELS["name"], fill=self._palette["text"], font=font
        )
        draw.text(
            (x + col_widths["name"] + gap, y),
            self.HEADER_LABELS["type"],
            fill=self._palette["text"],
            font=font,
        )

        last_seen_width = self._get_text_width(font, self.HEADER_LABELS["time"])
        draw.text(
            (width - x - last_seen_width, y),
            self.HEADER_LABELS["time"],
            fill=self._palette["text"],
            font=font,
        )

        text_height = self._get_text_height(font, self.HEADER_LABELS["name"])
        y += text_height + self.ROW_SPACING
        draw.line([(x, y), (width - x, y)], fill=self._palette["line"], width=2)
        y += self.ROW_SPACING

        return y

    def _draw_table_row(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        vessel: dict[str, Any],
        x: int,
        y: int,
        width: int,
        col_widths: dict[str, int],
        gap: int,
    ) -> int:
        """Draw a single vessel row and return the next y-position."""

        ship_name = vessel.get("name")
        # Fall back to the mmsi if we don't know the name
        if ship_name == "Unknown" or ship_name is None:
            ship_name = vessel.get("mmsi") or "Unknown"

        ship_type = get_vessel_full_type_name(vessel.get("type", -1))
        timestamp = self._format_timestamp(vessel.get("ts", 0))

        name_x = x
        type_x = x + col_widths["name"] + gap

        timestamp_width = self._get_text_width(font, timestamp)
        time_x = width - x - timestamp_width

        draw.text((name_x, y), ship_name, fill=self._palette["text"], font=font)
        draw.text((type_x, y), ship_type, fill=self._palette["text"], font=font)
        draw.text((time_x, y), timestamp, fill=self._palette["text"], font=font)

        text_height = self._get_text_height(font, ship_name)
        y += text_height + self.ROW_SPACING
        draw.line([(x, y), (width - x, y)], fill=self._palette["line"], width=2)
        y += self.ROW_SPACING

        return y

    def _calculate_column_widths(
        self, font: ImageFont.FreeTypeFont, vessels: list[dict[str, Any]]
    ) -> dict[str, int]:
        """
        Calculate column widths from headers and current vessel data.
        
        Columns may overlap if the data is too long to fit
        in the available horizontal space.
        """

        widths = {
            "name": self._get_text_width(font, self.HEADER_LABELS["name"]),
            "type": self._get_text_width(font, self.HEADER_LABELS["type"]),
            "time": self._get_text_width(font, self.HEADER_LABELS["time"]),
        }

        for vessel in vessels:
            ship_name = vessel.get("name", "Unknown")
            ship_type = get_vessel_full_type_name(vessel.get("type", -1))
            timestamp = self._format_timestamp(vessel.get("ts", 0))

            widths["name"] = max(widths["name"], self._get_text_width(font, ship_name))
            widths["type"] = max(widths["type"], self._get_text_width(font, ship_type))
            widths["time"] = max(widths["time"], self._get_text_width(font, timestamp))

        return widths

    def _format_timestamp(self, timestamp: int) -> str:
        """Convert a Unix timestamp to HH:MM:SS, or '--:--:--' on error."""
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        except (ValueError, OSError):
            return "--:--:--"

    def _calculate_column_gap(
        self, start_x: int, width: int, col_widths: dict[str, int]
    ) -> int:
        """Calculate spacing between columns based on remaining width."""
        total_text_width = sum(col_widths.values())
        available_space = width - (2 * start_x) - total_text_width
        return available_space // self.COLUMN_GAP_DIVISOR

    def _get_text_width(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Calculate the pixel width of the given text with the provided font."""
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]

    def _get_text_height(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Calculate the pixel height of the given text with the provided font."""
        bbox = font.getbbox(text)
        return bbox[3] - bbox[1]

def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin.

    Defines editable fields for the admin panel.

    Returns:
        ConfigSchema: Schema describing this plugin's configuration options.
    """
    return ConfigSchema(
        plugin_name="zone_screen",
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
