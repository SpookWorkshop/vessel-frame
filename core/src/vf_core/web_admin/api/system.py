from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any
import logging

from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager
from vf_core.web_admin.dependencies import get_config_manager, get_plugin_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class ConfigUpdate(BaseModel):
    key: str
    value: Any


class ConfigValueResponse(BaseModel):
    key: str
    value: Any


class ConfigUpdateResponse(BaseModel):
    success: bool
    key: str
    value: Any


@router.get("/")
async def get_config(cm: ConfigManager = Depends(get_config_manager)):
    """
    Return the system config as a dictionary.

    Args:
        cm (ConfigManager): Injected config manager dependency.

    Returns:
        dict[str, Any]: Deep copy of the full system config.
    """
    return cm.get("SYSTEM", {})


@router.put("/", response_model=ConfigUpdateResponse)
async def update_config(
    update: ConfigUpdate,
    cm: ConfigManager = Depends(get_config_manager),
    pm: PluginManager = Depends(get_plugin_manager),
):
    """
    Update a system config value and save the changes.

    Args:
        update (ConfigUpdate): The config key and value to update.
        cm (ConfigManager): Injected config manager dependency.
        pm (PluginManager): Injected plugin manager dependency.

    Returns:
        ConfigUpdateResponse: Confirmation of the updated value.

    Raises:
        HTTPException: If the path is invalid or an error occurs during update.
    """

    # Validate key
    if not update.key or not update.key.strip():
        raise HTTPException(status_code=400, detail="System config key cannot be empty")

    if len(update.key) > 40:
        raise HTTPException(status_code=400, detail="System config key too long")

    try:
        cm.set(f"SYSTEM.{update.key}", update.value)
        cm.save()
        return {"success": True, "key": update.key, "value": update.value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))