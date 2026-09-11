# ats-fastapi

Applicant Tracking System API — FastAPI, async SQLAlchemy, PostgreSQL, MinIO, Redis.

Domain-based modular monolith. See [CLAUDE.md](CLAUDE.md) for the architecture
in depth and [docs/architecture.md](docs/architecture.md) for the write/read
conventions and their deliberate exceptions.

## Requirements

- [uv](https://docs.astral.sh/uv/) (package manager)
- Docker + Docker Compose (Postgres, MinIO, Redis)
- Python 3.14 (pinned in `.python-version`; `uv` installs it)

## Setup

```bash
cp .env.example .env            # then edit secrets
docker compose up -d            # Postgres + MinIO + Redis
uv sync                         # install dependencies
uv run alembic upgrade head     # apply migrations
uv run python -m app.scripts.create_admin   # bootstrap the first admin
```

Optionally seed dev data: `uv run python -m app.scripts.seed_dummy_data`
(dummy user password: `Password123!`).

## Running

```bash
PYTHONUTF8=1 uv run fastapi dev app/main.py
```

API is under `/api/v1` (e.g. `POST /api/v1/auth/signup`). `/health` is
unversioned. Interactive docs at `/docs`.

`PYTHONUTF8=1` is required on Windows (the dev-server banner otherwise crashes
on the cp1252 console codec).

## Tests

```bash
uv run pytest            # unit tests — no containers required
uv run pytest tests/integration  # needs a real Postgres (see conftest.py) — auto-skips if unreachable
```

The unit suite mocks repositories and never touches Postgres/MinIO/Redis. It
does read configuration, so `.env` must exist. `tests/integration/` runs
against a real, throwaway `<db>_test` database (dropped/recreated per session,
migrated via Alembic) — for the races/constraints/N+1 checks a mocked
repository can't cover; see
[docs/maintainability-review.md](docs/maintainability-review.md) F06.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

New domain models must be imported in `alembic/env.py` or autogenerate won't
see them. Offline SQL generation (`--sql`) is **not supported** — some
migrations run queries; use online execution. See
[docs/decisions/D07-migration-baseline.md](docs/decisions/D07-migration-baseline.md).

## Background sweep

An in-process APScheduler job expires overdue assessment attempts and then
disqualifies overdue applications. It is **opt-in** via `SCHEDULER_ENABLED` and
must run on at most one process; a Postgres advisory lock guards each tick. The
same logic is runnable standalone:

```bash
uv run python -m app.scripts.expire_overdue_assessment_attempts
uv run python -m app.scripts.disqualify_overdue_applications
```

See [docs/decisions/D06-scheduler-ownership.md](docs/decisions/D06-scheduler-ownership.md).

## Background jobs (arq)

`POST /applications/export/async` (review F09/F26) hands a large evaluation-pack
export to an [arq](https://arq-docs.helpmanual.io/) worker instead of building
it inline — for job posts too big for the synchronous `GET /applications/export`
route. Run the worker as its own process (needs the same `.env` as the API,
including `REDIS_URL`):

```bash
uv run arq app.workers.evaluation_export.WorkerSettings
```

Poll `GET /applications/export-jobs/{id}` for status, then
`GET /applications/export-jobs/{id}/download` once it's `done`.

## Lint / format

```bash
uv run ruff check .
uv run ruff format --check .
```

Both run in CI (`.github/workflows/ci.yml`) alongside the test suite.

## Auth

Access + refresh JWTs (`app/core/security.py`), bcrypt password hashing (72-byte
limit enforced at the boundary). Refresh tokens are revocable via
`POST /api/v1/auth/logout`; access tokens are not (they just expire). Refresh
does not currently rotate the refresh token — see
[docs/decisions/D08-session-semantics.md](docs/decisions/D08-session-semantics.md).
