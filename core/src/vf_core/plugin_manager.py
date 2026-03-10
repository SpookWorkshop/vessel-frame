from importlib.metadata import entry_points, EntryPoint
from collections.abc import Iterable, Callable
from typing import Any
import logging

from .plugin_types import GROUP_SCHEMAS, ConfigFieldType


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
        instantiates it with the provided keyword arguments. Config values
        are coerced to the types declared in the plugin's schema before
        being passed to the factory.

        Args:
            group (str): The entry point group containing the plugin.
            name (str): The name of the plugin to instantiate.
            **kwargs (Any): Keyword arguments passed to the plugin factory.

        Returns:
            Any: The instantiated plugin object.
        """
        factory = self.load_factory(group, name)
        kwargs = self._coerce_kwargs(name, kwargs)
        plugin = factory(**kwargs)

        self._logger.info(f"Created plugin '{name}': {type(plugin).__name__}")

        return plugin

    def _coerce_kwargs(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Coerce plugin kwargs to the types declared in the plugin's schema.

        Falls back to returning kwargs unchanged if no schema is found or
        coercion fails for a given field.

        Args:
            name (str): Plugin name used to look up the schema.
            kwargs (dict[str, Any]): Raw kwargs to coerce.

        Returns:
            dict[str, Any]: Kwargs with values coerced to declared types.
        """
        try:
            schema_func = self.load_factory(GROUP_SCHEMAS, name)
            schema = schema_func()
        except KeyError:
            return kwargs
        except Exception:
            self._logger.warning(f"Failed to load schema for '{name}', skipping type coercion")
            return kwargs

        coerced = dict(kwargs)
        for field in schema.fields:
            if field.key not in coerced:
                continue
            value = coerced[field.key]
            try:
                ft = field.field_type
                if ft == ConfigFieldType.INTEGER:
                    coerced[field.key] = int(value)
                elif ft == ConfigFieldType.FLOAT:
                    coerced[field.key] = float(value)
                elif ft == ConfigFieldType.BOOLEAN:
                    if not isinstance(value, bool):
                        coerced[field.key] = str(value).lower() in ("true", "1", "yes")
                elif ft in (ConfigFieldType.STRING, ConfigFieldType.COLOUR,
                            ConfigFieldType.FILE, ConfigFieldType.SELECT):
                    coerced[field.key] = str(value)
            except Exception:
                self._logger.warning(
                    f"Failed to coerce '{field.key}' to {field.field_type} for plugin '{name}'"
                )

        return coerced
