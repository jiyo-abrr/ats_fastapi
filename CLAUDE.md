# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`ats-fastapi` is an Applicant Tracking System API built with FastAPI. The app lives under `app/` (`app/main.py` is the FastAPI entrypoint — there is no root-level `main.py`). Currently implemented: JWT-based signup/login authentication, with resumes uploaded to MinIO and profiles stored in Postgres via SQLAlchemy.

## Architecture

Domain-based layout, not layered-by-type. Each business domain owns its full vertical slice:

```
app/
  core/
    repository.py          # BaseRepository[ModelType, IdType] — generic get_by_id/add/delete (query/staging only, no commit); IdType lets a domain key on non-UUID PKs (e.g. RevokedRefreshToken keys on a str jti)
    unit_of_work.py        # UnitOfWork — flush/commit/rollback/refresh for the whole request's Session
    ...                    # config, db engine/session, JWT + password primitives, generic MinIO client
  domains/
    auth/
      models.py            # SQLAlchemy ORM models
      schemas.py           # Pydantic request/response schemas
      repository.py        # UserRepository(BaseRepository[User]) — only adds query methods the generic base can't cover (get_by_email)
      service.py           # business logic as a class (AuthService), constructed with its repository + a UnitOfWork
      dependencies.py      # FastAPI Depends() providers for this domain (get_current_user, get_auth_service, get_user_repository)
      router.py            # thin, version-agnostic — endpoints just call the service; doesn't know it's mounted under /api/v1
  api/
    v1.py                  # version-specific aggregator: mounts each domain's router under /api/v1 (e.g. auth_router -> /api/v1/auth/*)
    router.py              # top-level aggregator: api_router combines every active version (currently just v1) into one router
  main.py                  # includes app.api.router.api_router (NOT v1_router or domain routers directly)
```

Every `__init__.py` in this project (`app/`, `app/core/`, `app/domains/`, `app/domains/auth/`, `app/api/`) is empty — a plain package marker, nothing else. Actual logic always lives in an explicitly-named module. Don't put logic in `__init__.py`, even for something as small as a router aggregator — it's easy to miss and invites circular-import surprises as the package grows.

When adding a new domain (e.g. `jobs`, `applications`), mirror this structure under `app/domains/<name>/`. Route handlers stay plain functions (FastAPI's DI is built around that); business logic goes in a service class per domain, and that service depends on a repository class rather than querying the ORM directly. New domain repositories should subclass `app.core.repository.BaseRepository[Model]` and only add query methods the base CRUD doesn't cover — don't re-implement `get_by_id`/`add`/etc. per domain. Register new domain routers in the relevant `app/api/vN.py`, not directly in `main.py` — domain routers must stay unaware of versioning.

**API versioning**: all routes are mounted under `/api/v1` via `app/api/v1.py` (e.g. `POST /api/v1/auth/signup`, not `/auth/signup`). `app/api/router.py` is the single aggregator `main.py` imports (`api_router`) — it combines every active version, so `main.py` never changes when a version is added or retired. `/health` is the one deliberate exception — it stays unversioned at the root, matching the convention that infra/monitoring probes shouldn't need to track API versions. If a `v2` is ever needed: add `app/api/v2.py` reusing unchanged domain routers and overriding only what changed, then add one line to `app/api/router.py` to mount it — `main.py` needs no changes.

**Transactions**: repositories only stage changes (`add`/`delete`/query) — they never commit. Any service method that mutates data takes a `UnitOfWork` (via `Depends(get_unit_of_work)`, from `app.core.unit_of_work`) and calls `flush()`/`commit()`/`refresh()` on it, not on the repository. `get_user_repository` and `get_unit_of_work` both resolve from the same `Depends(get_db)` session per request, so a service that touches multiple repositories in one operation (e.g. a future "apply to job" flow spanning `ApplicationRepository` + `JobRepository`) can stage all of them and commit once via one shared `UnitOfWork` — keeping that operation atomic. Only put something in `app/core` if more than one domain will need it.

**Exception handling**: known, expected errors (bad credentials, duplicate email, invalid token) are raised as `HTTPException` directly inside `service.py`/`dependencies.py`, right where they're detected — FastAPI's built-in exception middleware catches those regardless of how deep in the call stack they're raised. Anything unexpected (a bug, MinIO/Postgres connectivity failure, etc.) is caught by the global handler in `app/core/exception_handlers.py`, registered in `main.py` via `register_exception_handlers(app)` — it logs the full traceback server-side and returns a generic `{"detail": "Internal server error"}` (500) to the client, so internals never leak. Add a `RequestValidationError`/`HTTPException`-specific handler here too if the response shape ever needs to change; don't scatter `try/except` for unexpected errors elsewhere.

**Rate limiting**: `app/core/rate_limit.py` exposes `rate_limit(key_prefix, limit, window_seconds)`, a factory returning a FastAPI dependency backed by Redis (fixed-window counter via `INCR`/`EXPIRE`, keyed by `ratelimit:{key_prefix}:{client_ip}`). Apply it via `dependencies=[Depends(rate_limit("signup", limit=5, window_seconds=60))]` on the route decorator (see `auth/router.py`'s `/signup` and `/login`) — not as a handler parameter, since the return value isn't needed. Each endpoint gets its own independent counter (different `key_prefix`), so exhausting `/login`'s limit doesn't affect `/signup`. Exceeding the limit raises `HTTPException(429)`, handled the same way as any other known error. Requires the `redis` container (`docker compose up -d`) and `REDIS_URL` in `.env`.

## Environment

- Package manager: `uv` (see `uv.lock`). Use `uv add <package>` to add dependencies, `uv run <script>` to run things — don't call `pip` directly.
- Python version is pinned via `.python-version` (3.14).
- Copy `.env.example` to `.env` before running anything — `app/core/config.py` (pydantic-settings) requires `DATABASE_URL`, `JWT_SECRET_KEY`, and `MINIO_*` vars to be set.
- Infra (Postgres + MinIO) runs via Docker: `docker compose up -d`. `docker-compose.yml` matches the defaults in `.env.example` (do not change one without the other).
- Migrations: `uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`. `alembic/env.py` is wired to `app.core.database.Base` — new domain models must be imported there (see the `from app.domains.auth import models` line) or autogenerate won't see them. Generated files under `alembic/versions/` are excluded from ruff (`extend-exclude` in `pyproject.toml`) — don't hand-edit them for style.
- Run the API: `PYTHONUTF8=1 uv run fastapi dev app/main.py`. The `PYTHONUTF8=1` is required on Windows — without it, `fastapi dev`'s startup banner crashes with a `UnicodeEncodeError` trying to print an emoji through the cp1252 console codec.
- Auth design: access + refresh JWTs (see `app/core/security.py`), passwords hashed with `bcrypt` directly (not `passlib`). No email verification yet.
- Refresh-token revocation: every JWT carries a `jti`. `POST /api/v1/auth/logout` records the refresh token's `jti` + expiry in the `revoked_refresh_tokens` table (`app/domains/auth/models.py`); `POST /api/v1/auth/refresh` rejects any token whose `jti` is in that table. Access tokens are NOT revocable (they just expire — 30 min default) — only refresh tokens are checked against the denylist. There's no cleanup job for expired rows in that table yet.

## Git

`rd/ats_fastapi` is its own standalone git repository (`main` branch) — it is not part of the larger `D:/devjiyo` repo it happens to live under. The parent repo's `.gitignore` excludes `rd/ats_fastapi/` entirely, so nothing here is ever picked up by a `git status`/`git add` run from the parent. No remote is configured yet.
