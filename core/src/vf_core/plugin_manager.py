from importlib.metadata import entry_points, EntryPoint
from collections.abc import Iterable, Callable
from typing import Any
import logging


class PluginManager:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._entry_points_cache: dict[str, list[EntryPoint]] = {}

    def iter_entry_points(self, group: str) -> Iterable[EntryPoint]:
        """
        Iterate over registered plugin entry points for a given group.

        Caches discovered entry points to avoid repeated lookups. Subsequent calls
        for the same group use the cached results.

        Args:
            group (str): The entry point group name to search for.

        Returns:
            Iterable[EntryPoint]: An iterator over the matching entry points.
        """
        if group not in self._entry_points_cache:
            self._entry_points_cache[group] = list(entry_points().select(group=group))

        return iter(self._entry_points_cache[group])

    def empty_cache(self, group: str | None = None) -> None:
        """
        Clear cached plugin entry points.

        If a group is provided, only that group's cache is cleared. If no group is
        specified, the entire entry point cache is emptied.

        Args:
            group (str | None): The name of the entry point group to clear,
                or None to clear all groups.
        """
        if group is None:
            self._entry_points_cache.clear()
            self._logger.debug("Cleared entire entry points cache")
        else:
            self._entry_points_cache.pop(group, None)
            self._logger.debug(f"Cleared entry points cache for group '{group}'")

    def names(self, group: str) -> list[str]:
        """
        Return the names of all plugin entry points in a given group.

        Args:
            group (str): The entry point group to list names for.

        Returns:
            list[str]: A list of entry point names within the specified group.
        """
        return [ep.name for ep in self.iter_entry_points(group)]

    def load_factory(self, group: str, name: str) -> Callable[..., Any]:
        """
        Load a plugin factory function by name from a given entry point group.

        Searches all entry points within the specified group for a matching name.
        If found, the entry point is loaded and returned as a callable factory.
        Raises a KeyError if the plugin name is not found.

        Args:
            group (str): The entry point group containing the plugin.
            name (str): The name of the plugin to load.

        Returns:
            Callable[..., Any]: The loaded plugin factory callable.

        Raises:
            KeyError: If no plugin with the given name exists in the group.
        """
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
        """
        Instantiate a plugin using its registered factory.

        Loads the plugin factory from the specified entry point group and
        instantiates it with the provided keyword arguments.

        Args:
            group (str): The entry point group containing the plugin.
            name (str): The name of the plugin to instantiate.
            **kwargs (Any): Keyword arguments passed to the plugin factory.

        Returns:
            Any: The instantiated plugin object.
        """
        factory = self.load_factory(group, name)
        plugin = factory(**kwargs)

        self._logger.info(f"Created plugin '{name}': {type(plugin).__name__}")

        return plugin
