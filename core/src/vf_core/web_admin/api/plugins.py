from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Any, cast
from pydantic import BaseModel

from vf_core.plugin_manager import PluginManager
from vf_core.config_manager import ConfigManager

router = APIRouter()

def get_plugin_manager(request: Request) -> PluginManager:
    """
    Dependency injection for PluginManager pulled from app.state.
    """
    pm = getattr(request.app.state, "plugin_manager", None)
    if pm is None:
        raise HTTPException(status_code=500, detail="PluginManager is not available")
    return cast(PluginManager, pm)

def get_config_manager(request: Request) -> ConfigManager:
    """
    Dependency injection for ConfigManager
    """
    cm = getattr(request.app.state, "config_manager", None)
    if cm is None:
        raise HTTPException(status_code=500, detail="ConfigManager is not available")
    return cast(ConfigManager, cm)

@router.get("/schemas")
async def get_plugin_schemas(pm: PluginManager = Depends(get_plugin_manager)):
    """Get configuration schemas for all plugins"""
    schemas = {
    }
    
    print("[SCHEMA] Iter schema entry points")
    for entry_point in pm.iter_entry_points("vesselframe.config.schemas"):
        try:
            name = entry_point.name
            schema_func = entry_point.load()
            schema = schema_func()

            schemas[name] = schema.to_dict()
        except Exception as e:
            print(f"Error loading schema for {entry_point.name}: {e}")
    
    return schemas

@router.get("/available")
async def get_available_plugins(pm: PluginManager = Depends(get_plugin_manager)):
    """
    Get list of all available plugins (discovered via entry points).
    """
    available = {
        "sources": [],
        "processors": [],
        "renderer": [],
        "screens": []
    }
    
    plugin_groups = {
        "sources": "vesselframe.plugins.messagesource",
        "processors": "vesselframe.plugins.messageprocessors",
        "renderer": "vesselframe.plugins.renderer",
        "screens": "vesselframe.plugins.screens"
    }
    
    for category, group in plugin_groups.items():
        available[category] = pm.names(group)

    return available

class PluginUpdate(BaseModel):
    category: str
    name: str

@router.put('/enable')
async def enable_plugin(update:PluginUpdate, pm: PluginManager = Depends(get_plugin_manager), cm: ConfigManager = Depends(get_config_manager)):
    plugin_list = cm.get(f"plugins.{update.category}")
    if plugin_list is None:
        plugin_list = []

    plugin_list.append(update.name)
    cm.set(f"plugins.{update.category}", plugin_list)

    plugin_config = cm.get(update.name)
    if plugin_config is None:
        for entry_point in pm.iter_entry_points("vesselframe.config.schemas"):
            try:
                if entry_point.name == update.name:
                    schema_func = entry_point.load()
                    schema = schema_func()

                    print(f"Plugins - got schema for {update.name} {schema}")
                    for field in schema.fields:
                        if field.default is None:
                            continue

                        full_key = f"{update.name}.{field.key}"
                        current = cm.get(full_key)
                        if current is None:
                            cm.set(full_key, field.default)
            except Exception as e:
                print(f"Error loading schema for {update.name}: {e}")

    cm.save()

    return True

@router.put('/disable')
async def disable_plugin(update:PluginUpdate, pm: PluginManager = Depends(get_plugin_manager), cm: ConfigManager = Depends(get_config_manager)):
    plugin_list = cm.get(f"plugins.{update.category}")
    if plugin_list is None:
        return True

    if update.name in plugin_list:
        plugin_list.remove(update.name)

    cm.set(f"plugins.{update.category}", plugin_list)
    cm.save()

    return True