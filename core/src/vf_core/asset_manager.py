from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


@dataclass
class VariableFont:
    file: Path
    italic_file: Path
    def load(self, variant: str, size: int, italic: bool) -> ImageFont.FreeTypeFont:
        f = ImageFont.truetype(self.italic_file if italic else self.file, size)
        try:
            f.set_variation_by_axes([size, int(variant)])
        except ValueError:
            f.set_variation_by_name(variant)
        return f


@dataclass
class StaticFont:
    dir: Path
    pattern: str = "{family}-{variant}.ttf"
    family: str | None = None
    def load(self, variant: str, size: int, italic: bool) -> ImageFont.FreeTypeFont:
        fam = self.family or self.dir.name
        return ImageFont.truetype(self.dir / self.pattern.format(family=fam, variant=variant), size)


class AssetManager:
    def __init__(self,
        path: Path,
        primary_font: StaticFont | VariableFont | None = None,
        secondary_font: StaticFont | VariableFont | None = None,
    ) -> None:
        self._fonts_path = path / "fonts"

        if not primary_font:
            primary_font = VariableFont(file = self._fonts_path / "Literata/Literata-VariableFont_opsz,wght.ttf",
                                        italic_file = self._fonts_path / "Literata/Literata-Italic-VariableFont_opsz,wght.ttf")

        if not secondary_font:
            secondary_font = StaticFont(dir = self._fonts_path / "IBM_Plex_Mono", family = "IBMPlexMono")

        self._fonts = {
            "primary": primary_font,
            "secondary": secondary_font
        }

        self._font_cache: dict[tuple[str,str,int,bool], ImageFont.FreeTypeFont] = {}

    def get_font(self, role: str, variation: str, size: int, italic: bool = False) -> ImageFont.FreeTypeFont:
        font = self._font_cache.get((role, variation, size, italic))

        if not font:
            font = self._fonts[role].load(variation, size, italic)
            self._font_cache[(role, variation, size, italic)] = font

        return font
