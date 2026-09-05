# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`ats-fastapi` is an Applicant Tracking System API built with FastAPI. The app lives under `app/` (`app/main.py` is the FastAPI entrypoint — there is no root-level `main.py`). Currently implemented: JWT-based signup/login authentication, with resumes uploaded to MinIO and profiles stored in Postgres via SQLAlchemy.

## Architecture

Domain-based layout, not layered-by-type. Each business domain owns its full vertical slice:

```
app/
  core/
    exceptions.py          # DomainError + 5 HTTP-semantic subclasses (NotFoundError/ConflictError/UnauthorizedError/ForbiddenError/ValidationError) — the ONLY place that knows about HTTP status codes for business errors
    exception_handlers.py  # maps each category above to its status code, once, centrally; plus the catch-all Exception -> 500
    repository.py          # BaseRepository[ModelType, EntityType, IdType] — generic get_by_id/add/delete/list_all (query/staging only, no commit), mapping ORM rows <-> domain entities via each subclass's _to_entity/_to_model; IdType lets a domain key on non-UUID PKs (e.g. RevokedRefreshToken keys on a str jti)
    unit_of_work.py        # UnitOfWork — flush/commit/rollback for the whole request's Session
    ...                    # config, db engine/session, JWT + password primitives, generic MinIO client
  domains/
    auth/
      models.py            # SQLAlchemy ORM models — persistence only, touched ONLY by this domain's repository
      entities.py           # plain @dataclass domain entities (User, RevokedRefreshToken) — no SQLAlchemy, no FastAPI. What services actually operate on.
      exceptions.py         # EmailAlreadyRegisteredError, InvalidCredentialsError, InvalidRefreshTokenError, InvalidAccessTokenError, UnsupportedResumeTypeError, ResumeTooLargeError
      schemas.py            # Pydantic request/response schemas
      repository.py         # UserRepository(BaseRepository[UserModel, entities.User, uuid.UUID]) — only adds query methods the generic base can't cover (get_by_email)
      service.py            # business logic as a class (AuthService), constructed with its repository + a UnitOfWork; never imports fastapi or sqlalchemy
      dependencies.py       # FastAPI Depends() providers for this domain (get_current_user, get_auth_service, get_user_repository)
      router.py             # thin, version-agnostic — endpoints just call the service; doesn't know it's mounted under /api/v1
    rbac/
      models.py            # Role, Permission, RolePermission (ORM)
      entities.py           # Role, Permission (plain dataclasses)
      exceptions.py         # PermissionDeniedError, RoleNotFoundError, PermissionNotFoundError
      repository.py        # RoleRepository, PermissionRepository, RolePermissionRepository
      service.py            # RBACService — grant/revoke/list, raises the exceptions above
      dependencies.py      # require_permission(key) — the enforcement mechanism every domain gates on
      router.py             # admin-only endpoints to inspect/reconfigure role_permissions live
  api/
    v1.py                  # version-specific aggregator: mounts each domain's router under /api/v1 (e.g. auth_router -> /api/v1/auth/*)
    router.py              # top-level aggregator: api_router combines every active version (currently just v1) into one router
  scripts/
    create_admin.py         # one-off CLI to bootstrap the first admin account (uv run python -m app.scripts.create_admin)
  main.py                  # includes app.api.router.api_router (NOT v1_router or domain routers directly)
```

Every `__init__.py` in this project is empty — a plain package marker, nothing else. Actual logic always lives in an explicitly-named module. Don't put logic in `__init__.py`, even for something as small as a router aggregator — it's easy to miss and invites circular-import surprises as the package grows.

