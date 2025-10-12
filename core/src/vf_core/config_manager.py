import tomllib
import tomli_w
from pathlib import Path
from typing import Any

class ConfigManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._cfg: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            with open(self.path, "rb") as f:
                self._cfg = tomllib.load(f)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "wb") as f:
            tomli_w.dump(self._cfg, f)

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
            
        return value

    def set(self, key: str, value: Any) -> None:
        keys = key.split(".")
        dict = self._cfg

        for k in keys[:-1]:
            if k not in dict:
                dict[k] = {}
            elif not isinstance(dict[k], dict):
                raise TypeError(f"Cannot descend into non-dictionary '{k}'")
            
            dict = dict[k]

        dict[keys[-1]] = value
