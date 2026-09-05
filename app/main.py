import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_pagination import add_pagination

from app.api.router import api_router
from app.core.exception_handlers import register_exception_handlers
from app.core.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="ATS FastAPI", lifespan=lifespan)

register_exception_handlers(app)
app.include_router(api_router)
add_pagination(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
