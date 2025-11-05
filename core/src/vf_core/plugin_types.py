from typing import Protocol, runtime_checkable, Any, TYPE_CHECKING
from enum import Enum
from dataclasses import dataclass

if TYPE_CHECKING:
    from PIL import Image, ImageFont

# Plugin discovery via setuptools entry points
# Plugins register themselves in pyproject.toml under these groups
GROUP_SOURCES = "vesselframe.plugins.messagesource"
GROUP_PROCESSORS = "vesselframe.plugins.messageprocessors"
GROUP_RENDERER = "vesselframe.plugins.renderer"
GROUP_SCREENS = "vesselframe.plugins.screens"

@runtime_checkable
class Plugin(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

@runtime_checkable
class RendererPlugin(Protocol):
    """
    Protocol for plugins that render visual output.
    
    Renderers provide a canvas, fonts, and color palette for screens to use,
    and handle the final output (saving to file, displaying on screen, etc).
    """
    
    MIN_RENDER_INTERVAL: int
    
    @property
    def canvas(self) -> 'Image.Image':
        """PIL Image canvas for screens to draw on."""
        ...
    
    @property
    def fonts(self) -> dict[str, 'ImageFont.FreeTypeFont']:
        """Available fonts keyed by size name (xsmall, small, medium, large)."""
        ...
    
    @property
    def palette(self) -> dict[str, str]:
        """Color palette with keys: background, foreground, line, text, accent."""
        ...
    
    def clear(self) -> None:
        """Clear the canvas to background color."""
        ...
    
    def flush(self) -> None:
        """Output the current canvas (save to file, update display, etc)."""
        ...

@runtime_checkable
class ScreenPlugin(Protocol):
    async def activate(self) -> None:
        """Set this screen plugin as the currently active screen"""
        ...

    async def deactivate(self) -> None:
        """Set the screen to deactivated and no longer expect it to update"""
        ...

class ConfigFieldType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SELECT = "select"
    COLOUR = "colour"
    FILE = "file"
    JSON = "json"

@dataclass
class ConfigField:
    key: str
    label: str
    field_type: ConfigFieldType
    default: Any
    required: bool = True
    description: str = ""
    options: list[Any] | None = None  # For SELECT
    validation: dict[str, Any] | None = None
    
    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.field_type.value,
            "default": self.default,
            "required": self.required,
            "description": self.description,
            "options": self.options,
            "validation": self.validation
        }

@dataclass
class ConfigSchema:
    plugin_name: str
    plugin_type: str
    fields: list[ConfigField]
    
    def to_dict(self) -> dict:
        return {
            "plugin_name": self.plugin_name,
            "plugin_type": self.plugin_type,
            "fields": [f.to_dict() for f in self.fields]
        }