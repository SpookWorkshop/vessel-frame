from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class NetworkStatusResponse(BaseModel):
    """Response model for network status"""
    configured_mode: str
    actual_mode: str
    timestamp: str
    config_file: str
    ap_ssid: Optional[str] = None
    ap_ip: Optional[str] = None
    connected_ssid: Optional[str] = None
    ip_address: Optional[str] = None


class NetworkConfigResponse(BaseModel):
    """Response model for network configuration"""
    mode: str
    ap_ssid: str
    ap_password: str
    ap_channel: int
    ap_ip: str
    client_ssid: Optional[str]
    client_password: Optional[str]
    auto_fallback: bool
    fallback_timeout: int


class NetworkInfo(BaseModel):
    """Model for scanned network information"""
    ssid: str
    quality: Optional[str]
    signal: Optional[str]
    encrypted: bool


class APModeRequest(BaseModel):
    """Request model for AP mode configuration"""
    ssid: Optional[str] = Field(None, min_length=1, max_length=32)
    password: Optional[str] = Field(None, min_length=8, max_length=63)
    channel: Optional[int] = Field(None, ge=1, le=11)


class ClientModeRequest(BaseModel):
    """Request model for client mode configuration"""
    ssid: str = Field(..., min_length=1, max_length=32)
    password: str = Field(default="")
    auto_fallback: Optional[bool] = True
    fallback_timeout: Optional[int] = Field(60, ge=30, le=300)


@router.get("/status", response_model=NetworkStatusResponse)
async def get_network_status(request: Request):
    """Get current network status"""

    try:
        network_manager = request.app.state.network_manager
        status = network_manager.get_status()
        return status
    except Exception as e:
        logger.error(f"Error getting network status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=NetworkConfigResponse)
async def get_network_config(request: Request):
    """Get current network configuration"""

    try:
        network_manager = request.app.state.network_manager
        config = network_manager.get_config_dict()
        return config
    except Exception as e:
        logger.error(f"Error getting network config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan", response_model=List[NetworkInfo])
async def scan_networks(request: Request):
    """Scan for available networks"""
    try:
        network_manager = request.app.state.network_manager
        networks = await network_manager.scan_networks_async()
        return networks
    except Exception as e:
        logger.error(f"Error scanning networks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mode/ap")
async def set_ap_mode(request: Request, config: APModeRequest):
    """Configure and schedule AP mode
    
    This will save the configuration and schedule it for the next reboot.
    The user will be advised to reboot for changes to take effect.
    """
    try:
        network_manager = request.app.state.network_manager
        
        # Update AP configuration if provided
        if config.ssid or config.password or config.channel:
            success, message = network_manager.update_ap_config(
                ssid=config.ssid,
                password=config.password,
                channel=config.channel
            )
            if not success:
                raise HTTPException(status_code=400, detail=message)
        
        # Schedule mode change
        success, message = network_manager.schedule_mode_change('ap')
        
        if success:
            return {
                "success": True,
                "message": "AP mode scheduled. Please reboot the device for changes to take effect.",
                "requires_reboot": True
            }
        else:
            raise HTTPException(status_code=500, detail=message)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting AP mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mode/client")
async def set_client_mode(request: Request, config: ClientModeRequest):
    """Configure and schedule client mode
    
    This will save the configuration and schedule it for the next reboot.
    The user will be advised to reboot for changes to take effect.
    """
    try:
        network_manager = request.app.state.network_manager
        
        # Update client configuration
        success, message = network_manager.update_client_config(
            ssid=config.ssid,
            password=config.password,
            auto_fallback=config.auto_fallback,
            fallback_timeout=config.fallback_timeout
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        # Schedule mode change
        success, message = network_manager.schedule_mode_change('client')
        
        if success:
            return {
                "success": True,
                "message": "Client mode scheduled. Please reboot the device for changes to take effect.",
                "requires_reboot": True
            }
        else:
            raise HTTPException(status_code=500, detail=message)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting client mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))
