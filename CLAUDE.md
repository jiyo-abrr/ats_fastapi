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
      router.py            # thin — endpoints just call the service, no logic here
  main.py                  # includes each domain's router
```

When adding a new domain (e.g. `jobs`, `applications`), mirror this structure under `app/domains/<name>/`. Route handlers stay plain functions (FastAPI's DI is built around that); business logic goes in a service class per domain, and that service depends on a repository class rather than querying the ORM directly. New domain repositories should subclass `app.core.repository.BaseRepository[Model]` and only add query methods the base CRUD doesn't cover — don't re-implement `get_by_id`/`add`/etc. per domain.

**Transactions**: repositories only stage changes (`add`/`delete`/query) — they never commit. Any service method that mutates data takes a `UnitOfWork` (via `Depends(get_unit_of_work)`, from `app.core.unit_of_work`) and calls `flush()`/`commit()`/`refresh()` on it, not on the repository. `get_user_repository` and `get_unit_of_work` both resolve from the same `Depends(get_db)` session per request, so a service that touches multiple repositories in one operation (e.g. a future "apply to job" flow spanning `ApplicationRepository` + `JobRepository`) can stage all of them and commit once via one shared `UnitOfWork` — keeping that operation atomic. Only put something in `app/core` if more than one domain will need it.

## Environment

- Package manager: `uv` (see `uv.lock`). Use `uv add <package>` to add dependencies, `uv run <script>` to run things — don't call `pip` directly.
- Python version is pinned via `.python-version` (3.14).
- Copy `.env.example` to `.env` before running anything — `app/core/config.py` (pydantic-settings) requires `DATABASE_URL`, `JWT_SECRET_KEY`, and `MINIO_*` vars to be set.
- Infra (Postgres + MinIO) runs via Docker: `docker compose up -d`. `docker-compose.yml` matches the defaults in `.env.example` (do not change one without the other).
- Migrations: `uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`. `alembic/env.py` is wired to `app.core.database.Base` — new domain models must be imported there (see the `from app.domains.auth import models` line) or autogenerate won't see them. Generated files under `alembic/versions/` are excluded from ruff (`extend-exclude` in `pyproject.toml`) — don't hand-edit them for style.
- Run the API: `PYTHONUTF8=1 uv run fastapi dev app/main.py`. The `PYTHONUTF8=1` is required on Windows — without it, `fastapi dev`'s startup banner crashes with a `UnicodeEncodeError` trying to print an emoji through the cp1252 console codec.
- Auth design: access + refresh JWTs (see `app/core/security.py`), passwords hashed with `bcrypt` directly (not `passlib`). No email verification yet.
- Refresh-token revocation: every JWT carries a `jti`. `POST /auth/logout` records the refresh token's `jti` + expiry in the `revoked_refresh_tokens` table (`app/domains/auth/models.py`); `POST /auth/refresh` rejects any token whose `jti` is in that table. Access tokens are NOT revocable (they just expire — 30 min default) — only refresh tokens are checked against the denylist. There's no cleanup job for expired rows in that table yet.

## Git scope (important)

This directory (`rd/ats_fastapi`) is nested inside a much larger personal git repository rooted at `D:/devjiyo` that also contains many unrelated, unversioned-together projects (games, freelance work, ML experiments, etc.). There is no repo-level `.gitignore` for this project.

- When staging or committing, target files under `rd/ats_fastapi/` explicitly — never run a blanket `git add -A` or `git add .` from the repo root.
- Before any commit, review `git status` output carefully since it will show changes across unrelated projects too.
