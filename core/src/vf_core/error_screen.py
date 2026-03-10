from __future__ import annotations

import logging

from PIL import ImageDraw, ImageFont

from .asset_manager import AssetManager
from .plugin_types import RendererPlugin, ScreenPlugin


class ErrorScreen(ScreenPlugin):
    """Sccreen displayed when a system.error event is received on the bus.

    Owned by ScreenManager rather than a plugin, not loaded via entry points.
    Call set_error() with the message payload before calling activate().
    """

    SCREEN_PADDING = 10
    CONTAINER_PADDING_HORZ = 20
    CONTAINER_PADDING_VERT = 20

    _PALETTE = {
        "background": "#8B0000",
        "foreground": "#FFE4E4",
        "line": "#CC0000",
        "text": "#3D0000",
    }

    def __init__(self, renderer: RendererPlugin, asset_manager: AssetManager) -> None:
        self._logger = logging.getLogger(__name__)
        self._renderer = renderer
        self._message = ""
        self._recovery = ""
        self._fonts = {
            "title": asset_manager.get_font("default", "Bold", 24),
            "body": asset_manager.get_font("default", "SemiBold", 16),
            "hint": asset_manager.get_font("default", "SemiBold", 13),
        }

    def set_error(self, message: str, recovery: str = "") -> None:
        """Store the error details to display on the next activate()."""
        self._message = message
        self._recovery = recovery

    async def activate(self) -> None:
        """Render the error screen immediately."""
        await self._render()

    async def deactivate(self) -> None:
        pass

    async def _render(self) -> None:
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size

        draw.rectangle([(0, 0), (width, height)], fill=self._PALETTE["background"])

        draw.rounded_rectangle(
            [
                (self.SCREEN_PADDING, self.SCREEN_PADDING),
                (width - self.SCREEN_PADDING, height - self.SCREEN_PADDING),
            ],
            radius=8,
            fill=self._PALETTE["foreground"],
        )

        x = self.SCREEN_PADDING + self.CONTAINER_PADDING_HORZ
        y = self.SCREEN_PADDING + self.CONTAINER_PADDING_VERT
        max_text_width = width - 2 * x

        title_font = self._fonts["title"]
        draw.text((x, y), "System Error", fill=self._PALETTE["text"], font=title_font)
        y += self._text_height(title_font, "System Error") + 8

        draw.line([(x, y), (width - x, y)], fill=self._PALETTE["line"], width=2)
        y += 16

        body_font = self._fonts["body"]
        for line in self._wrap(body_font, self._message, max_text_width):
            draw.text((x, y), line, fill=self._PALETTE["text"], font=body_font)
            y += self._text_height(body_font, line) + 4

        if self._recovery:
            y += 16
            hint_font = self._fonts["hint"]
            for line in self._wrap(hint_font, self._recovery, max_text_width):
                draw.text((x, y), line, fill=self._PALETTE["text"], font=hint_font)
                y += self._text_height(hint_font, line) + 4

        await self._renderer.flush()

    def _wrap(self, font: ImageFont.FreeTypeFont, text: str, max_width: int) -> list[str]:
        """Word-wrap text into lines that fit within max_width pixels."""
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            bbox = font.getbbox(candidate)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _text_height(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        bbox = font.getbbox(text)
        return bbox[3] - bbox[1]
