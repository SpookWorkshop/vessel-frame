from importlib.metadata import entry_points, EntryPoint
from collections.abc import Iterable, Callable
from typing import Any
from .message_bus import MessageBus
from .plugin_types import Plugin

GROUP = "vesselframe.plugins.messagesource"

class PluginManager:
    def __init__(self, bus: MessageBus, group: str = GROUP) -> None:
        self.group = group
        self.bus = bus

    def iter_entry_points(self) -> Iterable[EntryPoint]:
        return entry_points().select(group=self.group)

    def names(self) -> list[str]:
        return [ep.name for ep in self.iter_entry_points()]

    def load_factory(self, name: str) -> Callable[[MessageBus], Plugin]:
        for ep in self.iter_entry_points():
            if ep.name == name:
                return ep.load()
            
        raise KeyError(f"Plugin '{name}' not found in group '{self.group}'")

    def create(self, name: str, **kwargs: Any) -> Plugin:
        factory = self.load_factory(name)
        plugin = factory(self.bus, **kwargs)

        if not isinstance(plugin, Plugin):
            raise TypeError(
                f"Factory for '{name}' did not return a Plugin instance, got {type(plugin).__name__}"
            )
            
        return plugin