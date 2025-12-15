from __future__ import annotations
from typing import Any
from vf_core.plugin_types import (
    ConfigField,
    ConfigFieldType,
    ConfigSchema,
    RendererPlugin,
)
from PIL import Image, ImageFont, ImageDraw
from pathlib import Path


class ImageRenderer(RendererPlugin):
    """Renderer plugin that draws an image canvas using Pillow."""

    MIN_RENDER_INTERVAL: int = 0

    def __init__(
        self,
        *,
        out_path: str = "data/image.png",
        width: int = 480,
        height: int = 800,
        orientation: str = "portrait",
    ) -> None:
        self._out_path = out_path
        self._orientation = orientation

        # Swap width and height if they weren't passed in a way that expresses the orientation
        if (orientation == "portrait" and width > height) or (
            orientation == "landscape" and height > width
        ):
            self._width = int(height)
            self._height = int(width)
        else:
            self._width = int(width)
            self._height = int(height)

        self._canvas: Image.Image = Image.new("RGB", (self._width, self._height))
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    async def flush(self) -> None:
        """Save the current canvas to the configured output path."""
        self.canvas.save(self._out_path, "png")

    def clear(self) -> None:
        """Clear the canvas by filling it with the background colour."""
        draw = ImageDraw.Draw(self._canvas)
        draw.rectangle(
            [(0, 0), (self._width, self._height)], fill=self.palette["background"]
        )

    @property
    def palette(self) -> dict[str, str]:
        """Colour palette for drawing operations.

        Returns:
            dict[str, str]: A mapping of theme colour names to hex values.
        """

        return {
            "background": "#0000FF",
            "foreground": "#FFFFFF",
            "line": "#0000FF",
            "text": "#0000FF",
            "accent": "#000000",
        }

    @property
    def canvas(self) -> Image.Image:
        """Current Pillow image canvas."""
        return self._canvas

    @property
    def fonts(self) -> dict[str, ImageFont.FreeTypeFont]:
        """Dictionary of preloaded font sizes."""
        return self._fonts


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin.

    Defines editable fields for the admin panel.

    Returns:
        ConfigSchema: Schema describing this plugin's configuration options.
    """
    
    return ConfigSchema(
        plugin_name="image_renderer",
        plugin_type="renderer",
        fields=[
            ConfigField(
                key="out_path",
                label="File Path",
                field_type=ConfigFieldType.STRING,
                default="data/image.png",
                description="File output path",
            ),
            ConfigField(
                key="width",
                label="Width",
                field_type=ConfigFieldType.INTEGER,
                default=480,
                required=True
            ),
            ConfigField(
                key="height",
                label="Height",
                field_type=ConfigFieldType.INTEGER,
                default=800,
                required=True
            ),
            ConfigField(
                key="orientation",
                label="Orientation",
                field_type=ConfigFieldType.SELECT,
                default="portrait",
                options=["portrait", "landscape"],
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> RendererPlugin:
    """
    Factory function required by the entry point.
    """

    return ImageRenderer(**kwargs)
