import logging

from fastapi import FastAPI

from app.api.router import api_router
from app.core.exception_handlers import register_exception_handlers

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ATS FastAPI")

register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
