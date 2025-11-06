from fastapi import HTTPException, Request

from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager


def get_config_manager(request: Request) -> ConfigManager:
    """Dependency injection for ConfigManager"""
    cm = getattr(request.app.state, "config_manager", None)
    if cm is None:
        raise HTTPException(status_code=500, detail="ConfigManager is not available")
    return cm


def get_plugin_manager(request: Request) -> PluginManager:
    """Dependency injection for PluginManager"""
    pm = getattr(request.app.state, "plugin_manager", None)
    if pm is None:
        raise HTTPException(status_code=500, detail="PluginManager is not available")
    return pm
