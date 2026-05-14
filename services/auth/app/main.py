from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes.auth import router as auth_router
from app.core.config import get_settings
from app.core.database import Base, engine

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager — выполняется при старте и остановке приложения.
    Заменяет устаревшие on_startup/on_shutdown события.
    """
    # Startup
    logger.info("Starting Auth Service", environment=settings.environment)
    async with engine.begin() as conn:
        # В production использовать только Alembic migrations!
        # Здесь create_all для удобства разработки
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    yield  # приложение работает

    # Shutdown
    await engine.dispose()
    logger.info("Auth Service stopped")


app = FastAPI(
    title="AI Interview Platform — Auth Service",
    description="Authentication & authorization microservice",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — в production указывай конкретные origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint /metrics
Instrumentator().instrument(app).expose(app)

# Routers
app.include_router(auth_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint — используется Docker healthcheck и мониторингом."""
    return {"status": "healthy", "service": "auth", "version": "1.0.0"}
