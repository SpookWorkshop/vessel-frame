"""Generic PIL text/font helpers for screen rendering.

Any screen plugin can mix TextRenderingMixin in to get
anchored text drawing and font metric helpers.
"""
from __future__ import annotations
from PIL import ImageDraw, ImageFont

__all__ = ["FONT_FLOOR", "split_two", "TextRenderingMixin"]

FONT_FLOOR = 7  # never render a font smaller than this


def split_two(name: str) -> list[str]:
    """Split a string into two balanced lines on the space nearest the middle.

    Returns a single-element list when there is no space to break on.
    """
    spaces = [i for i, c in enumerate(name) if c == " "]
    if not spaces:
        return [name]
    mid = len(name) / 2
    i = min(spaces, key=lambda j: abs(j - mid))
    return [name[:i], name[i + 1:]]


class TextRenderingMixin:
    """Mixin: anchored text drawing and font metric helpers.

    Hosts must define self._palette (colour dict) and self._asset_manager.
    """

    # PIL anchor codes per horizontal alignment, all on the text baseline ("s").
    _ANCHORS = {"left": "ls", "centre": "ms", "right": "rs"}

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        x: float,
        y: float,
        text: str,
        font: ImageFont.FreeTypeFont,
        halign: str = "left",
        fill: str | tuple | None = None,
        baseline_y: float | None = None,
    ) -> tuple[int, float, int]:
        """Draw text at (x, y) where y is the top of the ascender line.

        Returns (line_height, baseline_y, text_width). Pass baseline_y from a
        previous call to align mixed-size text on the same visual baseline.
        halign: "left" | "centre" | "right"
        """
        ascent, descent = font.getmetrics()
        bl_y = baseline_y if baseline_y is not None else y + ascent
        draw.text(
            (x, bl_y), text, font=font,
            fill=fill if fill is not None else self._palette["text"],
            anchor=self._ANCHORS[halign],
        )
        return ascent + descent, bl_y, self._text_width(font, text)

    def _text_width(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Rendered width of text in pixels for the given font."""
        left, _, right, _ = font.getbbox(text)
        return right - left

    def _line_height(self, font: ImageFont.FreeTypeFont) -> int:
        a, d = font.getmetrics()
        return a + d

    def _ink_top(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Pixels of empty leading above the glyph ink (ascender-top to ink-top)."""
        return font.getbbox(text)[1]

    def _ink_bottom(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        """Ascender-top to ink-bottom, the visible height when drawn from top."""
        return font.getbbox(text)[3]

    def _fit_font(
        self,
        role: str,
        variation: str,
        text: str,
        max_w: float,
        max_px: int,
        min_px: int,
        italic: bool = False,
    ) -> ImageFont.FreeTypeFont:
        """Largest font (down to min_px) whose text fits within max_w."""
        am = self._asset_manager
        px = max_px
        while px > min_px:
            f = am.get_font(role, variation, px, italic)
            if self._text_width(f, text) <= max_w:
                return f
            px -= 1
        return am.get_font(role, variation, min_px, italic)
