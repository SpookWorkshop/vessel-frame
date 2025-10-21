from importlib.metadata import entry_points, EntryPoint
from collections.abc import Iterable, Callable
from typing import Any
import logging

class PluginManager:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._entry_points_cache: dict[str, list[EntryPoint]] = {}

    def iter_entry_points(self, group: str) -> Iterable[EntryPoint]:
        if group not in self._entry_points_cache:
            self._entry_points_cache[group] = list(entry_points().select(group=group))

        return iter(self._entry_points_cache[group])

    def names(self, group: str) -> list[str]:
        return [ep.name for ep in self.iter_entry_points(group)]

    def load_factory(self, group: str, name: str) -> Callable[..., Any]:
        for ep in self.iter_entry_points(group):
            if ep.name == name:
                self._logger.debug(f"Loading plugin '{name}' from '{group}'")
                return ep.load()
        
        available = self.names(group)
        raise KeyError(
            f"Plugin '{name}' not found in group '{group}'. "
            f"Available: {', '.join(available) if available else 'none'}"
        )

    def create(self, group: str, name: str, **kwargs: Any) -> Any:
        factory = self.load_factory(group, name)
        plugin = factory(**kwargs)

        self._logger.info(f"Created plugin '{name}': {type(plugin).__name__}")

        return plugin