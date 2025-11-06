from __future__ import annotations
import asyncio
import datetime
from typing import Any
from contextlib import suppress
from PIL import Image, ImageDraw, ImageFont
import logging

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import ScreenPlugin, RendererPlugin
from vf_core.vessel_manager import VesselManager
from vf_core.ais_utils import get_vessel_full_type_name
from vf_core.render_strategies import PeriodicRenderStrategy


class ZoneScreen(ScreenPlugin):
    """
    Screen to display detailed information about a vessel in a zone.
    """

    # Layout constants
    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20

    # Ship diagram constants
    SHIP_DIAGRAM_HEIGHT = 298
    SHIP_DIAGRAM_PADDING = 5
    SHIP_INNER_PADDING = 30
    MAST_SIZE = 10
    DIMENSION_LABEL_SPACING = 5

    # Spacing between sections
    SECTION_SPACING = 35
    INFO_ROW_SPACING = 30
    INFO_LINE_SPACING = 35

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        in_topic: str = "vessel.zone_entered",
        update_interval: float = 10.0,
    ) -> None:
        self._logger = logging.getLogger(__name__)

        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None
        self._palette = renderer.palette
        self._current_vessel: dict[str, Any] | None = None
        self._render_strategy = PeriodicRenderStrategy(
            self._render, renderer.MIN_RENDER_INTERVAL + update_interval
        )

    async def activate(self) -> None:
        """Start listening for zone events and enable periodic rendering."""
        if self._task and not self._task.done():
            return

        await self._render_strategy.start()
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        """Stop listening and cancel background work."""
        if self._task and not self._task.done():
            self._render_strategy.stop()
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        """Internal loop that receives zone events and requests renders."""
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                self._current_vessel = msg.get("vessel")

                if self._current_vessel and self._is_valid_vessel(self._current_vessel):
                    await self._render_strategy.request_render()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._logger.exception("Update loop crashed")
            raise

    def _is_valid_vessel(self, vessel: dict[str, Any]) -> bool:
        """Return True if the vessel dict contains an MMSI and name."""
        return vessel is not None and vessel.get("mmsi") and vessel.get("name")

    async def _render(self) -> None:
        """Render the detail view for the current vessel, if present."""
        vessel = self._current_vessel

        if not vessel:
            return

        fonts = self._renderer.fonts
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size

        self._renderer.clear()
        self._draw_container(draw, width, height)

        text_x = self.SCREEN_PADDING + self.CONTAINER_PADDING_HORZ
        text_y = self.SCREEN_PADDING + self.CONTAINER_PADDING_VERT

        # Draw sections
        text_y = self._draw_header(draw, fonts, text_x, text_y)
        text_y += self.SECTION_SPACING
        text_y = self._draw_vessel_diagram(draw, fonts, text_x, text_y, width, vessel)
        text_y = self._draw_vessel_name(draw, fonts, text_x, text_y, width, vessel)
        text_y = self._draw_vessel_info(draw, fonts, text_x, text_y, width, vessel)

        self._renderer.flush()

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
        fonts: dict[str, ImageFont.FreeTypeFont],
        x: int,
        y: int,
    ) -> int:
        """Draw the title and timestamp header and return the new y-position."""
        title_font = fonts["medium"]
        title_text = "Ship Tracker"

        subtitle_font = fonts["small"]
        subtitle_text = datetime.datetime.now().strftime("%A - %d/%m/%y %H:%M")

        draw.text((x, y), title_text, fill=self._palette["text"], font=title_font)
        y += self._get_text_height(title_font, title_text) + 4
        draw.text((x, y), subtitle_text, fill=self._palette["text"], font=subtitle_font)

        return y

    def _draw_vessel_diagram(
        self,
        draw: ImageDraw.ImageDraw,
        fonts: dict[str, ImageFont.FreeTypeFont],
        x: int,
        y: int,
        width: int,
        vessel: dict[str, Any],
    ) -> int:
        """
        Draw a simplified ship top-down diagram and dimension labels.

        The diagram is scaled to fit a fixed-height box, preserving aspect ratio
        based on AIS-reported bow/stern/port/starboard distances.

        Returns:
            int: The y-position immediately below the diagram box.
        """
        ship_stern = vessel.get("stern", 0)
        ship_bow = vessel.get("bow", 0)
        ship_port = vessel.get("port", 0)
        ship_starboard = vessel.get("starboard", 0)

        ship_len = ship_stern + ship_bow
        ship_wid = ship_port + ship_starboard

        if ship_len == 0 or ship_wid == 0:
            return y

        # Calculate diagram area
        max_width = width - ((self.SCREEN_PADDING + self.CONTAINER_PADDING_HORZ) * 2)
        diagram_height = self.SHIP_DIAGRAM_HEIGHT

        # Draw outer border
        border_x = x
        border_y = y
        draw.rectangle(
            [(border_x, border_y), (border_x + max_width, border_y + diagram_height)],
            outline=self._palette["line"],
            width=2,
        )

        # Padding inside the border
        border_padding = 5
        inner_x = border_x + border_padding
        inner_y = border_y + border_padding
        inner_width = max_width - (border_padding * 2)
        inner_height = diagram_height - (border_padding * 2)

        # Calc space for labels
        font = fonts["small"]

        # Width dimension indicator space
        wid_text = f"{ship_wid}m"
        wid_label_width = self._get_text_width(font, wid_text)
        left_label_space = wid_label_width + (
            self.DIMENSION_LABEL_SPACING * 4
        )  # Text + spacing for lines

        # Length dimension indicator space
        len_text = f"{ship_len}m"
        len_label_height = self._get_text_height(font, len_text)
        bottom_label_space = len_label_height + (
            self.DIMENSION_LABEL_SPACING * 4
        )  # Text + spacing for lines

        # Available space for ship + dimension indicators + padding
        ship_padding = self.SHIP_INNER_PADDING
        available_width = inner_width - (ship_padding * 2) - left_label_space
        available_height = inner_height - (ship_padding * 2) - bottom_label_space

        # Calculate scale
        width_ratio = available_width / ship_len
        height_ratio = available_height / ship_wid
        scale_factor = min(width_ratio, height_ratio)

        scaled_len = int(ship_len * scale_factor)
        scaled_wid = int(ship_wid * scale_factor)

        # The ship area starts after the left label space
        ship_area_left = inner_x + ship_padding + left_label_space
        ship_area_top = inner_y + ship_padding
        ship_area_width = available_width
        ship_area_height = available_height

        ship_center_x = ship_area_left + (ship_area_width / 2)
        ship_center_y = ship_area_top + (ship_area_height / 2)

        # Draw ship outline
        self._draw_ship_outline(
            draw, ship_center_x, ship_center_y, scaled_len, scaled_wid
        )

        # Draw GPS receiver position
        ship_top_left_x = ship_center_x - (scaled_len / 2)
        ship_top_left_y = ship_center_y - (scaled_wid / 2)

        dot_x = ship_top_left_x + (ship_stern * scale_factor)
        dot_y = ship_top_left_y + (ship_port * scale_factor)

        draw.ellipse(
            [
                dot_x - self.MAST_SIZE / 2,
                dot_y - self.MAST_SIZE / 2,
                dot_x + self.MAST_SIZE / 2,
                dot_y + self.MAST_SIZE / 2,
            ],
            fill=self._palette["accent"],
        )

        # Draw dimension labels
        self._draw_dimension_labels(
            draw,
            font,
            ship_center_x,
            ship_center_y,
            scaled_len,
            scaled_wid,
            ship_len,
            ship_wid,
        )

        return y + diagram_height

    def _draw_ship_outline(
        self,
        draw: ImageDraw.ImageDraw,
        center_x: float,
        center_y: float,
        scaled_len: int,
        scaled_wid: int,
    ) -> None:
        """Draw a simplified polygon outline of the vessel (top-down)."""
        # Calc nose length
        nose_ratio = 0.6 * (scaled_wid / scaled_len)
        nose_len = scaled_len * nose_ratio

        # Ship outline
        half_len = scaled_len / 2
        half_wid = scaled_wid / 2

        top_left = (center_x - half_len, center_y - half_wid)
        top_right = (center_x + half_len - nose_len, center_y - half_wid)
        nose = (center_x + half_len, center_y)
        bottom_right = (center_x + half_len - nose_len, center_y + half_wid)
        bottom_left = (center_x - half_len, center_y + half_wid)

        points = [top_left, top_right, nose, bottom_right, bottom_left]
        draw.polygon(points, outline=self._palette["accent"], width=2)

    def _draw_dimension_labels(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        center_x: float,
        center_y: float,
        scaled_len: int,
        scaled_wid: int,
        actual_len: int,
        actual_wid: int,
    ) -> None:
        """Draw measurement guides and text for length and width."""
        spacing = self.DIMENSION_LABEL_SPACING
        half_len = scaled_len / 2
        half_wid = scaled_wid / 2

        # Length on bottom
        left_x = center_x - half_len
        right_x = center_x + half_len
        bottom_y = center_y + half_wid

        draw.line(
            [
                (left_x, bottom_y + spacing),
                (left_x, bottom_y + spacing * 2),
                (center_x, bottom_y + spacing * 2),
                (center_x, bottom_y + spacing * 3),
                (center_x, bottom_y + spacing * 2),
                (right_x, bottom_y + spacing * 2),
                (right_x, bottom_y + spacing),
            ],
            fill=self._palette["accent"],
            width=2,
        )

        len_text = f"{actual_len}m"
        len_text_width, len_text_height = self._get_text_size(font, len_text)
        draw.text(
            (center_x - (len_text_width / 2), bottom_y + spacing * 4),
            len_text,
            fill=self._palette["accent"],
            font=font,
        )

        # Width vertically on left
        top_y = center_y - half_wid
        middle_y = center_y

        draw.line(
            [
                (left_x - spacing, top_y),
                (left_x - spacing * 2, top_y),
                (left_x - spacing * 2, middle_y),
                (left_x - spacing * 3, middle_y),
                (left_x - spacing * 2, middle_y),
                (left_x - spacing * 2, bottom_y),
                (left_x - spacing, bottom_y),
            ],
            fill=self._palette["accent"],
            width=2,
        )

        wid_text = f"{actual_wid}m"
        wid_text_width, wid_text_height = self._get_text_size(font, wid_text)
        draw.text(
            (left_x - wid_text_width - spacing * 4, middle_y - wid_text_height / 2),
            wid_text,
            fill=self._palette["accent"],
            font=font,
        )

    def _draw_vessel_name(
        self,
        draw: ImageDraw.ImageDraw,
        fonts: dict[str, ImageFont.FreeTypeFont],
        x: int,
        y: int,
        width: int,
        vessel: dict[str, Any],
    ) -> int:
        """Draw the vessel name with an underline and return new y."""
        font = fonts["large"]
        name = vessel.get("name", "Unknown")

        text_width, text_height = self._get_text_size(font, name)
        center_x = width / 2 - text_width / 2

        # Draw name
        draw.text((int(center_x), y), name, fill=self._palette["text"], font=font)
        y += text_height + 12
        # todo: magic 12 number otherwise the line goes through the text even after the height calc.
        # Need to figure out what's going wrong with this part

        # Draw underline
        draw.line(
            [
                (int(width / 2 - text_width / 2), y),
                (int(width / 2 + text_width / 2), y),
            ],
            fill=self._palette["line"],
            width=2,
        )

        y += self.SECTION_SPACING
        return y

    def _draw_vessel_info(
        self,
        draw: ImageDraw.ImageDraw,
        fonts: dict[str, ImageFont.FreeTypeFont],
        x: int,
        y: int,
        width: int,
        vessel: dict[str, Any],
    ) -> int:
        """Draw key/value rows of data about the vessel."""
        font = fonts["medium"]

        info_rows = [
            {"label": "MMSI", "value": str(vessel.get("mmsi", "Unknown"))},
            {"label": "Callsign", "value": str(vessel.get("callsign", "Unknown"))},
            {
                "label": "Vessel Type",
                "value": get_vessel_full_type_name(vessel.get("type", -1)),
            },
        ]

        if "destination" in vessel and vessel["destination"]:
            info_rows.append({"label": "Destination", "value": vessel["destination"]})

        if "speed" in vessel and vessel["speed"] is not None:
            info_rows.append({"label": "Speed", "value": f"{vessel['speed']} kts"})

        for row in info_rows:
            y = self._draw_info_row(draw, font, x, y, width, row["label"], row["value"])

        return y

    def _draw_info_row(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        x: int,
        y: int,
        width: int,
        label: str,
        value: str,
    ) -> int:
        """Draw a single info row with label on the left and value on the right."""
        icon_width = 30

        # No icons implemented yet

        # Draw label and value
        label_x = x + icon_width
        value_width = self._get_text_width(font, value)
        value_x = (
            width - self.SCREEN_PADDING - self.CONTAINER_PADDING_HORZ - value_width
        )

        draw.text((label_x, y), label, fill=self._palette["text"], font=font)
        draw.text((value_x, y), value, fill=self._palette["text"], font=font)

        y += self.INFO_ROW_SPACING

        draw.line([(x, y), (width - x, y)], fill=self._palette["line"], width=2)

        y += self.INFO_LINE_SPACING
        return y

    def _get_text_width(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Calculate the pixel width of the text for the provided font."""
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]

    def _get_text_height(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Calculate the pixel height of the text for the provided font."""
        bbox = font.getbbox(text)
        return bbox[3] - bbox[1]

    def _get_text_size(
        self, font: ImageFont.FreeTypeFont, text: str
    ) -> tuple[int, int]:
        """Calculate width and height in pixels for the given text and font."""
        bbox = font.getbbox(text)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system"""
    return ZoneScreen(**kwargs)
