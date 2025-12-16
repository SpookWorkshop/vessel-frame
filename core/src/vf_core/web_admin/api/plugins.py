from enum import Enum
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from vf_core.plugin_manager import PluginManager
from vf_core.config_manager import ConfigManager
import logging

from vf_core.plugin_types import (
    GROUP_PROCESSORS,
    GROUP_RENDERER,
    GROUP_SCHEMAS,
    GROUP_SCREENS,
    GROUP_SOURCES,
    GROUP_CONTROLLERS
)
from vf_core.web_admin.dependencies import get_config_manager, get_plugin_manager, verify_token


class PluginCategory(str, Enum):
    SOURCES = "sources"
    PROCESSORS = "processors"
    RENDERER = "renderer"
    SCREENS = "screens"
    CONTROLLERS = "controllers"


class PluginUpdate(BaseModel):
    category: PluginCategory
    name: str


logger = logging.getLogger(__name__)

PLUGIN_GROUPS = {
    "sources": GROUP_SOURCES,
    "processors": GROUP_PROCESSORS,
    "renderer": GROUP_RENDERER,
    "screens": GROUP_SCREENS,
    "controllers": GROUP_CONTROLLERS,
}
router = APIRouter()


@router.get("/schemas")
async def get_plugin_schemas(user: dict = Depends(verify_token), pm: PluginManager = Depends(get_plugin_manager)):
    """Get configuration schemas for all plugins"""
    schemas = {}

    for entry_point in pm.iter_entry_points(GROUP_SCHEMAS):
        try:
            name = entry_point.name
            schema_func = entry_point.load()
            schema = schema_func()

            schemas[name] = schema.to_dict()
        except Exception as e:
            logger.exception(f"Error loading schema for {entry_point.name}")

    return schemas


@router.get("/available")
async def get_available_plugins(user: dict = Depends(verify_token), pm: PluginManager = Depends(get_plugin_manager)):
    """Get list of all available plugins (discovered via entry points)."""
    available = {"sources": [], "processors": [], "renderer": [], "screens": [], "controllers": []}

    for category, group in PLUGIN_GROUPS.items():
        available[category] = pm.names(group)

    return available


@router.put("/enable")
async def enable_plugin(
    update: PluginUpdate,
    user: dict = Depends(verify_token), 
    pm: PluginManager = Depends(get_plugin_manager),
    cm: ConfigManager = Depends(get_config_manager),
):
    """
    Enable a plugin and initialise default config if available.

    Args:
        update (PluginUpdate): Plugin category and name to enable.
        pm (PluginManager): Injected plugin manager dependency.
        cm (ConfigManager): Injected config manager dependency.

    Returns:
        dict: Success response payload.

    Raises:
        HTTPException: If the plugin is not found in the specified category (404).
    """
    category = update.category.value

    # Make sure plugin exists
    available = pm.names(PLUGIN_GROUPS.get(category, ""))
    if update.name not in available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin '{update.name}' not found in category '{category}'",
        )

    # Get current plugin list
    plugin_list_key = f"plugins.{category}"
    plugin_list = cm.get(plugin_list_key, [])

    # Don't add duplicates
    if update.name in plugin_list:
        logger.info(f"Plugin {update.name} already enabled")
        return {"success": True, "message": "Plugin already enabled"}

    # Add to enabled list
    plugin_list.append(update.name)
    cm.set(plugin_list_key, plugin_list)

    _init_plugin_config(cm, pm, update.name)

    cm.save()
    return {"success": True}


def _init_plugin_config(cm: ConfigManager, pm: PluginManager, plugin_name: str) -> None:
    """
    Init default configuration values for a plugin (if it has a schema).

    If the plugin already has configuration, this is a no-op. Otherwise, loads
    the plugin's schema from `GROUP_SCHEMAS` and sets default values for any
    fields with a specified default.

    Args:
        cm (ConfigManager): Configuration manager to write defaults into.
        pm (PluginManager): Plugin manager used to load the schema factory.
        plugin_name (str): Entry-point name of the plugin.
    """
    # Check if plugin already has config
    if cm.get(plugin_name) is not None:
        return

    # Load schema and set defaults
    try:
        schema_func = pm.load_factory(GROUP_SCHEMAS, plugin_name)
        schema = schema_func()

        for field in schema.fields:
            if field.default is not None:
                full_key = f"{plugin_name}.{field.key}"
                if cm.get(full_key) is None:
                    cm.set(full_key, field.default)

        logger.info(f"Initialised defaults for {plugin_name}")
    except KeyError:
        # No schema found
        logger.debug(f"No schema found for {plugin_name}")
    except Exception:
        logger.exception(f"Error initialising defaults for {plugin_name}")


@router.put("/disable")
async def disable_plugin(
    update: PluginUpdate,
    pm: PluginManager = Depends(get_plugin_manager),
    cm: ConfigManager = Depends(get_config_manager),
):
    """
    Disable a plugin by removing it from the enabled list.

    Config values are preserved so they can be restored if the plugin is reenabled.

    Args:
        update (PluginUpdate): Plugin category and name to disable.
        pm (PluginManager): Injected plugin manager dependency.
        cm (ConfigManager): Injected config manager dependency.

    Returns:
        bool: True on success (or if the plugin was already disabled).
    """

    category = update.category.value

    plugin_list = cm.get(f"plugins.{category}")
    
    if plugin_list is None:
        return True

    if update.name in plugin_list:
        plugin_list.remove(update.name)

    cm.set(f"plugins.{category}", plugin_list)
    cm.save()

    return True
