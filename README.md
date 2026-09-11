# ats-fastapi

Applicant Tracking System API — FastAPI, async SQLAlchemy, PostgreSQL, MinIO, Redis.

Domain-based modular monolith. See [CLAUDE.md](CLAUDE.md) for the architecture
in depth and [docs/architecture.md](docs/architecture.md) for the write/read
conventions and their deliberate exceptions.

## Requirements

- [uv](https://docs.astral.sh/uv/) (package manager)
- Docker + Docker Compose (Postgres, MinIO, Redis, RabbitMQ; Airflow
  separately and optionally — see "Background jobs (arq)" below)
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

An in-process APScheduler job expires overdue assessment attempts, then
disqualifies overdue applications, then purges expired refresh-token denylist
rows. It is **opt-in** via `SCHEDULER_ENABLED` and must run on at most one
process; a Postgres advisory lock guards each tick (the first two jobs share
one lock; the token purge doesn't need one — see the script's own docstring).

The same logic is runnable standalone, either the original per-script form:

```bash
uv run python -m app.scripts.expire_overdue_assessment_attempts
uv run python -m app.scripts.disqualify_overdue_applications
uv run python -m app.scripts.purge_expired_revoked_tokens
```

or the newer `ats-cli` front door (same scripts underneath; adds `--json`
output and predictable exit codes for an orchestrator):

```bash
uv run ats-cli sweep expire-attempts [--json]
uv run ats-cli sweep disqualify-applications [--json]
uv run ats-cli sweep purge-expired-tokens [--json]
```

**Migrating to Airflow** (review D06 / see
[docs/plans/rabbitmq-airflow-migration.md](docs/plans/rabbitmq-airflow-migration.md)
Phase 3) — `airflow/dags/assessment_sweep_dag.py` runs the three commands
above via `SSHOperator`, on the schedule APScheduler used to. **Not yet
cut over**: that DAG hasn't been verified against a real Airflow install yet
(blocked on a host Docker/disk problem while this was being built — see the
plan doc), so `app/core/scheduler.py`/`SCHEDULER_ENABLED` stay the live
mechanism for now, deliberately not deleted, per the plan's own staged-
cutover guidance (run both in parallel, diff outcomes, then retire the old
one). See [docs/decisions/D06-scheduler-ownership.md](docs/decisions/D06-scheduler-ownership.md).

## Background jobs (RabbitMQ + FastStream)

`POST /applications/export/async` (review F09/F26) publishes a large
evaluation-pack export to RabbitMQ instead of building it inline — for job
posts too big for the synchronous `GET /applications/export` route. A
[FastStream](https://faststream.ag2.ai/) consumer (`app/workers/evaluation_export.py`)
does the actual build; a message that fails is dead-lettered to
`evaluation_export.dlq` (no automatic retry — see that file's own comment on
why). Run the worker as its own process (needs the same `.env` as the API,
including `RABBITMQ_URL`; `docker compose up -d` brings up the `rabbitmq`
service, management UI at http://localhost:15672, guest/guest):

```bash
uv run faststream run app.workers.evaluation_export:app
```

Poll `GET /applications/export-jobs/{id}` for status, then
`GET /applications/export-jobs/{id}/download` once it's `done`.

**Migrated off arq/Redis** (review, see
[docs/plans/rabbitmq-airflow-migration.md](docs/plans/rabbitmq-airflow-migration.md)
Phase 2) — arq is no longer a dependency. "Background sweep" above is
still migrating from APScheduler to Airflow (that plan's Phase 3, code
ready, cutover not yet flipped); this section will be updated again once
that lands too.

- Airflow is optional and lives in its own compose file, separate from the
  app's (different lifecycle — its own Postgres, genuinely skippable if
  you're just doing API work):
  ```bash
  AIRFLOW_UID=$(id -u) docker compose -f docker-compose.airflow.yml up airflow-init
  AIRFLOW_UID=$(id -u) docker compose -f docker-compose.airflow.yml up
  ```
  UI at http://localhost:8081 (default admin/admin — override
  `_AIRFLOW_WWW_USER_USERNAME`/`_AIRFLOW_WWW_USER_PASSWORD` before this is
  anything but a laptop). No DAGs exist yet (`airflow/dags/` is empty
  pending Phase 3 of the plan above).

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
