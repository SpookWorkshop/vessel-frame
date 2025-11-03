from typing import Protocol, runtime_checkable, Any
from enum import Enum
from dataclasses import dataclass

@runtime_checkable
class Plugin(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

@runtime_checkable
class RendererPlugin(Protocol):
    def flush(self) -> None: ...

@runtime_checkable
class ScreenPlugin(Protocol):
    async def activate(self) -> None: ...
    async def deactivate(self) -> None: ...

class ConfigFieldType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SELECT = "select"
    COLOR = "colour"
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

@runtime_checkable
class Configurable(Protocol):    
    @staticmethod
    def get_config_schema() -> ConfigSchema: ...