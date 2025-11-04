from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Any, cast
import json
from fastapi.responses import JSONResponse, PlainTextResponse

from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager

router = APIRouter()

def get_config_manager(request: Request) -> ConfigManager:
    """
    Dependency injection for ConfigManager
    """
    cm = getattr(request.app.state, "config_manager", None)
    if cm is None:
        raise HTTPException(status_code=500, detail="ConfigManager is not available")
    return cast(ConfigManager, cm)

def get_plugin_manager(request: Request) -> PluginManager:
    """
    Dependency injection for PluginManager
    """
    pm = getattr(request.app.state, "plugin_manager", None)
    if pm is None:
        raise HTTPException(status_code=500, detail="PluginManager is not available")
    return cast(PluginManager, pm)

class ConfigUpdate(BaseModel):
    path: str
    value: Any

@router.get("/")
async def get_full_config(cm: ConfigManager = Depends(get_config_manager)):
    data: Any = cm.get_all()
    return data


@router.get("/{path:path}")
async def get_config_value(path: str, cm: ConfigManager = Depends(get_config_manager)):
    """
    Get a config value
    """
    try:
        value = cm.get(path)
        return {"path": path, "value": value}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Config path '{path}' not found")

@router.put("/")
async def update_config(
    update: ConfigUpdate,
    cm: ConfigManager = Depends(get_config_manager)
):
    """
    Update a config value
    """
    try:
        cm.set(update.path, update.value)
        cm.save()
        return {"success": True, "path": update.path, "value": update.value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))