import tomllib
import tomli_w
from pathlib import Path
from typing import Any
import copy

class ConfigManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._cfg: dict[str, Any] = {}

    def load(self) -> None:
        """
        Load the config file specified in the constructor.
        If the file does not exist, the load will fail silently and an empty
         config will be used.
        If the config file exists but is malformed then a ValueError will
         be thrown
        """
        self._cfg = {}
        
        if self.path.exists():
            try:
                with open(self.path, "rb") as f:
                    self._cfg = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                raise ValueError(f"Invalid TOML in config file {self.path}: {e}") from e

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "wb") as f:
            tomli_w.dump(self._cfg, f)

    def get_all(self) -> dict[str, Any]:
        return copy.deepcopy(self._cfg)

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._cfg

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
            
        return copy.deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        keys = key.split(".")
        config = self._cfg

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            elif not isinstance(config[k], dict):
                raise TypeError(f"Cannot descend into non-dictionary '{k}' (found type {type(config[k]).__name__})")
            
            config = config[k]

        config[keys[-1]] = copy.deepcopy(value)

    def has(self, key: str) -> bool:
        """Check if a config key exists"""
        keys = key.split(".")
        value = self._cfg

        for k in keys:
            if not isinstance(value, dict) or k not in value:
                return False
            value = value[k]
        
        return True
