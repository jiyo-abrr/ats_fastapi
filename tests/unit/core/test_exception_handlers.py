from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    def not_found():
        raise NotFoundError("missing")

    @app.get("/conflict")
    def conflict():
        raise ConflictError("dup")

    @app.get("/unauthorized")
    def unauthorized():
        raise UnauthorizedError("nope", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/forbidden")
    def forbidden():
        raise ForbiddenError("blocked")

    @app.get("/bad-request")
    def bad_request():
        raise ValidationError("invalid")

    @app.get("/boom")
    def boom():
        raise RuntimeError("unexpected")

    return app


client = TestClient(_build_app(), raise_server_exceptions=False)


def test_not_found_maps_to_404():
    resp = client.get("/not-found")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "missing"}


def test_conflict_maps_to_409():
    resp = client.get("/conflict")
    assert resp.status_code == 409
    assert resp.json() == {"detail": "dup"}


def test_unauthorized_maps_to_401_with_headers():
    resp = client.get("/unauthorized")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_forbidden_maps_to_403():
    resp = client.get("/forbidden")
    assert resp.status_code == 403
    assert resp.json() == {"detail": "blocked"}


def test_bad_request_maps_to_400():
    resp = client.get("/bad-request")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "invalid"}


def test_unhandled_exception_maps_to_generic_500():
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error"
    # request_id is None here because this throwaway app has no request-id
    # middleware installed (unlike the real app — see app/core/request_id.py).
    assert "request_id" in body
