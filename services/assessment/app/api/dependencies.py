import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Валидирует JWT через Auth Service.
    Assessment Service не хранит секрет — делегирует проверку.

    Это правильный подход для микросервисов: каждый сервис
    не дублирует логику проверки токенов.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.auth_service_url}/api/v1/auth/verify-token",
                headers={"Authorization": f"Bearer {credentials.credentials}"},
                timeout=5.0,
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth service unavailable",
            )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    data = response.json()
    return data["payload"]


def require_role(*roles: str):
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {list(roles)}",
            )
        return user
    return _check
