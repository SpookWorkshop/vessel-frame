import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from vf_core.web_admin.dependencies import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

class NetworkStatusResponse(BaseModel):
    """Response model for network status"""
    configured_mode: str
    actual_mode: str
    timestamp: str
    config_file: str
    ap_ssid: str | None = None
    ap_ip: str | None = None
    connected_ssid: str | None = None
    ip_address: str | None = None


class NetworkConfigResponse(BaseModel):
    """Response model for network configuration"""
    mode: str
    ap_ssid: str
    ap_password: str | None
    ap_channel: int
    ap_ip: str
    client_ssid: str | None
    client_password: str | None
    auto_fallback: bool
    fallback_timeout: int


class NetworkInfo(BaseModel):
    """Model for scanned network information"""
    ssid: str
    quality: str | None
    signal: str | None
    encrypted: bool


class APModeRequest(BaseModel):
    """Request model for AP mode configuration"""
    ssid: str | None = Field(None, min_length=1, max_length=32)
    password: str | None = Field(None, min_length=8, max_length=63)
    channel: int | None = Field(None, ge=1, le=11)


class ClientModeRequest(BaseModel):
    """Request model for client mode configuration"""
    ssid: str = Field(..., min_length=1, max_length=32)
    password: str | None = Field(None, max_length=63)
    auto_fallback: bool | None = True
    fallback_timeout: int | None = Field(60, ge=30, le=300)


@router.get("/status", response_model=NetworkStatusResponse, dependencies=[Depends(verify_token)])
async def get_network_status(request: Request):
    """Get current network status"""

    try:
        network_manager = request.app.state.network_manager
        status = network_manager.get_status()
        return status
    except Exception as e:
        logger.error(f"Error getting network status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config", response_model=NetworkConfigResponse, dependencies=[Depends(verify_token)])
async def get_network_config(request: Request):
    """Get current network configuration"""

    try:
        network_manager = request.app.state.network_manager
        config = network_manager.get_config_dict()
        return config
    except Exception as e:
        logger.error(f"Error getting network config: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/scan", response_model=list[NetworkInfo], dependencies=[Depends(verify_token)])
async def scan_networks(request: Request):
    """Scan for available networks"""
    try:
        network_manager = request.app.state.network_manager
        networks = await network_manager.scan_networks_async()
        return networks
    except Exception as e:
        logger.error(f"Error scanning networks: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/mode/ap", dependencies=[Depends(verify_token)])
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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/mode/offline", dependencies=[Depends(verify_token)])
async def set_offline_mode(request: Request):
    """Schedule offline mode (all wireless disabled) for next reboot."""
    try:
        network_manager = request.app.state.network_manager
        success, message = network_manager.schedule_mode_change('offline')

        if success:
            return {
                "success": True,
                "message": "Offline mode scheduled. Please reboot the device for changes to take effect.",
                "requires_reboot": True,
            }
        else:
            raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting offline mode: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/mode/client", dependencies=[Depends(verify_token)])
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
        raise HTTPException(status_code=500, detail=str(e)) from e
