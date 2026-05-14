import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    verify_token_type,
)
from app.models.user import User
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenResponse, UserRegisterRequest

settings = get_settings()


class AuthService:
    """
    Business logic layer.
    Знает про репозитории, но не про HTTP (никаких Request/Response здесь).
    Исключение — HTTPException для интеграции с FastAPI error handling.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.user_repo = UserRepository(db)
        self.token_repo = RefreshTokenRepository(db)

    async def register(self, data: UserRegisterRequest) -> User:
        # Проверяем уникальность email
        if await self.user_repo.exists_by_email(data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        user = await self.user_repo.create(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=data.role,
        )
        return user

    async def login(
        self,
        email: str,
        password: str,
        request: Request | None = None,
    ) -> TokenResponse:
        # Одно сообщение об ошибке для email и пароля — защита от user enumeration
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role, "email": user.email},
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )

        await self.token_repo.create(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
            user_agent=request.headers.get("user-agent") if request else None,
            ip_address=request.client.host if request and request.client else None,
        )
        await self.user_repo.update_last_login(user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        # 1. Декодируем токен
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        if not verify_token_type(payload, "refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        # 2. Проверяем в БД (не отозван ли)
        stored_token = await self.token_repo.get_by_token(refresh_token)
        if not stored_token or stored_token.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked",
            )

        if stored_token.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired",
            )

        # 3. Rotation — отзываем старый, выдаём новую пару
        await self.token_repo.revoke(refresh_token)

        user = await self.user_repo.get_by_id(stored_token.user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or deactivated",
            )

        new_access = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role, "email": user.email},
        )
        new_refresh = create_refresh_token(subject=str(user.id))

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )
        await self.token_repo.create(
            user_id=user.id,
            token=new_refresh,
            expires_at=expires_at,
        )

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def logout(self, refresh_token: str) -> None:
        await self.token_repo.revoke(refresh_token)

    async def logout_all(self, user_id: uuid.UUID) -> None:
        await self.token_repo.revoke_all_for_user(user_id)

    async def verify_access_token(self, token: str) -> dict:
        """
        Используется другими сервисами для валидации токена.
        Возвращает payload если токен валиден.
        """
        try:
            payload = decode_token(token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
            )

        if not verify_token_type(payload, "access"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        return payload
