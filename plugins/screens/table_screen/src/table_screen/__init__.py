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


class TableScreen(ScreenPlugin):
    """
    Screen to display a table of vessels which were recently observed
    """

    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20
    ROW_SPACING = 10
    MIN_COLUMN_GAP = 20
    NAME_COL_FRACTION = 0.4
    HEADER_LABELS = {"name": "Ship Name", "type": "Ship Type", "time": "Last Seen"}
    TIME_REFERENCE = "00:00:00"
    WIDEST_TYPE_REFERENCE = "Anti-pollution Equip."
    ELLIPSIS = "\u2026"

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

        # Scale all sizes relative to a 480-px short-edge baseline
        # (matches the 7.3" 800x480 inky display). Never scale below 1.0,
        # smaller displays keep the baseline sizing so fonts stay readable.
        canvas_w, canvas_h = renderer.canvas.size
        self._scale = max(1.0, min(canvas_w, canvas_h) / 480)

        self._screen_padding = int(self.SCREEN_PADDING * self._scale)
        self._container_padding_horz = int(self.CONTAINER_PADDING_HORZ * self._scale)
        self._container_padding_vert = int(self.CONTAINER_PADDING_VERT * self._scale)
        self._row_spacing = int(self.ROW_SPACING * self._scale)
        self._min_column_gap = int(self.MIN_COLUMN_GAP * self._scale)
        self._header_gap = int(35 * self._scale)
        self._title_gap = int(4 * self._scale)
        self._icon_title_gap = int(20 * self._scale)
        self._container_radius = int(8 * self._scale)
        self._line_width = max(1, int(2 * self._scale))

        self._fonts: dict[str,ImageFont.FreeTypeFont] = {}
        self._fonts["small"] = self._asset_manager.get_font("default", "SemiBold", int(14 * self._scale))
        self._fonts["medium"] = self._asset_manager.get_font("default", "SemiBold", int(20 * self._scale))

        # Uniform row pitch used by both packing calc and draw code. "SHIP NAME"
        # matches typical uppercase ship names
        self._body_text_height = self._get_text_height(self._fonts["small"], "SHIP NAME")
        self._row_height = self._body_text_height + 2 * self._row_spacing

        self._icons: dict[str,Image.Image] = {}
        self._icons["vessel"] = self._asset_manager.get_icon("vessel", int(40 * self._scale), self._palette["icon"])

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
        self._render_strategy.request_render()
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
                self._render_strategy.request_render()
        except asyncio.CancelledError:
            # Expected on deactivate
            raise
        except Exception:
            self._logger.exception("Update loop crashed")
            raise

    async def _render(self) -> None:
        """Render the table of most recently observed vessels."""

        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size

        self._renderer.clear()
        self._draw_container(draw, width, height)

        text_x = self._screen_padding + self._container_padding_horz
        text_y = self._screen_padding + self._container_padding_vert

        text_y = self._draw_header(draw, text_x, text_y)
        text_y += self._header_gap

        max_data_rows = self._calculate_max_data_rows(text_y, height)
        vessels = self._vessel_manager.get_recent_vessels(limit=max_data_rows)

        self._draw_table(draw, vessels, text_x, text_y, width)

        await self._renderer.flush()

    def _calculate_max_data_rows(self, table_top_y: int, height: int) -> int:
        """
        Calculate how many rows fit between the table header and the
        bottom of the container.
        """
        # Bottom reference is the container border.
        body_bottom = height - self._screen_padding - self._row_spacing
        available = body_bottom - table_top_y

        if available <= 0 or self._row_height <= 0:
            return 0

        total_rows = (available + self._row_spacing) // self._row_height
        return max(0, total_rows - 1)

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
        """
        Draw the title and timestamp header.

        Returns:
            int: Updated y-position after drawing.
        """

        title_font = self._fonts["medium"]
        title_text = "Ship Tracker"

        subtitle_font = self._fonts["small"]
        date_format = os.getenv("DATE_FORMAT", "%d/%m/%y")
        subtitle_text = datetime.datetime.now().strftime(f"%A - {date_format} %H:%M")

        icon = self._icons["vessel"]
        self._renderer.canvas.paste(icon, (x,y), icon)
        x += icon.size[0] + self._icon_title_gap

        draw.text((x, y), title_text, fill=self._palette["text"], font=title_font)
        y += self._get_text_height(title_font, title_text) + self._title_gap
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
        available = width - 2 * x

        col_caps = self._compute_column_caps(available)
        columns = self._select_columns(col_caps, available)
        if "time" not in columns:
            # 2 col: let the name column grow into the space the time column
            # would have occupied.
            col_caps["name"] = available - col_caps["type"] - self._min_column_gap

        col_widths = self._compute_actual_widths(body_font, vessels, columns, col_caps)
        col_layout = self._compute_column_layout(x, width, columns, col_widths)

        y = self._draw_table_headers(draw, body_font, x, y, width, columns, col_layout)

        for vessel in vessels:
            y = self._draw_table_row(
                draw, body_font, vessel, x, y, width, columns, col_layout
            )

    def _draw_table_headers(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        x: int,
        y: int,
        width: int,
        columns: list[str],
        col_layout: dict[str, tuple[int, int]],
    ) -> int:
        """Draw column headers and a divider line."""

        texts = {col: self.HEADER_LABELS[col] for col in columns}
        self._draw_row_cells(draw, font, texts, columns, col_layout, y)

        y += self._body_text_height + self._row_spacing
        draw.line([(x, y), (width - x, y)], fill=self._palette["line"], width=self._line_width)
        y += self._row_spacing

        return y

    def _draw_table_row(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        vessel: dict[str, Any],
        x: int,
        y: int,
        width: int,
        columns: list[str],
        col_layout: dict[str, tuple[int, int]],
    ) -> int:
        """Draw a single vessel row and return the next y-position."""

        texts = {
            "name": self._ship_name(vessel),
            "type": self._format_ship_type(vessel.get("ship_type_name")),
            "time": self._format_timestamp(vessel.get("ts", 0)),
        }
        self._draw_row_cells(draw, font, texts, columns, col_layout, y)

        y += self._body_text_height + self._row_spacing
        draw.line([(x, y), (width - x, y)], fill=self._palette["line"], width=self._line_width)
        y += self._row_spacing

        return y

    def _draw_row_cells(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        texts: dict[str, str],
        columns: list[str],
        col_layout: dict[str, tuple[int, int, str]],
        y: int,
    ) -> None:
        """Draw each column's text, truncating with ellipsis and aligning per column."""
        for col in columns:
            col_x, col_width, align = col_layout[col]
            text = self._truncate_to_width(font, texts.get(col, ""), col_width)
            if align == "right":
                text_w = self._get_text_width(font, text)
                draw_x = col_x + col_width - text_w
            else:
                draw_x = col_x
            draw.text((draw_x, y), text, fill=self._palette["text"], font=font)

    def _compute_column_caps(self, available_row_width: int) -> dict[str, int]:
        """
        Return stable maximum pixel widths per column.

        Derived from fixed references rather than current vessel data, so the
        3v2 column decision stays consistent across renders on the same
        screen. Each cap is floored at its header-label width so headers are
        never truncated even when data values are narrower.
        """
        font = self._fonts["small"]
        header_widths = {
            col: self._get_text_width(font, label)
            for col, label in self.HEADER_LABELS.items()
        }
        return {
            "name": max(header_widths["name"], int(available_row_width * self.NAME_COL_FRACTION)),
            "type": max(header_widths["type"], self._get_text_width(font, self.WIDEST_TYPE_REFERENCE)),
            "time": max(header_widths["time"], self._get_text_width(font, self.TIME_REFERENCE)),
        }

    def _select_columns(
        self, col_caps: dict[str, int], available_row_width: int
    ) -> list[str]:
        """Pick visible columns based on caps + minimum gaps."""
        three_col_width = (
            col_caps["name"] + col_caps["type"] + col_caps["time"]
            + 2 * self._min_column_gap
        )
        if three_col_width <= available_row_width:
            return ["name", "type", "time"]
        return ["name", "type"]

    def _compute_actual_widths(
        self,
        font: ImageFont.FreeTypeFont,
        vessels: list[dict[str, Any]],
        columns: list[str],
        col_caps: dict[str, int],
    ) -> dict[str, int]:
        """Return the pixel width actually needed per column, bounded by caps."""
        widths = {
            col: self._get_text_width(font, self.HEADER_LABELS[col]) for col in columns
        }
        for vessel in vessels:
            texts = {
                "name": self._ship_name(vessel),
                "type": self._format_ship_type(vessel.get("ship_type_name")),
                "time": self._format_timestamp(vessel.get("ts", 0)),
            }
            for col in columns:
                widths[col] = max(widths[col], self._get_text_width(font, texts[col]))
        return {col: min(widths[col], col_caps[col]) for col in columns}

    def _compute_column_layout(
        self,
        x: int,
        width: int,
        columns: list[str],
        col_widths: dict[str, int],
    ) -> dict[str, tuple[int, int, str]]:
        """
        Return {col: (x_left, cell_width, align)} for each visible column.

        3-col: name at x (left), time flush to right, type centred in the gap.
        2-col: name at x (left), type immediately after with MIN_COLUMN_GAP.
        """
        layout: dict[str, tuple[int, int, str]] = {}
        if "time" in columns:
            layout["name"] = (x, col_widths["name"], "left")
            layout["time"] = (width - x - col_widths["time"], col_widths["time"], "right")
            name_right = x + col_widths["name"]
            time_left = width - x - col_widths["time"]
            free = time_left - name_right
            type_x = name_right + max(0, (free - col_widths["type"]) // 2)
            layout["type"] = (type_x, col_widths["type"], "left")
        else:
            layout["name"] = (x, col_widths["name"], "left")
            type_x = x + col_widths["name"] + self._min_column_gap
            layout["type"] = (type_x, col_widths["type"], "left")
        return layout

    def _ship_name(self, vessel: dict[str, Any]) -> str:
        """Return the display name for a vessel, falling back to identifier."""
        name = vessel.get("name")
        if name == "Unknown" or name is None:
            name = vessel.get("identifier") or "Unknown"
        return name

    def _truncate_to_width(
        self, font: ImageFont.FreeTypeFont, text: str, max_width: int
    ) -> str:
        """Truncate text with a trailing ellipsis so it fits within max_width."""
        if self._get_text_width(font, text) <= max_width:
            return text
        if self._get_text_width(font, self.ELLIPSIS) > max_width:
            return ""
        for i in range(len(text) - 1, 0, -1):
            candidate = text[:i].rstrip() + self.ELLIPSIS
            if self._get_text_width(font, candidate) <= max_width:
                return candidate
        return self.ELLIPSIS

    def _format_ship_type(self, ship_type_name: str | None) -> str:
        """Return the main ship type, stripping the subtype classification."""
        if not ship_type_name:
            return "Unknown"
        return ship_type_name.split(" - ", 1)[0]

    def _format_timestamp(self, timestamp: int) -> str:
        """Convert a Unix timestamp to HH:MM:SS, or '--:--:--' on error."""
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        except (ValueError, OSError):
            return "--:--:--"

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
