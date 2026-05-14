from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes.assessment import router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.rabbitmq import publisher

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Assessment Service")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")
    await publisher.connect()
    logger.info("RabbitMQ publisher ready")
    yield
    await publisher.disconnect()
    await engine.dispose()
    logger.info("Assessment Service stopped")


app = FastAPI(
    title="AI Interview Platform — Assessment Service",
    description="Interview sessions, questions, code submissions & realtime evaluation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)
app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "healthy", "service": "assessment", "version": "1.0.0"}
