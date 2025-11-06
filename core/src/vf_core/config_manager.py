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
        Load config data from the file path provided at initialization.

        If the file does not exist, loading fails silently and an empty config
        is used instead. If the file exists but contains malformed TOML, a
        `ValueError` is raised.

        Raises:
            ValueError: If the config file exists but contains invalid TOML.
        """

        self._cfg = {}

        if self.path.exists():
            try:
                with open(self.path, "rb") as f:
                    self._cfg = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                raise ValueError(f"Invalid TOML in config file {self.path}: {e}") from e

    def save(self) -> None:
        """
        Write the current config data to the file path specified at initialisation.

        Creates parent directories if they do not already exist. The config is
        written in TOML format and overwrites any existing file.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "wb") as f:
            tomli_w.dump(self._cfg, f)

    def get_all(self) -> dict[str, Any]:
        """
        Return a deep copy of the entire config dictionary.

        Returns:
            dict[str, Any]: A copy of all config data currently loaded.
        """
        return copy.deepcopy(self._cfg)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a config value by dotted key path.

        Nested keys can be accessed using dot notation (e.g., "database.host").
        If any key in the path is missing, the provided default value is returned.

        Args:
            key (str): The dotted key path of the config value.
            default (Any, optional): The value to return if the key does not exist.
                Defaults to None.

        Returns:
            Any: A deep copy of the config value, or the default if not found.
        """
        
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
        """
        Set a config value by dotted key path.

        Creates intermediate dictionaries as needed when setting nested keys.
        If an intermediate key exists but is not a dictionary, a `TypeError` is raised.

        Args:
            key (str): The dotted key path where the value should be set.
            value (Any): The value to assign. A deep copy is stored to prevent
                external mutation.

        Raises:
            TypeError: If a non-dictionary value is encountered in the key path.
        """
        keys = key.split(".")
        config = self._cfg

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            elif not isinstance(config[k], dict):
                raise TypeError(
                    f"Cannot descend into non-dictionary '{k}' (found type {type(config[k]).__name__})"
                )

            config = config[k]

        config[keys[-1]] = copy.deepcopy(value)

    def has(self, key: str) -> bool:
        """
        Check whether a config key exists.

        Supports nested keys using dot notation (e.g., "server.port").

        Args:
            key (str): The dotted key path to check.

        Returns:
            bool: True if the key exists, otherwise False.
        """
        keys = key.split(".")
        value = self._cfg

        for k in keys:
            if not isinstance(value, dict) or k not in value:
                return False
            value = value[k]

        return True
