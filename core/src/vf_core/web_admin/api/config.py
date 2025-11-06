from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Any, cast
import json
from fastapi.responses import JSONResponse, PlainTextResponse

from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager
from vf_core.web_admin.dependencies import get_config_manager, get_plugin_manager

router = APIRouter()



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