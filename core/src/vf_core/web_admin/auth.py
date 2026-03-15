import secrets
import logging
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_auth_data_path: Path | None = None

def init(data_dir: Path) -> None:
    """Initialise the auth module with the application data directory."""
    global _auth_data_path
    _auth_data_path = data_dir / ".secrets" / "admin_auth.json"


def _get_auth_data_path() -> Path:
    if _auth_data_path is None:
        raise RuntimeError("auth module not initialised, call auth.init(data_dir) first")
    return _auth_data_path


def get_or_create_secret_key() -> str:
    """Get or generate JWT secret key."""
    auth_data = _load_auth_data()
    
    if not auth_data.get("secret_key"):
        auth_data["secret_key"] = secrets.token_urlsafe(32)
        _save_auth_data(auth_data)
        logger.info("Generated new JWT secret key")
    
    return auth_data["secret_key"]

def get_admin_credentials() -> Optional[dict]:
    """
    Get admin username and password hash.
    
    Returns:
        dict with 'username' and 'password_hash', or None if not configured
    """
    auth_data = _load_auth_data()
    
    if "username" in auth_data and "password_hash" in auth_data:
        return {
            "username": auth_data["username"],
            "password_hash": auth_data["password_hash"]
        }
    
    return None

def set_admin_credentials(username: str, password_hash: str) -> None:
    """Set admin username and password hash."""
    auth_data = _load_auth_data()
    auth_data["username"] = username
    auth_data["password_hash"] = password_hash
    _save_auth_data(auth_data)
    logger.info(f"Admin credentials set for user: {username}")

def is_admin_configured() -> bool:
    """Check if admin credentials are configured."""
    return get_admin_credentials() is not None

def _load_auth_data() -> dict:
    """Load auth data from file."""
    path = _get_auth_data_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            logger.exception("Failed to read auth data")
            return {}

    return {}

def _save_auth_data(data: dict) -> None:
    """Save auth data to file."""
    path = _get_auth_data_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))

        try:
            path.chmod(0o600)
        except Exception:
            pass  # Windows doesn't support chmod
    except Exception:
        logger.exception("Failed to save auth data")
        raise