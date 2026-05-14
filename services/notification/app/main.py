from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="AI Interview — Notification Service", version="1.0.0")

Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "notification"}
