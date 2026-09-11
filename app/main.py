import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_pagination import add_pagination
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import settings
from app.core.database import async_engine, engine
from app.core.exception_handlers import register_exception_handlers
from app.core.queue import broker as rabbitmq_broker
from app.core.rate_limit import redis_client
from app.core.request_id import request_id_middleware
from app.core.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await rabbitmq_broker.start()
    start_scheduler()
    yield
    shutdown_scheduler()
    # Close the long-lived clients we opened at import (review F21).
    await redis_client.aclose()
    await rabbitmq_broker.stop()
    await async_engine.dispose()
    engine.dispose()


app = FastAPI(title="ATS FastAPI", lifespan=lifespan)

_cors_origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # "*" origins can't be combined with credentials per the CORS spec; this API
    # authenticates with bearer tokens, not cookies, so credentials aren't needed there.
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added after CORS so it's the outermost middleware — every request/response,
# including ones that fail inside CORS handling, gets an ID.
app.middleware("http")(request_id_middleware)

register_exception_handlers(app)
app.include_router(api_router)
add_pagination(app)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness — the process is up. Does not touch dependencies."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> JSONResponse:
    """Readiness — can we serve traffic? Pings Postgres, Redis, and RabbitMQ."""
    checks: dict[str, str] = {}
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 - report, don't crash the probe
        checks["database"] = "error"
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"
    try:
        checks["rabbitmq"] = "ok" if await rabbitmq_broker.ping(timeout=5) else "error"
    except Exception:  # noqa: BLE001
        checks["rabbitmq"] = "error"

    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "not_ready", "checks": checks},
        status_code=200 if ok else 503,
    )
