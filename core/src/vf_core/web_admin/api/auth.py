from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, HTTPException, Depends, status
import jwt
from pydantic import BaseModel

from ..auth import (
    get_or_create_secret_key,
    get_admin_credentials,
    set_admin_credentials,
    is_admin_configured,
)

ph = PasswordHasher(type=Type.ID)
router = APIRouter()


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/setup")
async def setup_admin(request: AuthRequest):
    """Initial setup, create admin credentials."""

    # Check if already set up
    if is_admin_configured():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin already configured")

    # Hash password
    password_hash = ph.hash(request.password.encode())

    # Store credentials
    set_admin_credentials(request.username, password_hash)

    return {"success": True, "message": "Admin account created"}


@router.post("/login")
async def login(
    request: AuthRequest, secret_key: str = Depends(get_or_create_secret_key)
):
    """Login and receive JWT token."""

    credentials = get_admin_credentials()
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Admin not configured. Run setup first."
        )

    # Verify username
    if request.username != credentials["username"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Verify password
    try:
        ph.verify(credentials["password_hash"].encode(), request.password.encode())
    except VerifyMismatchError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Generate JWT
    token = jwt.encode(
        {
            "username": request.username,
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        },
        secret_key,
        algorithm="HS256",
    )

    return {"token": token}


@router.get("/status")
async def auth_status():
    """Check if admin is configured."""
    credentials = get_admin_credentials()
    return {"configured": credentials is not None}
