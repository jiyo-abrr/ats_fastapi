# Migration plan — RabbitMQ (queueing) + Airflow (orchestration)

Status: **decisions locked (section 2), implementation not started**.
Companion to
[docs/decisions/D06-scheduler-ownership.md](../decisions/D06-scheduler-ownership.md)
(which already commits to "delete `app/core/scheduler.py`, the two sweep
scripts become two Airflow tasks" as the known end state) and
[docs/architecture.md](../architecture.md).

## 1. What's moving, and why

Two independent pieces of infrastructure are being replaced:

| Today | Becomes | Why |
| --- | --- | --- |
| **arq** (Redis-backed) — `app/workers/evaluation_export.py`, one background job type (evaluation-pack export, review F09/F26) | **RabbitMQ** — a real message broker with durable queues, dead-lettering, and delivery acknowledgment, instead of Redis repurposed as a job queue | RabbitMQ is the standing target for "queueing" per this request; it also gives durability guarantees (message survives a broker restart) and dead-letter handling arq doesn't have out of the box. |
| **APScheduler** (in-process, one Python thread per web worker) — `app/core/scheduler.py`, the 15-minute expire→disqualify sweep | **Airflow** — a real orchestrator with a UI, task-level retries, dependency graphs, alerting, and a run history | This was already the documented end state (D06, and `scheduler.py`'s own docstring: *"This file is the only thing deleted when the cron responsibility moves to Airflow"*). Today's setup has no visibility into whether a tick ran, no per-task retry, and requires the `SCHEDULER_ENABLED` single-process discipline to stay correct. |

**Not in scope:** `app/core/rate_limit.py`'s Redis usage (fixed-window
counters) stays on Redis — that's a cache/counter use case, not a queue, and
RabbitMQ is the wrong tool for it. Redis is *not* being removed from the
stack; it just stops being the job-queue backend.

## 2. Decisions

Settled with the user (all three landed on the recommended option).

### 2a. RabbitMQ client library — **decided: FastStream**

| Option | Verdict |
| --- | --- |
| **FastStream** (`faststream[rabbit]`) — **decided** | Async-native (matches this codebase's "fully async end to end" rule in CLAUDE.md), FastAPI-shaped DX (`@broker.subscriber(...)` decorators, Pydantic message validation, built-in test client), actively maintained, smallest conceptual jump from arq's `@task` shape. |
| `aio-pika` directly | More control, but means hand-rolling retry/ack/dead-letter/prefetch logic FastStream already provides. Fallback if FastStream turns out to be immature on Python 3.14 (see 2d). |
| Celery + RabbitMQ broker | The "canonical" RabbitMQ pairing, but Celery workers are sync-first — every task would need `asyncio.run(...)` inside a sync function to call our async services, the same bridge arq specifically let us avoid. Also a much heavier dependency footprint (celery + kombu + billiard) for one job type. Rejected — no reason to standardize on Celery specifically here. |
| `rstream` (RabbitMQ **Streams** protocol) — considered, rejected | Targets a different RabbitMQ subsystem than classic queues: an append-only log (Kafka-shaped) where messages aren't removed on consumption and multiple consumer groups replay independently. The evaluation-export workload is job-shaped, not log-shaped — one job, one worker, ack-and-gone — so classic-queue semantics (native dead-lettering, per-message retry/nack) fit better than something built on log-replay. Worth revisiting only if a genuinely log-shaped workload shows up later (e.g. an application-status-change event stream multiple independent consumers replay), not for this job. |

### 2b. Airflow task-invocation strategy

How does an Airflow task actually run `expire_overdue_assessment_attempts` /
`disqualify_overdue_applications`? **Decided: `SSHOperator` to the app host,
which runs the sweep through Docker Compose there — not a shared
filesystem/venv, and not a Docker socket handed to Airflow.**

First, the scripts themselves get a proper CLI: a new **Typer** command
group (`uv add typer`; Typer is built on Click, matches this codebase's
FastAPI/Pydantic-author lineage and type-hint-driven style) wraps the
existing `run()` functions — `uv run ats-cli sweep expire-attempts` / `uv
run ats-cli sweep disqualify-applications`, registered as a
`[project.scripts]` entry point (`ats-cli`) in `pyproject.toml`. This
replaces the two bare `if __name__ == "__main__":` blocks with real
subcommands (`--help`, proper exit codes, a `--json` result flag Airflow's
`on_failure_callback` can parse) while leaving `run()`/`sweep_advisory_lock`
untouched.

| Option | Verdict |
| --- | --- |
| **`SSHOperator` → app host → `docker compose run --rm app uv run ats-cli sweep <task>`** — **recommended, decided** | Airflow needs only an SSH connection (a Connection entry + a key scoped, via `authorized_keys` `command=` pinning or a locked-down deploy user, to nothing but that one `docker compose run` invocation) — no shared filesystem, no shared Python version, no Docker socket or Kubernetes API exposed to Airflow at all. Each run gets a fresh, throwaway container (`--rm`), the same isolation `DockerOperator` gives you, without adding a new Airflow provider's API surface or the socket-mount privilege-escalation risk that comes with it. Works whether Airflow and the app share infrastructure or not. |
| `sshd` running *inside* the app container, `SSHOperator` connects there directly | Rejected. Means baking and running a second long-lived service (sshd) inside an image whose entire job is one Python process, managing SSH keys as Airflow Connections for it, and it's ambiguous against N app replicas — which one do you SSH into? Docker/Kubernetes already have their own exec/attach primitives for this; a long-lived sshd inside a container is the anti-pattern version of the same idea. |
| `BashOperator`: `uv run python -m app.scripts.<name>` | Only works if Airflow and the app happen to share a filesystem/venv (same host, same `uv`-managed environment) — not a safe assumption once Airflow is genuinely separate infrastructure (see open question 2). Superseded by the `SSHOperator` approach, which gets the same "Airflow's Python env never needs the app's deps" property without that assumption. |
| `DockerOperator` (Docker Engine API) | Same throwaway-container isolation as the chosen approach, but requires exposing the Docker socket (or a remote Docker API endpoint) to Airflow — real privilege-escalation surface, since anything that can talk to that socket can effectively root the host. Rejected in favor of SSH, which uses a much smaller, better-understood credential (one restricted SSH key). |
| `PythonOperator` importing `app.scripts.*` directly, wrapped in `asyncio.run(...)` | Tightest integration, but couples Airflow's Python environment to the app's full dependency set and Python version (3.14 — see 2d), and reintroduces the sync/async bridge point. No benefit over the SSH approach for two scripts that already have (soon-to-be Typer) CLI entry points. |

### 2c. Airflow executor + metadata DB

- **Executor:** `LocalExecutor` is enough — two tasks, one DAG, no need for
  `CeleryExecutor`'s distributed-worker model at this scale. (Using
  `CeleryExecutor` backed by the *same* RabbitMQ broker from 2a is possible
  later if Airflow's own task volume grows, but would be premature now.)
- **Metadata DB:** a **separate** Postgres database/instance from the app's,
  not a schema inside it. Airflow owns its own migrations (`airflow db
  migrate`) and its schema has zero business meaning — sharing the app's DB
  would just create an unrelated migration-ownership conflict.

### 2d. Python 3.14 compatibility risk

This project is pinned to Python 3.14 (`.python-version`, very recent as of
writing). **Before committing to FastStream or any Airflow provider version,
verify they support 3.14** — Airflow in particular has historically lagged
the newest CPython by a Python minor version or two. If Airflow doesn't yet
support 3.14:
- Airflow's DAG-authoring code and the app's runtime don't need to share a
  Python version at all — the `SSHOperator` approach (2b) shells out over
  SSH to the app's own venv/container, which stays on 3.14, regardless of
  what Python Airflow itself is pinned to. This is an *additional* reason
  the SSH approach was chosen over `PythonOperator`.
- FastStream needs to run inside the app's own process (the consumer is part
  of this codebase), so it genuinely needs 3.14 support. Check this first;
  if it's not there yet, fall back to `aio-pika` directly (2a).

### 2e. Airflow hosting model — **decided: self-hosted**

Airflow runs self-hosted (Phase 1's own `docker-compose.airflow.yml`), on
infrastructure that can reach the app host over plain SSH — same network,
VPN, or bastion, but not a third-party-controlled worker fleet. This is what
makes 2b's `SSHOperator` plan work without an extra VPC-peering/managed-
network-path project first. If this ever moves to a managed Airflow (MWAA /
Cloud Composer / Astronomer) later, revisit 2b — those workers aren't
guaranteed reachable from the app host by default the way a self-hosted
Airflow is.

### 2f. Refresh-token-denylist cleanup — **decided: third Airflow task**

The cleanup currently riding the same APScheduler timer as the sweep
(unrelated business logic — see section 1's table and Phase 3 step 4) gets
its own task in `assessment_sweep_dag.py` (or its own tiny DAG, if keeping
its schedule independent of the sweep's 15-minute interval turns out to
matter later) rather than moving off Airflow. It gets the same
retry/alerting/run-history Airflow already gives the sweep tasks, for
negligible extra DAG complexity.

## 3. Target architecture

```
                    ┌─────────────┐
  HR clicks         │   FastAPI   │  POST /applications/export/async
  "export" ───────▶ │  (producer) │──────┐
                    └─────────────┘      │ publish
                                          ▼
                                   ┌─────────────┐
                                   │  RabbitMQ   │  durable queue,
                                   │             │  dead-letter queue
                                   └─────────────┘
                                          │ consume
                                          ▼
                                   ┌─────────────┐
                                   │ FastStream  │  app/workers/
                                   │  consumer   │  evaluation_export.py
                                   └─────────────┘
                                          │ writes result, updates
                                          ▼    EvaluationExportJob row
                                   Postgres + MinIO


  Airflow scheduler ──▶ DAG: assessment_sweep (every 15 min, catchup=False,
                        max_active_runs=1)
                          expire_attempts_task >> disqualify_applications_task
                            │                         │
                            ▼                         ▼
                       SSHOperator               SSHOperator
                            │                         │
                            ▼                         ▼
                     ssh app-host:              ssh app-host:
                     docker compose run --rm    docker compose run --rm
                       app uv run ats-cli          app uv run ats-cli
                       sweep expire-attempts        sweep disqualify-applications
                            │                         │
                            └────────┬────────────────┘
                                     ▼
                              same Postgres app DB
                       (sweep_advisory_lock still guards
                        a manual CLI run overlapping a
                        scheduled Airflow run — D06)

  (Airflow's SSH connection is scoped, via authorized_keys command= pinning
   or a locked-down deploy user, to exactly that one docker compose
   invocation — no Docker socket, no Kubernetes API, no shared venv handed
   to Airflow.)
```

## 4. Phased plan

### Phase 0 — Spike / compatibility check (before any other work)
- Confirm FastStream + Airflow's current stable release both support Python
  3.14 (2d). If either doesn't, resolve per the fallbacks above *before*
  Phase 1, not discovered mid-migration.
- Stand up a throwaway RabbitMQ container and Airflow's `docker compose`
  quickstart locally; confirm both start cleanly on this machine/CI runner
  before writing any app code against them.

### Phase 1 — Infrastructure
- Add a `rabbitmq` service to `docker-compose.yml` (image
  `rabbitmq:4-management`, so the management UI is available at `:15672`
  during dev).
- Add `RABBITMQ_URL` (or `RABBITMQ_HOST`/`PORT`/`USER`/`PASSWORD`/`VHOST`) to
  `app/core/config.py`'s `Settings` and `.env.example`, following the
  existing `redis_url`/`minio_*` pattern.
- Airflow gets its **own** `docker-compose.airflow.yml` (or a dedicated
  `airflow/` directory with Airflow's official quickstart compose file,
  trimmed down) — kept separate from the app's `docker-compose.yml` since
  Airflow is a different lifecycle (its own Postgres, its own containers,
  optionally not run at all on a laptop doing pure API work). Document both
  the "just the app" and "app + Airflow" `docker compose` invocations in
  README.
- CI (`.github/workflows/ci.yml`): add a `rabbitmq` service container next
  to the existing `postgres`/`redis` ones, same `--health-cmd` pattern, so
  the integration suite (Phase 4) can run against a real broker. Airflow DAG
  validation (Phase 4) can run as its own lightweight CI job that doesn't
  need the full Airflow stack up (`airflow dags list-import-errors` needs
  only Airflow installed, not a running scheduler/webserver).

### Phase 2 — RabbitMQ migration (replaces arq)
1. `uv add "faststream[rabbit]"`; `uv remove arq hiredis` (deferred to the
   end of this phase, once the cutover is verified — see Phase 5's rollback
   note).
2. New `app/core/queue.py` (replaces `app/core/job_queue.py`) — the
   `FastStream` `RabbitBroker` instance + a `get_broker()` FastAPI
   dependency, mirroring `job_queue.py`'s `get_arq_pool()` shape.
3. Rewrite `app/workers/evaluation_export.py`: same `build_evaluation_export`
   business logic (untouched — it already only takes a `job_id`), now
   registered as a FastStream subscriber instead of an arq `WorkerSettings`
   function. Same "run as its own process" story:
   `uv run faststream run app.workers.evaluation_export:app` in place of
   `uv run arq app.workers.evaluation_export.WorkerSettings`.
4. `app/domains/evaluations/export_jobs.py::ExportJobService.enqueue` swaps
   `arq_pool.enqueue_job("build_evaluation_export", str(job_id))` for a
   `broker.publish(...)` call; update its `arq_pool: ArqRedis` parameter and
   the router's `Depends(get_arq_pool)` accordingly.
5. Declare a dead-letter queue (or FastStream's retry/nack support) for the
   export queue — a job that fails repeatedly (e.g. MinIO unreachable)
   should land somewhere visible, not silently vanish or retry forever. This
   is new behavior arq didn't give us; decide the DLQ policy explicitly
   (e.g. 3 retries with backoff, then DLQ + the `EvaluationExportJob` row
   already gets marked `failed` with `error_message` regardless).
6. `main.py`'s lifespan: replace `close_arq_pool()` with the broker's own
   connect/close (FastStream brokers support `async with`/lifespan
   integration directly — check its FastAPI integration docs for the
   idiomatic hook, likely nicer than the current manual
   `get_arq_pool`/`close_arq_pool` pair).
7. Tests: `tests/unit/evaluations/test_export_jobs.py`'s `enqueue` tests swap
   the mocked `arq_pool.enqueue_job` assertion for a mocked
   `broker.publish` assertion — same shape, different call. Add an
   integration test that publishes to a real (CI) RabbitMQ instance and
   asserts the message lands on the expected queue (FastStream ships a test
   client — `TestRabbitBroker` — that can assert this without a real broker
   too; prefer that for speed, keep one real-broker smoke test for
   confidence).

### Phase 3 — Airflow migration (replaces APScheduler)
1. `uv add typer`. New `app/cli.py` (or `app/cli/` if it grows) — a Typer
   `sweep` command group calling the existing `run()` functions in
   `app/scripts/expire_overdue_assessment_attempts.py` /
   `disqualify_overdue_applications.py` unchanged; register `ats-cli =
   "app.cli:app"` under `[project.scripts]`. `sweep_advisory_lock` stays
   exactly where it is (inside each script's own lock-taking entry point,
   now called by the Typer command instead of the old `if __name__ ==
   "__main__":` block). Verify `uv run ats-cli sweep expire-attempts` /
   `uv run ats-cli sweep disqualify-applications` work locally before
   touching Airflow.
2. Provision the SSH access path (2b): a deploy user (or existing one) on
   the app host, an SSH key pinned to `docker compose run --rm app uv run
   ats-cli sweep ...` via `authorized_keys` `command=` (or an equivalently
   scoped restriction), and an Airflow `Connection` (type `ssh`) holding
   that key. Confirm `ssh <that-connection> 'docker compose run --rm app uv
   run ats-cli sweep expire-attempts'` works manually before wiring Airflow
   to it.
3. Bring up Airflow (Phase 1's compose file) with a `dags/` folder mounted
   in.
4. New `dags/assessment_sweep_dag.py`:
   - `schedule_interval="*/15 * * * *"` (matching today's
     `SCHEDULER_INTERVAL_MINUTES` default — or read it from an Airflow
     Variable if it should stay configurable per-environment).
   - `catchup=False`, `max_active_runs=1` (Airflow's own equivalent of "only
     one tick running at a time" — the advisory lock becomes a
     belt-and-suspenders guard against a *manual* CLI run colliding with a
     scheduled DAG run, not the primary mutual-exclusion mechanism anymore).
   - Two `SSHOperator` tasks per 2b, each running `docker compose run --rm
     app uv run ats-cli sweep expire-attempts` /
     `... sweep disqualify-applications` against the app-host SSH
     connection from step 2:
     `expire_attempts_task >> disqualify_applications_task` — the exact
     ordering already documented in `scheduler.py`'s docstring and
     `disqualify_overdue_applications.py`'s module comment, preserved.
   - Retry policy (`retries=`, `retry_delay=`) and failure alerting
     (`on_failure_callback` — Slack/email webhook, or at minimum
     Airflow's own UI-visible failure state) — this is new capability
     APScheduler never had; decide the alerting channel before cutover.
   - The refresh-token-denylist housekeeping query currently tacked onto
     `_run_periodic_jobs` (unrelated to the sweep, just riding the same
     timer) becomes its own third task or its own DAG — don't silently keep
     coupling it to the sweep's timing just because that's how it happened
     to be wired today.
5. Delete `app/core/scheduler.py` entirely, and its two calls
   (`start_scheduler()`/`shutdown_scheduler()`) from `main.py`'s lifespan —
   exactly the deletion D06 and the file's own docstring already promised.
6. Remove `scheduler_enabled`/`scheduler_interval_minutes` from
   `Settings`/`.env.example` (or keep `scheduler_interval_minutes` only as
   documentation input to the DAG's schedule, if that's more convenient than
   hand-editing the DAG file per environment).
7. `sweep_advisory_lock` (`app/core/sweep_lock.py`) stays — both scripts'
   lock-taking entry points keep taking it, so a manual `uv run ats-cli
   sweep disqualify-applications` still can't collide with a
   concurrently-running Airflow task.
8. `uv remove apscheduler` once the DAG is verified running in every
   environment that mattered (see Phase 5).

### Phase 4 — Testing & CI
- **RabbitMQ:** integration test publishing/consuming against the real CI
  broker (Phase 1); FastStream's `TestRabbitBroker` for fast unit-level
  coverage of the publish call and the consumer's message handling.
- **Airflow:** a `dag_bag` test — import `dags/assessment_sweep_dag.py`,
  assert zero import errors, assert the task count and the
  `expire_attempts_task >> disqualify_applications_task` dependency edge.
  This is the standard, cheap Airflow test pattern (no running
  scheduler/webserver needed) and should run in CI as its own quick job.
- **CLI:** `tests/unit/test_cli.py` (Typer ships a `CliRunner` — same shape
  as FastAPI's `TestClient`) invoking `sweep expire-attempts` /
  `sweep disqualify-applications` against mocked repositories, asserting
  exit code 0 and the `run()` call — proves the Typer wiring itself is
  correct in CI without needing SSH/Docker/Airflow at all; the SSH →
  `docker compose run` path (step 2 of Phase 3) is verified manually per
  environment instead, since it's infrastructure, not application code.
- Re-run the full existing suite (`uv run pytest`) after each phase — same
  ritual as every batch in this session: `ruff check`, `ruff format
  --check`, `pytest -q`, `alembic check` (Airflow's own metadata DB has its
  own separate migration story per 2c, not `alembic check`'s concern).

### Phase 5 — Rollout / cutover
- **Queue (Phase 2):** clean cutover, not a parallel run — there's no
  durable backlog to migrate (in-flight export jobs are short-lived and
  polled by the user; worst case, a job started right before cutover is
  lost and the user retries). Sequence: deploy the FastStream consumer
  process alongside the still-running arq worker → flip
  `ExportJobService.enqueue` to publish to RabbitMQ → verify one real export
  end-to-end → retire the arq worker process and its dependency.
- **Scheduler (Phase 3):** this one changes production data
  (disqualifications, attempt expiry) on its own timer with no user in the
  loop — stage the cutover per environment: run the Airflow DAG **and**
  leave `SCHEDULER_ENABLED` on (both active) for one full sweep-interval
  cycle in a non-prod environment first, diff the outcomes (same
  applications disqualified, same attempts expired), then flip
  `SCHEDULER_ENABLED=false` and confirm only the DAG is now producing the
  effects, before deleting `scheduler.py`.
- **Rollback:** keep the arq/APScheduler code on a branch (or just don't
  merge the deletion commits) until each cutover has run cleanly in
  production for a defined bake period (e.g. one week) — cheap insurance
  given how contained both deletions are.

### Phase 6 — Documentation & cleanup
- CLAUDE.md: add an `airflow/` top-level-package entry (per the project's
  "every top-level package is documented" convention) and an `app/cli.py`
  entry (the Typer `sweep` command group); rewrite the
  `app/workers/evaluation_export.py` note to describe the FastStream
  consumer instead of the arq `WorkerSettings` shape; update the
  "Background jobs (arq)" README section title/instructions to RabbitMQ +
  FastStream commands, and add a "Sweep CLI" note pointing at `ats-cli
  sweep --help` plus the SSH-connection provisioning steps from Phase 3.
- Update D06 with a final "implemented" note (mirroring how D01/D04/D06/D09
  already got marked implemented earlier in this project's history) instead
  of leaving it as a forward-looking decision.
- New `docs/decisions/D10-queue-orchestration-technology.md` recording the
  RabbitMQ-vs-alternatives and Airflow-executor-vs-alternatives calls made
  in section 2, in the same ADR shape as D01–D09 — so the *why* survives
  independently of this plan document once the migration is old news.
- Remove `arq`/`hiredis`/`apscheduler` from `pyproject.toml` (already noted
  per-phase above; called out again here as the final "is anything still
  importing the old thing" sweep — `grep -rn "arq\|apscheduler" app/` should
  come back empty).

## 5. Operational cost, called out explicitly

This is a materially bigger operational footprint than arq+APScheduler:
RabbitMQ and Airflow are each their own long-running services with their own
failure modes, upgrade cadence, and (for Airflow specifically) a non-trivial
metadata database and web UI to keep patched. Airflow in particular is heavy
for orchestrating exactly two tasks — the honest trade-off being made here is
operational overhead now for retry/alerting/audit-trail capability later.
Worth confirming that trade-off is wanted before Phase 1, not after Airflow
is already running in production.

## 6. Decisions confirmed

All three open questions from the previous revision are settled — see 2a,
2e, and 2f respectively:

1. **RabbitMQ client:** FastStream.
2. **Airflow hosting:** self-hosted, reachable from the app host over SSH —
   this is what makes 2b's `SSHOperator` plan work as designed.
3. **Refresh-token-denylist cleanup:** a third task in
   `assessment_sweep_dag.py`.

Nothing is blocking Phase 0 anymore.
