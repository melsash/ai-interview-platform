from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# AsyncEngine — неблокирующий движок, использует asyncpg под капотом
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,       # SQL логи в dev режиме
    pool_size=10,              # постоянные соединения в пуле
    max_overflow=20,           # дополнительные при пике нагрузки
    pool_pre_ping=True,        # проверяет соединение перед использованием
)

# Фабрика сессий — async_sessionmaker для async/await
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,    # объекты не expire после commit (важно для async)
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — инжектирует сессию в роуты.
    Context manager гарантирует закрытие сессии даже при исключении.

    Usage in route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