When adding a new domain (e.g. `jobs`, `applications`), mirror this structure under `app/domains/<name>/`: `models.py` (ORM) + `entities.py` (plain dataclass) + `exceptions.py` (domain errors) + `repository.py` + `service.py` + `dependencies.py` + `router.py`. Route handlers stay plain functions (FastAPI's DI is built around that); business logic goes in a service class per domain, and that service depends on a repository class rather than querying the ORM directly — and only ever sees that domain's `entities`, never its `models`. New domain repositories should subclass `app.core.repository.BaseRepository[Model, Entity, IdType]`, implement `_to_entity`/`_to_model`, and only add query methods the base CRUD doesn't cover — don't re-implement `get_by_id`/`add`/etc. per domain (composite-key join tables are the one exception — see `rbac.RolePermissionRepository` below). Register new domain routers in the relevant `app/api/vN.py`, not directly in `main.py` — domain routers must stay unaware of versioning. Gate any endpoint that isn't universally accessible with `Depends(require_permission("..."))` from `app.domains.rbac.dependencies` — see below.

**API versioning**: all routes are mounted under `/api/v1` via `app/api/v1.py` (e.g. `POST /api/v1/auth/signup`, not `/auth/signup`). `app/api/router.py` is the single aggregator `main.py` imports (`api_router`) — it combines every active version, so `main.py` never changes when a version is added or retired. `/health` is the one deliberate exception — it stays unversioned at the root, matching the convention that infra/monitoring probes shouldn't need to track API versions. If a `v2` is ever needed: add `app/api/v2.py` reusing unchanged domain routers and overriding only what changed, then add one line to `app/api/router.py` to mount it — `main.py` needs no changes.

**Transactions**: repositories only stage changes (`add`/`delete`/query) — they never commit. Any service method that mutates data takes a `UnitOfWork` (via `Depends(get_unit_of_work)`, from `app.core.unit_of_work`) and calls `flush()`/`commit()` on it, not on the repository. `get_user_repository` and `get_unit_of_work` both resolve from the same `Depends(get_db)` session per request, so a service that touches multiple repositories in one operation (e.g. a future "apply to job" flow spanning `ApplicationRepository` + `JobRepository`) can stage all of them and commit once via one shared `UnitOfWork` — keeping that operation atomic. Only put something in `app/core` if more than one domain will need it.

**Entities vs. models — services never see FastAPI or SQLAlchemy types.** Every domain has both a `models.py` (SQLAlchemy, persistence-only) and an `entities.py` (plain `@dataclass`, no ORM, no framework). Repositories are the *only* place that converts between them — `BaseRepository` subclasses implement `_to_entity(orm_obj)`/`_to_model(entity)`; `get_by_id`/`list_all` return entities, `add(entity)` maps to ORM internally and stages it. Services (`AuthService`, `RBACService`) only ever construct/read/pass around entities — they don't import anything from `models.py`, and router endpoints never pass a `UploadFile`/`Request`/etc. into a service (the router extracts plain values first — see `signup()`: the router calls `await resume.read()` and passes `resume_filename`/`resume_content_type`/`resume_bytes`, not the `UploadFile` itself). One consequence: identity generation moved from the ORM to the service — `signup()`/`create_hr_account()` generate `uuid.uuid4()` themselves *before* constructing the entity (needed immediately to build the MinIO resume key), rather than relying on `uow.flush()` to learn a DB-generated id. After `add()` + `commit()`, the service re-fetches via `get_by_id(the_id_it_already_has)` to pick up server-generated fields (`created_at`/`updated_at`) for the response — this is why `UnitOfWork.refresh()` was removed; there's no live, session-attached object left in the service to refresh.

**Exception handling — services raise plain domain exceptions, never `HTTPException`.** `app/core/exceptions.py` defines `DomainError` and five subclasses matching HTTP semantics (`NotFoundError`→404, `ConflictError`→409, `UnauthorizedError`→401, `ForbiddenError`→403, `ValidationError`→400; `DomainError` carries an optional `headers` dict for cases like the `WWW-Authenticate: Bearer` header on an invalid access token). Each domain subclasses these with concrete, named exceptions (`auth.exceptions.EmailAlreadyRegisteredError(ConflictError)`, `rbac.exceptions.PermissionDeniedError(ForbiddenError)`, etc.) and raises them directly — `AuthService`/`RBACService`/`get_current_user`/`require_permission` never construct an `HTTPException` or know their own status code. `app/core/exception_handlers.py`'s `register_exception_handlers(app)` registers one handler per category (mapping to its status) plus the pre-existing catch-all `Exception` → 500 (unhandled bugs/connectivity failures still get logged server-side with a generic body to the client — unchanged). Adding a new domain error: subclass the right category in that domain's `exceptions.py`, raise it — no new handler needed unless the category itself doesn't exist yet.

**Rate limiting**: `app/core/rate_limit.py` exposes `rate_limit(key_prefix, limit, window_seconds)`, a factory returning a FastAPI dependency backed by Redis (fixed-window counter via `INCR`/`EXPIRE`, keyed by `ratelimit:{key_prefix}:{client_ip}`). Apply it via `dependencies=[Depends(rate_limit("signup", limit=5, window_seconds=60))]` on the route decorator (see `auth/router.py`'s `/signup` and `/login`) — not as a handler parameter, since the return value isn't needed. Each endpoint gets its own independent counter (different `key_prefix`), so exhausting `/login`'s limit doesn't affect `/signup`. Exceeding the limit raises `HTTPException(429)` directly — this one deliberately does NOT go through the `app.core.exceptions` domain-error hierarchy, since rate limiting is infra operating right at the HTTP boundary, not a business rule a domain service is deciding. Requires the `redis` container (`docker compose up -d`) and `REDIS_URL` in `.env`.

**RBAC (`app/domains/rbac/`)**: three roles — `admin`, `hr`, `applicant` — seeded via migration, fixed at deploy time (a new role isn't useful until code checks for it). What's actually configurable at runtime is **which permissions each role has**, via the `role_permissions` table:
- `roles` / `permissions` — seeded, effectively read-only in normal operation.
- `role_permissions` (composite PK: role_id + permission_id) — the live, editable part. Managed through admin-only endpoints: `GET /rbac/roles`, `GET /rbac/permissions`, `POST /rbac/roles/{role_name}/permissions/{permission_key}` (grant), `DELETE .../{permission_key}` (revoke).
- Enforcement: `require_permission(permission_key)` (`app/domains/rbac/dependencies.py`) — same factory-returning-a-`Depends()` pattern as `rate_limit`. It checks `role_permissions` **live on every request** — permissions are never cached in the JWT, so granting/revoking one takes effect on the caller's very next request, no re-login needed (verified: revoking `manage_hr_accounts` from `hr` mid-session immediately 403s a still-valid, already-issued HR access token).
- Current permissions: `manage_hr_accounts` (create HR accounts — `POST /auth/hr-accounts`), `manage_rbac` (the `/rbac/*` endpoints themselves), `manage_own_profile` (granted to all three roles). Seeded grants: admin → all three; hr and applicant → `manage_own_profile` only. Adding a new gated capability means adding a new `Permission` row (migration) and granting it to whichever roles should have it — either in a migration (default) or live via the grant endpoint.
- `RolePermissionRepository` does **not** extend `BaseRepository` — its table has a composite PK, which doesn't fit `BaseRepository`'s single-`id` `get_by_id` contract. It's the one deliberate exception to "always subclass BaseRepository."
- Dependency direction: `auth` depends on `rbac` (for `require_permission` and role lookup during signup), never the reverse. `auth.dependencies` duplicates a trivial `get_role_repository` factory rather than importing it from `rbac.dependencies`, specifically to avoid a circular import (`rbac.dependencies` imports `get_current_user` from `auth.dependencies`).
- Bootstrapping: nothing in the API can create the first admin (admins are the only ones who create accounts). `uv run python -m app.scripts.create_admin` does it directly via `SessionLocal()` — reads `ADMIN_EMAIL`/`ADMIN_PASSWORD`/`ADMIN_FIRST_NAME`/`ADMIN_LAST_NAME`/`ADMIN_CONTACT_NUMBER` from env (prompts for email/password if unset), errors clearly instead of duplicating if that email already exists.
- `User.resume_object_key` is nullable — it's applicant-specific. HR/admin accounts (`create_hr_account`, the seed script) never set it.

**MinIO layout**: resumes are stored under the `applicant_resume/` prefix within the `resumes` bucket (`applicant_resume/{user_id}/{uuid4}_{filename}`, built in `AuthService.signup()`), not directly at the bucket root — keeps the bucket organized if other file types get added later (e.g. HR-uploaded documents would get their own prefix, not dumped alongside resumes).

## Testing

`tests/unit/` mirrors `app/`'s structure (`core/`, `auth/`, `rbac/`). Run with `uv run pytest` (or `uv run pytest -v`) — **no Docker containers required**; these are pure unit tests exercising services directly with `unittest.mock.MagicMock` repositories, which is the whole point of the entities/domain-exceptions split above (verified by running the full suite with Postgres/MinIO/Redis all stopped — all 33 pass).

- `test_service.py` per domain — constructs `AuthService`/`RBACService` with mocked repositories, asserts on raised domain exceptions and on what the mocks were called with (e.g. `role_permissions.grant.assert_called_once_with(role.id, permission.id)`). No real database.
- `test_security.py` — pure roundtrip tests for `hash_password`/`verify_password`/`create_access_token`/`create_refresh_token`/`decode_token`.
- `test_exception_handlers.py` — a throwaway `FastAPI()` app + `TestClient` proving each `DomainError` category maps to its documented status code (and that `UnauthorizedError`'s `headers` argument actually reaches the response).
- When a fake repository needs to simulate "after commit, the DB filled in server-generated columns" (e.g. `created_at`), don't return the same entity object that was passed to `add()` — timestamps on it are still `None`. Use `dataclasses.replace(entity, created_at=..., updated_at=...)` to simulate what a real `get_by_id` re-fetch would return (see `_as_persisted` in `tests/unit/auth/test_service.py`) — this bit two tests during development, it's not an application bug.

No integration tests yet (nothing hits a real Postgres/MinIO/Redis) — worth adding once there's a second domain to prove the repository mapping layer (`_to_entity`/`_to_model`) itself is correct against a real schema, not just that services call their collaborators correctly.

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
