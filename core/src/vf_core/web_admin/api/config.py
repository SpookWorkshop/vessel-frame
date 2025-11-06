from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any
import logging

from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager
from vf_core.plugin_types import GROUP_SCHEMAS
from vf_core.web_admin.dependencies import get_config_manager, get_plugin_manager

logger = logging.getLogger(__name__)
router = APIRouter()

class ConfigUpdate(BaseModel):
    path: str
    value: Any

class ConfigValueResponse(BaseModel):
    path: str
    value: Any

class ConfigUpdateResponse(BaseModel):
    success: bool
    path: str
    value: Any

@router.get("/")
async def get_full_config(cm: ConfigManager = Depends(get_config_manager)):
    return cm.get_all()

@router.get("/{path:path}", response_model=ConfigValueResponse)
async def get_config_value(path: str, cm: ConfigManager = Depends(get_config_manager)):
    """Get a config value"""
    if not cm.has(path):
        raise HTTPException(status_code=404, detail=f"Config path '{path}' not found")
    
    value = cm.get(path)
    return {"path": path, "value": value}

@router.put("/", response_model=ConfigUpdateResponse)
async def update_config(
    update: ConfigUpdate,
    cm: ConfigManager = Depends(get_config_manager),
    pm: PluginManager = Depends(get_plugin_manager)
):
    """
    Update a config value
    """

    # Validate path
    if not update.path or not update.path.strip():
        raise HTTPException(status_code=400, detail="Config path cannot be empty")
    
    if len(update.path) > 200:
        raise HTTPException(status_code=400, detail="Config path too long")
    
    if not _is_valid_config_path(update.path, pm):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid config path '{update.path}'. Path must match a field in the plugin's schema."
        )

    try:
        cm.set(update.path, update.value)
        cm.save()
        return {"success": True, "path": update.path, "value": update.value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
def _is_valid_config_path(path: str, pm: PluginManager) -> bool:
    """Check if a config path is valid against plugin schemas."""
    parts = path.split(".", 1)
    
    if len(parts) != 2:
        return False
    
    plugin_name, field_key = parts
    
    # Try to load the plugin's schema
    try:
        schema_func = pm.load_factory(GROUP_SCHEMAS, plugin_name)
        schema = schema_func()
        
        # Check if field_key exists in schema
        valid_keys = {field.key for field in schema.fields}
        return field_key in valid_keys
        
    except KeyError:
        # No schema found for this plugin
        logger.warning(f"No schema found for plugin '{plugin_name}'")
        return False
    except Exception:
        logger.exception(f"Error loading schema for plugin '{plugin_name}'")
        return False