from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegisterRequest,
    service: AuthService = Depends(get_auth_service),
):
    """Register a new user."""
    user = await service.register(data)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    """Login and receive access + refresh tokens."""
    return await service.login(data.email, data.password, request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
):
    """Rotate refresh token and get new token pair."""
    return await service.refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
):
    """Revoke a refresh token."""
    await service.logout(data.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """Revoke all refresh tokens for the current user (logout from all devices)."""
    await service.logout_all(current_user.id)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.post("/verify-token")
async def verify_token(
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    """
    Internal endpoint — used by other services to validate access tokens.
    Returns decoded payload if token is valid.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth_header.split(" ")[1]
    payload = await service.verify_access_token(token)
    return {"valid": True, "payload": payload}
