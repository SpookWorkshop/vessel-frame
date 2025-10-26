from __future__ import annotations
import asyncio
import datetime
import math
from typing import Any
from contextlib import suppress
from PIL import Image, ImageDraw, ImageFont

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import ScreenPlugin, RendererPlugin
from vf_core.vessel_manager import VesselManager
from vf_core.ais_utils import get_vessel_full_type_name

class TableScreen(ScreenPlugin):
    """
    Screen to display a table of vessels which were recently observed
    """
    
    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20
    ROW_SPACING = 10
    COLUMN_GAP_DIVISOR = 2
    HEADER_LABELS = {
        'name': "Ship Name",
        'type': "Ship Type", 
        'time': "Last Seen"
    }

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        in_topic: str = "vessel.updated"
    ) -> None:
        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None
        self._palette = renderer.palette

    async def activate(self) -> None:
        if self._task and not self._task.done():
            return
        
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                await self._render()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            # Expected on deactivate
            raise
        except Exception as e:
            print(f"[table_screen] Update loop crashed: {e}")
            raise

    async def _render(self) -> None:
        vessels = self._vessel_manager.get_recent_vessels()

        fonts = self._renderer.fonts
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size
        
        self._renderer.clear()
        self._draw_container(draw, width, height)
        
        text_x = self.SCREEN_PADDING + self.CONTAINER_PADDING_HORZ
        text_y = self.SCREEN_PADDING + self.CONTAINER_PADDING_VERT
        
        text_y = self._draw_header(draw, fonts, text_x, text_y)
        text_y += 35
        
        self._draw_table(draw, fonts, vessels, text_x, text_y, width)
        
        self._renderer.flush()

    def _draw_container(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        draw.rounded_rectangle(
            [(self.SCREEN_PADDING, self.SCREEN_PADDING),
             (width - self.SCREEN_PADDING, height - self.SCREEN_PADDING)],
            radius=8,
            fill=self._palette['foreground']
        )

    def _draw_header(
        self,
        draw: ImageDraw.ImageDraw,
        fonts: dict[str, ImageFont.FreeTypeFont],
        x: int,
        y: int
    ) -> int:
        title_font = fonts['medium']
        title_text = "Ship Tracker"

        subtitle_font = fonts['small']
        subtitle_text = datetime.datetime.now().strftime("%A - %d/%m/%y %H:%M")

        draw.text((x, y), title_text, fill=self._palette['text'], font=title_font)
        y += self._get_text_height(title_font, title_text) + 4
        draw.text((x, y), subtitle_text, fill=self._palette['text'], font=subtitle_font)
        
        return y

    def _draw_table(
        self,
        draw: ImageDraw.ImageDraw,
        fonts: dict[str, ImageFont.FreeTypeFont],
        vessels: list[dict[str, Any]],
        x: int,
        y: int,
        width: int
    ) -> None:
        body_font = fonts['small']
        
        col_widths = self._calculate_column_widths(body_font, vessels)
        gap = self._calculate_column_gap(x, width, col_widths)
        
        y = self._draw_table_headers(draw, body_font, x, y, width, col_widths, gap)
        
        for vessel in vessels:
            y = self._draw_table_row(draw, body_font, vessel, x, y, width, col_widths, gap)

    def _draw_table_headers(
        self,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont,
        x: int,
        y: int,
        width: int,
        col_widths: dict[str, int],
        gap: int
    ) -> int:
        draw.text((x, y), self.HEADER_LABELS['name'], fill=self._palette['text'], font=font)
        draw.text((x + col_widths['name'] + gap, y), self.HEADER_LABELS['type'], fill=self._palette['text'], font=font)
        
        last_seen_width = self._get_text_width(font, self.HEADER_LABELS['time'])
        draw.text((width - x - last_seen_width, y), self.HEADER_LABELS['time'], fill=self._palette['text'], font=font)
        
        text_height = self._get_text_height(font, self.HEADER_LABELS['name'])
        y += text_height + self.ROW_SPACING
        draw.line([(x, y), (width - x, y)], fill=self._palette['line'], width=2)
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
        gap: int
    ) -> int:
        ship_name = vessel.get("name", "Unknown")
        ship_type = get_vessel_full_type_name(vessel.get("type", -1))
        timestamp = self._format_timestamp(vessel.get("ts", 0))
        
        name_x = x
        type_x = x + col_widths['name'] + gap

        timestamp_width = self._get_text_width(font, timestamp)
        time_x = width - x - timestamp_width
        
        draw.text((name_x, y), ship_name, fill=self._palette['text'], font=font)
        draw.text((type_x, y), ship_type, fill=self._palette['text'], font=font)
        draw.text((time_x, y), timestamp, fill=self._palette['text'], font=font)
        
        text_height = self._get_text_height(font, ship_name)
        y += text_height + self.ROW_SPACING
        draw.line([(x, y), (width - x, y)], fill=self._palette['line'], width=2)
        y += self.ROW_SPACING
        
        return y

    def _calculate_column_widths(
        self,
        font: ImageFont.FreeTypeFont,
        vessels: list[dict[str, Any]]
    ) -> dict[str, int]:
        widths = {
            'name': self._get_text_width(font, self.HEADER_LABELS['name']),
            'type': self._get_text_width(font, self.HEADER_LABELS['type']),
            'time': self._get_text_width(font, self.HEADER_LABELS['time'])
        }
        
        for vessel in vessels:
            ship_name = vessel.get("name", "Unknown")
            ship_type = get_vessel_full_type_name(vessel.get("type", -1))
            timestamp = self._format_timestamp(vessel.get("ts", 0))
            
            widths['name'] = max(widths['name'], self._get_text_width(font, ship_name))
            widths['type'] = max(widths['type'], self._get_text_width(font, ship_type))
            widths['time'] = max(widths['time'], self._get_text_width(font, timestamp))
        
        return widths

    def _format_timestamp(self, timestamp: int) -> str:
        return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

    def _calculate_column_gap(
        self,
        start_x: int,
        width: int,
        col_widths: dict[str, int]
    ) -> int:
        total_text_width = sum(col_widths.values())
        available_space = width - (2 * start_x) - total_text_width
        return available_space // self.COLUMN_GAP_DIVISOR

    def _get_text_width(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]

    def _get_text_height(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        bbox = font.getbbox(text)
        return bbox[3] - bbox[1]

def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system"""
    return TableScreen(**kwargs)