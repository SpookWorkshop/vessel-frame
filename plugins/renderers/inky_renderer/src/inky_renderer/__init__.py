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
from inky.auto import auto


class InkyRenderer(RendererPlugin):
    """Renderer plugin that draws a Pillow canvas to an Inky screen."""

    MIN_RENDER_INTERVAL: int = 60

    def __init__(
        self,
        *,
        width: int = 480,
        height: int = 800,
        orientation: str = "portrait",
    ) -> None:
        plugin_dir = Path(__file__).parent
        font_path = plugin_dir / "fonts" / "Inter" / "Inter-VariableFont_opsz,wght.ttf"

        if not font_path.exists():
            raise FileNotFoundError(f"Font file not found: {font_path}")

        try:
            self._fonts = {
                "xsmall": ImageFont.truetype(font_path, 8),
                "small": ImageFont.truetype(font_path, 14),
                "medium": ImageFont.truetype(font_path, 20),
                "large": ImageFont.truetype(font_path, 35),
            }
        except Exception as e:
            raise RuntimeError(f"Failed to load fonts from {font_path}: {e}") from e

        self._display = auto()
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

    def flush(self) -> None:
        """Save the current canvas to the configured output path."""
        image = self._canvas
        
        # Inky expects landscape so rotate if we're in portrait
        if self._orientation == "portrait":
            image = image.rotate(90, expand=True)

        self._display.set_image(image)
        self._display.show()

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
        plugin_name="inky_renderer",
        plugin_type="renderer",
        fields=[
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

    return InkyRenderer(**kwargs)
