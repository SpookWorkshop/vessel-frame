from pathlib import Path
from PIL import Image, ImageFont
from dataclasses import dataclass

@dataclass
class VariableFont:
    file: Path
    italic_file: Path
    def load(self, variant: str, size: int, italic: bool) -> ImageFont.FreeTypeFont:
        print(f"VARIABLE font load {self.file} - {self.file}")
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
        print("STATIC font load")
        fam = self.family or self.dir.name
        return ImageFont.truetype(self.dir / self.pattern.format(family=fam, variant=variant), size)

class AssetManager:
    ICON_MAP = {
        "vessel": "vessel.png",
        "id": "fingerprint.png",
        "callsign": "radio.png",
        "ship_type": "shiptype.png",
        "destination": "route.png",
        "speed": "gauge.png"
    }

    def __init__(self,
        path: Path,
        primary_font: StaticFont | VariableFont | None = None,
        secondary_font: StaticFont | VariableFont | None = None,
        default_icons: str = "Tabler"
    ) -> None:
        self._root_dir = path

        self._icons_path = path / "icons"
        self._fonts_path = path / "fonts"

        if not primary_font:
            primary_font = VariableFont(file = self._fonts_path / "Literata/Literata-VariableFont_opsz,wght.ttf",
                                        italic_file = self._fonts_path / "Literata/Literata-Italic-VariableFont_opsz,wght.ttf")

        if not secondary_font:
            secondary_font = StaticFont(dir = self._fonts_path / "IBM_Plex_Mono", family= "IBMPlexMono")
        
        self._fonts = {
            "primary": primary_font,
            "secondary": secondary_font
        }
        self._default_icons = default_icons

        self._icon_cache: dict[tuple[str,int], Image.Image] = {}
        self._font_cache: dict[tuple[str,str,int], ImageFont.FreeTypeFont] = {}

    def get_font(self, role: str, variation: str, size: int, italic: bool = False) -> ImageFont.FreeTypeFont:
        print(f"GET FONT {role} - {variation} - {size}")
        font = self._font_cache.get((role, variation, size, italic))

        if not font:
            font = self._fonts[role].load(variation, size, italic)
            self._font_cache[(role, variation, size, italic)] = font

        return font
    
    def get_icon(self, role: str, size: int, colour: str) -> Image.Image:
        icon = self._icon_cache.get((role, size, colour))

        if not icon:
            icon_path = self._root_dir / "icons" / self._default_icons / self.ICON_MAP.get(role)
            icon = self._load_icon(icon_path, size)

            if icon.mode != "RGBA":
                icon = icon.convert("RGBA")

            r, g, b = tuple(int(colour.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
            tmp = Image.new("RGBA", icon.size, (r, g, b, 255))
            tmp.putalpha(icon.split()[3])
            icon = tmp

            self._icon_cache[(role, size, colour)] = icon

        return icon

    def _load_font(self, path: Path, variation: str, size: int) -> ImageFont.FreeTypeFont:
        font = ImageFont.truetype(path, size)
        font.set_variation_by_name(variation)

        return font

    def _load_icon(self, path: Path, size: int) -> Image.Image:
        icon = Image.open(path)
        icon = self._resize_image(icon, size, size)

        return icon
    
    def _resize_image(self, image:Image.Image, max_width:int, max_height:int) -> Image.Image:
        original_width, original_height = image.size

        width_ratio: float = max_width / original_width
        height_ratio: float = max_height / original_height

        scale_factor: float = min(width_ratio, height_ratio)

        new_width: int = int(original_width * scale_factor)
        new_height: int = int(original_height * scale_factor)

        return image.resize((new_width, new_height), Image.LANCZOS)