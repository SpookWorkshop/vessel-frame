from importlib.metadata import entry_points, EntryPoint
from collections.abc import Iterable, Callable
from typing import Any
from .message_bus import MessageBus
from .plugin_types import Plugin

class PluginManager:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    def iter_entry_points(self, group: str) -> Iterable[EntryPoint]:
        return entry_points().select(group=group)

    def names(self) -> list[str]:
        return [ep.name for ep in self.iter_entry_points()]

    def load_factory(self, group: str, name: str) -> Callable[[MessageBus], Plugin]:
        for ep in self.iter_entry_points(group):
            if ep.name == name:
                return ep.load()
            
        raise KeyError(f"Plugin '{name}' not found in group '{group}'")

    def create(self, group: str, name: str, **kwargs: Any) -> Plugin:
        factory = self.load_factory(group, name)
        plugin = factory(self.bus, **kwargs)

        if not isinstance(plugin, Plugin):
            raise TypeError(
                f"Factory for '{name}' did not return a Plugin instance, got {type(plugin).__name__}"
            )
            
        return plugin