from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Any
import logging

from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager
from vf_core.web_admin.dependencies import get_config_manager, get_plugin_manager, verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

# Keys writable under the [SYSTEM] config section. Unlike plugin config, SYSTEM
# has no per-field schema, so we gate writes against an explicit allowlist.
ALLOWED_SYSTEM_KEYS = {"mapbox_api_key"}


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


@router.get("/", dependencies=[Depends(verify_token)])
async def get_config(cm: ConfigManager = Depends(get_config_manager)):
    """
    Return the system config as a dictionary.

    Args:
        cm (ConfigManager): Injected config manager dependency.

    Returns:
        dict[str, Any]: Deep copy of the full system config.
    """
    return cm.get("SYSTEM", {})


@router.put("/", response_model=ConfigUpdateResponse, dependencies=[Depends(verify_token)])
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System config key cannot be empty")

    if update.key not in ALLOWED_SYSTEM_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown system config key '{update.key}'. Allowed: {', '.join(sorted(ALLOWED_SYSTEM_KEYS))}",
        )

    try:
        cm.set(f"SYSTEM.{update.key}", update.value)
        cm.save()
        return {"success": True, "key": update.key, "value": update.value}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))