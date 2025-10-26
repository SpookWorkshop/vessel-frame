from __future__ import annotations
from typing import Any
from vf_core.plugin_types import RendererPlugin
from PIL import Image, ImageFont, ImageDraw
from pathlib import Path

class ImageRenderer(RendererPlugin):
    def __init__(
        self,
        *,
        out_path: str = "data/image.png",
        width: int = 480,
        height: int = 800
    ) -> None:
        plugin_dir = Path(__file__).parent
        font_path = plugin_dir / 'fonts' / 'Inter' / 'Inter-VariableFont_opsz,wght.ttf'

        self._fonts = {
            'xsmall': ImageFont.truetype(font_path, 8),
            'small': ImageFont.truetype(font_path, 14),
            'medium': ImageFont.truetype(font_path, 20),
            'large': ImageFont.truetype(font_path, 35),
        }

        self._canvas: Image.Image = Image.new("RGB", (width,height))
        self._out_path = out_path
        self._width = width
        self._height = height

        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    def flush(self):
        self.canvas.save(self._out_path, "png")

    def clear(self):
        draw = ImageDraw.Draw(self._canvas)
        draw.rectangle([(0, 0),(self._width, self._height)], fill=self.palette['background'])

    @property
    def palette(self) -> dict[str, str]:
        return {
            'background': '#0000FF',
            'foreground': '#FFFFFF',
            'line': '#0000FF',
            'text': '#0000FF'
        }

    @property
    def canvas(self) -> Image.Image:
        return self._canvas

    @property
    def fonts(self) -> list[ImageFont]:
        return self._fonts

def make_plugin(**kwargs: Any) -> RendererPlugin:
    """
    Factory function required by the entry point.
    """

    return ImageRenderer(**kwargs)