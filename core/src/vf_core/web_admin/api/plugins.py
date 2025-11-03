from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Any, cast

from vf_core.plugin_manager import PluginManager
from vf_core.plugin_types import Configurable

router = APIRouter()

def get_plugin_manager(request: Request) -> PluginManager:
    """
    Dependency injection for PluginManager pulled from app.state.
    """
    pm = getattr(request.app.state, "plugin_manager", None)
    if pm is None:
        raise HTTPException(status_code=500, detail="PluginManager is not available")
    return cast(PluginManager, pm)

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