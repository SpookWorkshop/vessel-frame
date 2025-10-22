from __future__ import annotations
from typing import Any
from vf_core.plugin_types import RendererPlugin
from PIL import Image

class ImageRenderer(RendererPlugin):
    def __init__(
        self,
        *,
        out_dir: str = "data",
    ) -> None:
        self._out_dir = out_dir

    def render(self, image: Image):
        image.save(self._out_dir + "/img.png", "png")

def make_plugin(**kwargs: Any) -> RendererPlugin:
    """
    Factory function required by the entry point.
    """

    return ImageRenderer(**kwargs)