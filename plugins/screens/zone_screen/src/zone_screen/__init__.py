from __future__ import annotations
import asyncio
import datetime
import os
from typing import Any
from contextlib import suppress
from PIL import Image, ImageDraw, ImageFont
import logging

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import ConfigField, ConfigFieldType, ConfigSchema, ScreenPlugin, RendererPlugin, require_plugin_args
from vf_core.vessel_manager import VesselManager
from vf_core.asset_manager import AssetManager
from vf_core.render_strategies import PeriodicRenderStrategy


class ZoneScreen(ScreenPlugin):
    """
    Screen to display detailed information about a vessel in a zone.
    """

    # Layout constants
    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20

    # Ship diagram constants. Height is derived from width via the aspect
    # ratio: vessels are never wider than long, so a tall square frame wastes
    # vertical space on smaller screens.
    SHIP_DIAGRAM_ASPECT = 0.7
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
        asset_manager: AssetManager,
        in_topic: str = "vessel.zone_entered",
        update_interval: float = 10.0,
        zone_name: str = "Unknown",
        zone: dict | None = None,
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

        # Scale chrome to canvas size using the 480px short-edge display as
        # the 1.0 baseline. Never scales below 1.0.
        canvas_w, canvas_h = self._renderer.canvas.size
        self._scale = max(1.0, min(canvas_w, canvas_h) / 480)

        self._screen_padding = int(self.SCREEN_PADDING * self._scale)
        self._container_padding_horz = int(self.CONTAINER_PADDING_HORZ * self._scale)
        self._container_padding_vert = int(self.CONTAINER_PADDING_VERT * self._scale)
        self._container_radius = max(1, int(8 * self._scale))

        self._ship_diagram_padding = max(1, int(self.SHIP_DIAGRAM_PADDING * self._scale))
        self._ship_inner_padding = int(self.SHIP_INNER_PADDING * self._scale)
        self._mast_size = max(2, int(self.MAST_SIZE * self._scale))
        self._dimension_label_spacing = max(1, int(self.DIMENSION_LABEL_SPACING * self._scale))

        self._section_spacing = int(self.SECTION_SPACING * self._scale)
        self._info_row_spacing = int(self.INFO_ROW_SPACING * self._scale)
        self._info_line_spacing = int(self.INFO_LINE_SPACING * self._scale)
        self._info_row_icon_gap = int(30 * self._scale)

        self._title_gap = max(1, int(4 * self._scale))
        self._name_underline_gap = int(12 * self._scale)
        self._waiting_subtitle_gap = int(16 * self._scale)
        self._line_width = max(1, int(2 * self._scale))

        self._fonts: dict[str,ImageFont.FreeTypeFont] = {}
        self._fonts["small"] = self._asset_manager.get_font("default", "SemiBold", max(10, int(14 * self._scale)))
        self._fonts["medium"] = self._asset_manager.get_font("default", "SemiBold", max(12, int(20 * self._scale)))
        self._fonts["large"] = self._asset_manager.get_font("default", "Bold", max(18, int(35 * self._scale)))

        self._icons: dict[str,Image.Image] = {}
        icon_colour = self._palette["icon"]

        self._icons["vessel"] = self._asset_manager.get_icon("vessel", max(16, int(40 * self._scale)), icon_colour)
        row_icon_size = max(10, int(20 * self._scale))
        for name in ["id", "callsign", "ship_type", "destination", "speed"]:
            self._icons[name] = self._asset_manager.get_icon(name, row_icon_size, icon_colour)

        # Vertical space occupied by the vessel name + underline + trailing section spacing.
        name_text_height = self._get_text_height(self._fonts["large"], "SHIP NAME")
        self._name_block_height = name_text_height + self._name_underline_gap + self._section_spacing

        lat = float(zone["lat"]) if zone else 0.0
        lon = float(zone["lon"]) if zone else 0.0
        rad = float(zone["rad"]) if zone else 0.0
        self._zone_name = zone_name
        self._vessel_manager.register_zone(zone_name, lat, lon, rad)

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
        
        # Must have an identifier
        if not vessel.get("identifier"):
            return False

        # Must have a known name (not None, not empty, not "Unknown")
        name = vessel.get("name")
        if not name or name == "Unknown":
            return False
        
        # Must have a size in both axes
        length = vessel.get("bow", 0) + vessel.get("stern", 0)
        width = vessel.get("port", 0) + vessel.get("starboard", 0)

        if length == 0 or width == 0:
            return False
        
        return True

    async def _render(self) -> None:
        """Render the detail view for the current vessel, or a waiting state."""
        vessel = self._current_vessel

        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size

        self._renderer.clear()
        self._draw_container(draw, width, height)

        text_x = self._screen_padding + self._container_padding_horz
        text_y = self._screen_padding + self._container_padding_vert

        text_y = self._draw_header(draw, text_x, text_y)
        text_y += self._section_spacing

        inner_width = width - 2 * (self._screen_padding + self._container_padding_horz)

        if vessel is None:
            self._draw_waiting_state(draw, text_x, text_y, width, height)
        elif width > height:
            # Landscape: name centred above, then diagram (left) and info
            # rows (right) below, aligned at the same y so the diagram sits
            # alongside the info rows.
            text_y = self._draw_vessel_name(draw, text_x, text_y, inner_width, vessel)

            column_gap = self._section_spacing
            column_w = (inner_width - column_gap) // 2
            left_x = text_x
            right_x = text_x + column_w + column_gap

            container_bottom = height - self._screen_padding - self._container_padding_vert
            available_height = container_bottom - text_y

            info_rows = self._fit_info_rows(self._get_info_rows(vessel), available_height)

            self._draw_vessel_diagram(
                draw, left_x, text_y, column_w, vessel,
                box_height=self._info_height_for(len(info_rows)),
            )
            self._draw_vessel_info(draw, right_x, text_y, column_w, info_rows)
        else:
            # Portrait: single column stacked layout. Shrink the diagram to
            # fit all info rows before resorting to dropping rows, so tall
            # displays aren't forced to sacrifice data for a large diagram.
            container_bottom = height - self._screen_padding - self._container_padding_vert
            body_available = container_bottom - text_y

            ideal_diagram_h = int(inner_width * self.SHIP_DIAGRAM_ASPECT)
            min_diagram_h = int(inner_width * 0.3)

            info_rows = self._get_info_rows(vessel)
            info_h = self._info_height_for(len(info_rows))
            available_for_diagram = body_available - self._name_block_height - info_h

            if available_for_diagram < min_diagram_h:
                # Not enough room even with a minimal diagram, drop rows.
                info_rows = self._fit_info_rows(
                    info_rows,
                    body_available - self._name_block_height - min_diagram_h,
                )
                diagram_h = min_diagram_h
            else:
                diagram_h = min(ideal_diagram_h, available_for_diagram)

            text_y = self._draw_vessel_diagram(draw, text_x, text_y, inner_width, vessel, box_height=diagram_h)
            text_y = self._draw_vessel_name(draw, text_x, text_y, inner_width, vessel)
            self._draw_vessel_info(draw, text_x, text_y, inner_width, info_rows)

        await self._renderer.flush()

    def _draw_waiting_state(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        """Draw a placeholder when no vessel is currently in the zone."""
        medium_font = self._fonts["medium"]
        small_font = self._fonts["small"]

        zone_text = f"Zone: {self._zone_name}"
        zone_w = self._get_text_width(medium_font, zone_text)
        draw.text(
            (width // 2 - zone_w // 2, y),
            zone_text,
            fill=self._palette["text"],
            font=medium_font,
        )
        y += self._get_text_height(medium_font, zone_text) + self._waiting_subtitle_gap

        status_text = "Waiting for vessel..."
        status_w = self._get_text_width(small_font, status_text)
        draw.text(
            (width // 2 - status_w // 2, y),
            status_text,
            fill=self._palette["text"],
            font=small_font,
        )

    def _draw_container(
        self, draw: ImageDraw.ImageDraw, width: int, height: int
    ) -> None:
        """Draw the card-like container for the table."""
        draw.rounded_rectangle(
            [
                (self._screen_padding, self._screen_padding),
                (width - self._screen_padding, height - self._screen_padding),
            ],
            radius=self._container_radius,
            fill=self._palette["foreground"],
        )

    def _draw_header(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
    ) -> int:
        """Draw the title and timestamp header and return the new y-position."""
        title_font = self._fonts["medium"]
        title_text = "Ship Tracker"

        subtitle_font = self._fonts["small"]
        date_format = os.getenv("DATE_FORMAT", "%d/%m/%y")
        subtitle_text = datetime.datetime.now().strftime(f"%A - {date_format} %H:%M")

        draw.text((x, y), title_text, fill=self._palette["text"], font=title_font)
        y += self._get_text_height(title_font, title_text) + self._title_gap
        draw.text((x, y), subtitle_text, fill=self._palette["text"], font=subtitle_font)

        return y

    def _draw_vessel_diagram(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        box_width: int,
        vessel: dict[str, Any],
        box_height: int | None = None,
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

        # Diagram height is derived from box width via a fixed aspect, or
        # the caller can supply an explicit height (used in landscape to
        # match the info column so both columns end at the same y).
        max_width = box_width
        diagram_height = box_height if box_height is not None else int(max_width * self.SHIP_DIAGRAM_ASPECT)

        # Draw outer border
        border_x = x
        border_y = y
        draw.rectangle(
            [(border_x, border_y), (border_x + max_width, border_y + diagram_height)],
            outline=self._palette["line"],
            width=self._line_width,
        )

        # Padding inside the border
        border_padding = self._ship_diagram_padding
        inner_x = border_x + border_padding
        inner_y = border_y + border_padding
        inner_width = max_width - (border_padding * 2)
        inner_height = diagram_height - (border_padding * 2)

        # Calc space for labels
        font = self._fonts["small"]

        # Width dimension indicator space
        wid_text = f"{ship_wid}m"
        wid_label_width = self._get_text_width(font, wid_text)
        left_label_space = wid_label_width + (
            self._dimension_label_spacing * 4
        )  # Text + spacing for lines

        # Length dimension indicator space
        len_text = f"{ship_len}m"
        len_label_height = self._get_text_height(font, len_text)
        bottom_label_space = len_label_height + (
            self._dimension_label_spacing * 4
        )  # Text + spacing for lines

        # Available space for ship + dimension indicators + padding
        ship_padding = self._ship_inner_padding
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

        ship_centre_x = ship_area_left + (ship_area_width / 2)
        ship_centre_y = ship_area_top + (ship_area_height / 2)

        # Draw ship outline
        self._draw_ship_outline(
            draw, ship_centre_x, ship_centre_y, scaled_len, scaled_wid
        )

        # Draw GPS receiver position
        ship_top_left_x = ship_centre_x - (scaled_len / 2)
        ship_top_left_y = ship_centre_y - (scaled_wid / 2)

        dot_x = ship_top_left_x + (ship_stern * scale_factor)
        dot_y = ship_top_left_y + (ship_port * scale_factor)

        draw.ellipse(
            [
                dot_x - self._mast_size / 2,
                dot_y - self._mast_size / 2,
                dot_x + self._mast_size / 2,
                dot_y + self._mast_size / 2,
            ],
            fill=self._palette["accent"],
        )

        # Draw dimension labels
        self._draw_dimension_labels(
            draw,
            font,
            ship_centre_x,
            ship_centre_y,
            scaled_len,
            scaled_wid,
            ship_len,
            ship_wid,
        )

        return y + diagram_height

    def _draw_ship_outline(
        self,
        draw: ImageDraw.ImageDraw,
        centre_x: float,
        centre_y: float,
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

        top_left = (centre_x - half_len, centre_y - half_wid)
        top_right = (centre_x + half_len - nose_len, centre_y - half_wid)
        nose = (centre_x + half_len, centre_y)
        bottom_right = (centre_x + half_len - nose_len, centre_y + half_wid)
        bottom_left = (centre_x - half_len, centre_y + half_wid)

        points = [top_left, top_right, nose, bottom_right, bottom_left]
        draw.polygon(points, outline=self._palette["accent"], width=self._line_width)

    def _draw_dimension_labels(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        centre_x: float,
        centre_y: float,
        scaled_len: int,
        scaled_wid: int,
        actual_len: int,
        actual_wid: int,
    ) -> None:
        """Draw measurement guides and text for length and width."""
        spacing = self._dimension_label_spacing
        half_len = scaled_len / 2
        half_wid = scaled_wid / 2

        # Length on bottom
        left_x = centre_x - half_len
        right_x = centre_x + half_len
        bottom_y = centre_y + half_wid

        draw.line(
            [
                (left_x, bottom_y + spacing),
                (left_x, bottom_y + spacing * 2),
                (centre_x, bottom_y + spacing * 2),
                (centre_x, bottom_y + spacing * 3),
                (centre_x, bottom_y + spacing * 2),
                (right_x, bottom_y + spacing * 2),
                (right_x, bottom_y + spacing),
            ],
            fill=self._palette["accent"],
            width=self._line_width,
        )

        len_text = f"{actual_len}m"
        len_text_width, len_text_height = self._get_text_size(font, len_text)
        draw.text(
            (centre_x - (len_text_width / 2), bottom_y + spacing * 4),
            len_text,
            fill=self._palette["accent"],
            font=font,
        )

        # Width vertically on left
        top_y = centre_y - half_wid
        middle_y = centre_y

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
            width=self._line_width,
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
        x: int,
        y: int,
        region_width: int,
        vessel: dict[str, Any],
    ) -> int:
        """Draw the vessel name with an underline and return new y."""
        font = self._fonts["large"]
        name = vessel.get("name") or vessel.get("identifier") or "Unknown"

        text_width, text_height = self._get_text_size(font, name)
        centre_x = x + region_width / 2
        name_left = int(centre_x - text_width / 2)

        # Draw name
        draw.text((name_left, y), name, fill=self._palette["text"], font=font)
        y += text_height + self._name_underline_gap
        # todo: magic 12 number otherwise the line goes through the text even after the height calc.
        # Need to figure out what's going wrong with this part

        # Draw underline
        draw.line(
            [
                (name_left, y),
                (int(centre_x + text_width / 2), y),
            ],
            fill=self._palette["line"],
            width=self._line_width,
        )

        y += self._section_spacing
        return y

    # Rows are dropped in this order when content would overflow the
    # available vertical space. MMSI and Vessel Type are never dropped.
    ROW_DROP_ORDER = ("Speed", "Destination", "Callsign")

    def _info_height_for(self, n_rows: int) -> int:
        """Return the visual height of n info rows.

        The visual bottom is the last separator line. The trailing
        line_spacing after it is whitespace and not counted.
        """
        if n_rows <= 0:
            return 0
        pitch = self._info_row_spacing + self._info_line_spacing
        return n_rows * pitch - self._info_line_spacing

    def _fit_info_rows(
        self, rows: list[dict[str, Any]], available_height: int
    ) -> list[dict[str, Any]]:
        """Drop rows in priority order until they fit within available_height."""
        rows = list(rows)
        while self._info_height_for(len(rows)) > available_height and rows:
            for label in self.ROW_DROP_ORDER:
                idx = next((i for i, r in enumerate(rows) if r["label"] == label), None)
                if idx is not None:
                    del rows[idx]
                    break
            else:
                # No droppable row found, leave the list as-is and accept overflow.
                break
        return rows

    def _get_info_rows(self, vessel: dict[str, Any]) -> list[dict[str, Any]]:
        """Build the ordered list of info rows available for a vessel."""
        rows = [
            {"label": "MMSI", "value": vessel.get("identifier") or "Unknown", "icon": self._icons["id"]},
            {"label": "Callsign", "value": vessel.get("callsign") or "Unknown", "icon": self._icons["callsign"]},
            {
                "label": "Vessel Type",
                "value": vessel.get("ship_type_name") or "Unknown",
                "icon": self._icons["ship_type"],
            },
        ]

        if "destination" in vessel and vessel["destination"]:
            rows.append({"label": "Destination", "value": vessel["destination"], "icon": self._icons["destination"]})

        if "speed" in vessel and vessel["speed"] is not None:
            rows.append({"label": "Speed", "value": f"{vessel['speed']} kts", "icon": self._icons["speed"]})

        return rows

    def _draw_vessel_info(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        region_width: int,
        info_rows: list[dict[str, Any]],
    ) -> int:
        """Draw key/value rows of data about the vessel."""
        font = self._fonts["medium"]

        for row in info_rows:
            y = self._draw_info_row(draw, font, x, y, region_width, row["label"], row["value"], row["icon"])

        return y

    def _draw_info_row(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        x: int,
        y: int,
        region_width: int,
        label: str,
        value: str,
        icon: Image.Image,
    ) -> int:
        """Draw a single info row with label on the left and value on the right."""
        # Draw icon
        self._renderer.canvas.paste(icon, (x,y), icon)

        # Draw label and value
        label_x = x + self._info_row_icon_gap
        value_width = self._get_text_width(font, value)
        value_x = x + region_width - value_width

        draw.text((label_x, y), label, fill=self._palette["text"], font=font)
        draw.text((value_x, y), value, fill=self._palette["text"], font=font)

        y += self._info_row_spacing

        draw.line([(x, y), (x + region_width, y)], fill=self._palette["line"], width=self._line_width)

        y += self._info_line_spacing
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
        ],
    )

def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system"""
    return ZoneScreen(**kwargs)
