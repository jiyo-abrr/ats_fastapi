import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_STATUS_BY_CATEGORY = {
    NotFoundError: 404,
    ConflictError: 409,
    UnauthorizedError: 401,
    ForbiddenError: 403,
    ValidationError: 400,
}


def _make_domain_error_handler(status_code: int):
    async def handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": exc.message},
            headers=exc.headers,
        )

    return handler


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception while handling %s %s", request.method, request.url.path
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    for category, status_code in _STATUS_BY_CATEGORY.items():
        app.add_exception_handler(category, _make_domain_error_handler(status_code))
    app.add_exception_handler(Exception, unhandled_exception_handler)
