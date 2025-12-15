from pathlib import Path
from PIL import Image, ImageFont

class AssetManager:
    ICON_MAP = {
        "vessel": "vessel.png",
        "id": "fingerprint.png",
        "callsign": "radio.png",
        "destination": "route.png",
        "speed": "gauge.png"
    }

    def __init__(self, path: Path, default_font: str = "Inter", default_icons: str = "Tabler") -> None:
        self._root_dir = path

        self._icons_path = path / "icons"
        self._fonts_path = path / "fonts"

        self._default_font = default_font
        self._default_icons = default_icons

        self._icon_cache: dict[tuple[str,int], Image.Image] = {}
        self._font_cache: dict[tuple[str,str,int], ImageFont.FreeTypeFont] = {}

    def get_font(self, role: str, variation: str, size: int) -> ImageFont.FreeTypeFont:
        font = self._font_cache.get((role, variation, size))

        if not font:
            font_path = self._root_dir / "fonts" / self._default_font / f"{self._default_font}-VariableFont_opsz,wght.ttf"
            font = self._load_font(font_path, variation, size)
            self._font_cache[(role, variation, size)] = font

        return font
    
    def get_icon(self, role: str, size: int) -> Image.Image:
        icon = self._icon_cache.get((role, size))

        if not icon:
            icon_path = self._root_dir / "icons" / self._default_icons / self.ICON_MAP.get(role)
            icon = self._load_icon(icon_path, size)

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