from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# bcrypt — industry standard для хеширования паролей
# deprecated="auto" автоматически обновляет старые хеши при логине
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---- Password utils ----

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---- JWT utils ----

def create_access_token(subject: str | Any, extra_claims: dict | None = None) -> str:
    """
    Create a short-lived JWT access token.

    subject — обычно user_id (str).
    extra_claims — дополнительные данные (role, email и т.д.).
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str | Any) -> str:
    """
    Create a long-lived JWT refresh token.
    Хранится в БД — можно инвалидировать при logout или компрометации.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    Raises JWTError if invalid or expired.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


def verify_token_type(payload: dict, expected_type: str) -> bool:
    return payload.get("type") == expected_type
