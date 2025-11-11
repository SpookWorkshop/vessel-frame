from fastapi import Depends, HTTPException, Request, status

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from vf_core.config_manager import ConfigManager
from vf_core.plugin_manager import PluginManager

security = HTTPBearer(auto_error=False)


def get_config_manager(request: Request) -> ConfigManager:
    """Dependency injection for ConfigManager"""
    cm = getattr(request.app.state, "config_manager", None)
    if cm is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ConfigManager is not available",
        )
    return cm


def get_plugin_manager(request: Request) -> PluginManager:
    """Dependency injection for PluginManager"""
    pm = getattr(request.app.state, "plugin_manager", None)
    if pm is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PluginManager is not available",
        )
    return pm


def get_secret_key(request: Request) -> str:
    return request.app.state.secret_key


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    secret_key: str = Depends(get_secret_key),
) -> dict:
    """
    Verify JWT token and return payload.

    Raises 401 if token is missing, expired, or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(credentials.credentials, secret_key, algorithms=["HS256"])
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
