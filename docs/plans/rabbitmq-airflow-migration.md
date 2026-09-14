# Migration plan — RabbitMQ (queueing) + Airflow (orchestration)

Status: **Phases 0–4 code-complete, committed and pushed; scheduler cutover
(Phase 5) not flipped — see "What's remaining" below.** Companion to
[docs/decisions/D06-scheduler-ownership.md](../decisions/D06-scheduler-ownership.md)
(which already commits to "delete `app/core/scheduler.py`, the two sweep
scripts become two Airflow tasks" as the known end state) and
[docs/architecture.md](../architecture.md).

## What's remaining

The disk-space/Docker-corruption problem that blocked verification resolved
itself (host disk recovered from ~250 MiB to ~2.9 GiB free on its own;
`docker builder prune -f` reclaimed a further ~20 GiB of stale build cache
from unrelated projects on this machine, safe/regenerable, not touching any
project's data or volumes). With Docker healthy again, the real
verifications below all ran — **for real, against live services, not
mocked** — with one genuine bug found and fixed along the way.

**Done, verified for real (not just "should work"):**
1. **RabbitMQ round-trip against the actual app code** (Phase 2). Started
   `uv run faststream run app.workers.evaluation_export:app` for real,
   published a job through `app/core/queue.py` exactly as
   `ExportJobService.enqueue` does, and watched the full pipeline complete:
   consumed → `AssessmentService`/`JobPostRepository` built a real
   evaluation pack → uploaded to MinIO → `EvaluationExportJob` row reached
   `status="done"` with the correct `result_object_key` → read the object
   back out of MinIO and confirmed it's a well-formed ZIP with the expected
   files. Also proved the "job row not found" branch acks cleanly instead
   of erroring.
2. **Airflow actually starting, and a real bug found + fixed.**
   `airflow-init` initially failed with `ModuleNotFoundError: No module
   named 'airflow'` — root cause: the service's `entrypoint: /bin/bash`
   override (a commonly copy-pasted pattern) **skips the official image's
   own `/entrypoint` script**, which is what makes
   `_PIP_ADDITIONAL_REQUIREMENTS` actually resolve on `PYTHONPATH`
   afterward. Fixed in `docker-compose.airflow.yml`: keep the image's
   default `ENTRYPOINT` and pass `bash -c "..."` as the *command* instead —
   confirmed working (`airflow db migrate` ran and actually created the
   metadata DB's tables) against a real `apache/airflow:3.2.0-python3.12`
   pull. Documented in the compose file itself so nobody reintroduces it.
   A second, separate issue found — **and now fixed too**: `airflow users
   create` initially threw `AttributeError: 'AirflowSecurityManagerV2'
   object has no attribute 'find_role'`. Root cause: Airflow 3's own default
   auth manager (`SimpleAuthManager`) doesn't implement `find_role`, which
   the FAB provider's `users create` command needs. Fix: set
   `AIRFLOW__CORE__AUTH_MANAGER: airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager`
   explicitly in `docker-compose.airflow.yml` — confirmed working end to
   end: `airflow-init` now prints `User "admin" created with role "Admin"`,
   and with the full stack up (`airflow-api-server` +
   `airflow-scheduler` + `airflow-dag-processor`), `GET
   /api/v2/monitor/health` returns 200 and `POST /auth/token` with
   `admin`/`admin` returns a real JWT — a genuine login, not just a
   container that didn't crash.
3. **`airflow/dags/assessment_sweep_dag.py` imports cleanly and the
   dependency graph is exactly as designed**, checked directly inside the
   real container: `dag.dag_id == "assessment_sweep"`, all 3 tasks present
   (`expire_attempts`, `disqualify_applications`, `purge_expired_tokens`),
   `expire_attempts.downstream_task_ids == {"disqualify_applications"}`,
   and `purge_expired_tokens` correctly has no dependency edges either way.
4. **The scheduler and dag-processor actually run, not just parse.**
   Brought up `airflow-scheduler` + `airflow-dag-processor` for real: the
   dag-processor found the file, parsed it with **0 errors**, wrote the DAG
   to the metadata DB, and computed the correct next scheduled run from the
   `*/15 * * * *` cron. Both containers stayed up and stable (checked twice,
   15s apart) — no crash loop. Stack torn down afterward
   (`docker compose -f docker-compose.airflow.yml down`) rather than left
   running.
5. **The Phase 4 `dag_bag` check, automated in CI.** `airflow/validate_dags.py`
   (new) runs the same checks as points 3–4 above and is wired into
   `.github/workflows/ci.yml` as its own `airflow-dag-validation` job —
   `docker run` against the real image, no Airflow dependency added to this
   repo's own `pyproject.toml` (2b/2d), independent of the `lint`/`test`
   jobs. Verified locally with the exact command CI runs, both the pass
   case and — deliberately breaking the DAG's dependency edge to check the
   checker itself — the fail case (exit 1, itemized reasons).
6. [`docs/decisions/D10-queue-orchestration-technology.md`](../decisions/D10-queue-orchestration-technology.md)
   — the coherent ADR recording the RabbitMQ/FastStream choice, the
   `AckPolicy` correction, and the SSH-vs-Docker-socket call for Airflow
   task invocation.

**Still remaining — genuinely different work now, not blocked on Docker:**
7. **Phase 5's staged parallel-run verification** — run the Airflow DAG
   *and* `SCHEDULER_ENABLED` side by side for one full sweep cycle in a
   non-prod environment, diff the *business outcomes* (same applications
   disqualified, same attempts expired). What's proven so far is that the
   DAG mechanically works (parses, schedules, validates in CI, and — per
   point 1's pattern — the underlying `ats-cli sweep` commands work
   standalone); what's **not** proven is a live `SSHOperator` task actually
   reaching the app host and producing correct results end-to-end, since
   that needs the real SSH provisioning in point 10 below.
8. Delete `app/core/scheduler.py`, its `main.py` lifespan calls, and
   `scheduler_enabled`/`scheduler_interval_minutes` from `Settings` —
   deliberately still not done; gated on point 7, not on Docker anymore.
9. `uv remove apscheduler` — same gate as point 8.
10. Update `docs/decisions/D06-scheduler-ownership.md` with a final
    "implemented" note — same gate as point 8.

**Not code at all — real deploy-environment setup, whenever this actually
gets deployed:**
11. The app-host SSH user/key the plan's `SSHOperator` approach needs
    (`authorized_keys` `command=`-pinned to `docker compose run --rm app ...`,
    or equivalent), the matching Airflow `Connection`, and the
    `ats_app_dir` Airflow `Variable`. All documented as prerequisites in
    `airflow/dags/assessment_sweep_dag.py`'s own module docstring; none of
    it is something a coding session can provision. This is what point 7
    is actually waiting on now — not Docker, not code.

Everything else — Phases 0–4's actual code (RabbitMQ client library,
`app/core/queue.py`, the FastStream worker, `app/cli.py`, the DAG file, the
`airflow-dag-validation` CI job, all associated tests, README/CLAUDE.md
updates) — is done, **committed and pushed** (`6111a60` on
`infra/rabbitmq-airflow-migration`, confirmed live on GitHub), and verified
for real: imports clean, `ruff check`/`ruff format --check` clean (aside
from 3 pre-existing unrelated files), full unit suite green, and — as of
this session — the full integration suite green against a real Postgres too
(303 tests, no skips) plus the live RabbitMQ/Airflow checks described above.

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

### Phase 0 — Spike / compatibility check — **done ✅**
- **FastStream on Python 3.14:** confirmed. PyPI classifiers for
  `faststream==0.7.5` list 3.10–3.14 explicitly; `uv add "faststream[rabbit]"`
  resolves and installs cleanly against this repo's 3.14 environment (pulls
  in `aio-pika==10.0.1`, `aiormq==7.0.0`, `fast-depends==3.0.8`, no conflicts).
  `app.main` still imports cleanly, and the full suite (297 tests) still
  passes with the dependency present but unused.
- **Real round-trip, not just import:** a throwaway `rabbitmq:4-management`
  container + a `RabbitBroker`/`@broker.subscriber` spike script published
  and consumed a message end-to-end on this machine — `Received` /
  `Processed` in the broker log, the handler's payload matched what was
  published. Container torn down after. This is the strongest form of "does
  it work here" short of the real Phase 2 implementation.
- **Airflow on Python 3.14:** supported since Airflow **3.2.0** (per
  Airflow's own release notes) — but there's a live rough edge as of this
  writing: [apache/airflow#64954](https://github.com/apache/airflow/issues/64954)
  reports a numpy-version mismatch between the published 3.14 constraints
  file and the official Docker image for 3.2.0, breaking custom image builds
  that freeze requirements from a local dev install (workaround noted there:
  build against the 3.13 constraints file instead). Two things make this a
  non-blocker for *this* plan specifically: (1) the `SSHOperator` approach
  (2b) means Airflow's own Python version never has to match the app's 3.14
  at all — Airflow can run on whichever Python (3.12/3.13) is most stable
  for it, completely independent of the app container it SSHes into; (2)
  even if Airflow itself moves to 3.14 later, re-check that specific issue's
  status before building any custom Airflow image against 3.14 constraints.
- `faststream[rabbit]` is left installed (`pyproject.toml`/`uv.lock`
  updated) rather than added-then-reverted — Phase 2 needs it regardless,
  and leaving it in now avoids re-doing this exact verification later. Ruff/
  pytest/alembic all still green with it present. Not yet wired into any
  app code (`app/core/queue.py` doesn't exist yet — that's Phase 2 step 2).

### Phase 1 — Infrastructure — **done ✅, fully verified**
- `docker-compose.yml`: added a `rabbitmq` service (`rabbitmq:4-management`,
  management UI at `:15672`, `guest`/`guest` dev-only creds, its own
  `rabbitmq_data` volume). Validated with `docker compose config`.
- `RABBITMQ_URL` added to `app/core/config.py`'s `Settings` (defaults to the
  compose service above) and `.env.example`, matching the `redis_url`/
  `minio_*` pattern.
- `docker-compose.airflow.yml` (new, repo root, separate from
  `docker-compose.yml` per the reasoning above): trimmed from Airflow's
  official quickstart down to **LocalExecutor** (decision 2c) — no Redis
  broker, no Celery worker, no Flower. Services: `airflow-postgres` (its own,
  separate metadata DB), `airflow-init`, `airflow-api-server` (Airflow 3.x
  renamed `webserver` → `api-server`; port `8081:8080`), `airflow-scheduler`,
  `airflow-dag-processor` (Airflow 3.x split DAG parsing out of the
  scheduler into its own service). No `airflow-triggerer` — deliberate,
  `SSHOperator` isn't deferrable; noted in-file if a future DAG needs one.
  `_PIP_ADDITIONAL_REQUIREMENTS: apache-airflow-providers-ssh` gets the
  `SSHOperator` (2b) installed for local dev; bake into a custom image
  instead once this is more than a laptop (Phase 5). **Actually started for
  real** (`airflow-init`, `airflow-scheduler`, `airflow-dag-processor` all
  ran against a real `apache/airflow:3.2.0-python3.12` pull) — see the
  "What's remaining" section at the top for the full verification and the
  one real bug found (`entrypoint: /bin/bash` breaking
  `_PIP_ADDITIONAL_REQUIREMENTS`) and fixed in this file.
- `airflow/dags|config|plugins/` scaffolded (empty, `.gitkeep`); `airflow/logs/`
  added to `.gitignore` (Airflow's own runtime output, never committed).
- CI (`.github/workflows/ci.yml`): added a `rabbitmq:4` service container
  (no management UI needed in CI) next to `postgres`/`redis`, with a
  `rabbitmq-diagnostics -q ping` health check, and `RABBITMQ_URL` in the
  job's env — ready for Phase 2's integration test. Airflow DAG validation
  stays deferred to Phase 4 as planned (doesn't need a running Airflow
  stack).
- README/CLAUDE.md updated (new "Migration in progress" note under
  "Background jobs (arq)", Airflow quickstart commands, `airflow/`
  top-level entry, `docker compose up -d` now includes RabbitMQ).

**What's verified — all of it now:**
- ✅ `faststream[rabbit]` really connects to and round-trips through a real
  RabbitMQ container on this machine's Python 3.14 (Phase 0), and (Phase 2)
  the real `app/core/queue.py`/`evaluation_export.py` pipeline does too.
- ✅ Both compose files parse correctly (`docker compose config` on each).
- ✅ `docker-compose.airflow.yml` actually starts end-to-end:
  `airflow-init` ran `airflow db migrate` for real (metadata tables
  created), `airflow-scheduler` + `airflow-dag-processor` came up and
  stayed stable, and the dag-processor parsed
  `airflow/dags/assessment_sweep_dag.py` with 0 errors. Full detail in
  "What's remaining" at the top.
- ✅ App still imports clean, `ruff check` clean; full suite green
  including integration tests against a real Postgres (303 tests, no
  skips, as of this session).

### Phase 2 — RabbitMQ migration (replaces arq) — **done ✅, fully verified against a real broker**
1. ~~`uv add "faststream[rabbit]"`~~ done in Phase 0. `uv remove arq` done
   now that the cutover is code-complete (`hiredis` wasn't actually a
   direct dependency — it came in transitively via arq and left with it).
2. `app/core/queue.py` (new, replaces the deleted `app/core/job_queue.py`)
   — `RabbitBroker(settings.rabbitmq_url)`, a `get_broker()` FastAPI
   dependency, and the two `RabbitQueue` declarations (main queue + DLQ,
   see point 5).
3. `app/workers/evaluation_export.py` rewritten: `build_evaluation_export`'s
   business logic is **byte-for-byte unchanged** (still just takes
   `job_id: str` — arq's `ctx: dict` first-arg was never used, so dropping
   it was zero-risk), now a `@broker.subscriber(...)` instead of an arq
   `WorkerSettings.functions` entry. Run as its own process:
   `uv run faststream run app.workers.evaluation_export:app`.
4. `ExportJobService.enqueue` (`export_jobs.py`) swaps
   `arq_pool.enqueue_job("build_evaluation_export", str(job_id))` for
   `broker.publish(str(job_id), EVALUATION_EXPORT_QUEUE)`; its
   `arq_pool: ArqRedis` param became `broker: RabbitBroker`, and the
   router's `Depends(get_arq_pool)` became `Depends(get_broker)`.
5. **Dead-letter queue, done — but not the retry policy originally
   planned.** `EVALUATION_EXPORT_QUEUE` declares
   `x-dead-letter-exchange`/`x-dead-letter-routing-key` pointing at
   `EVALUATION_EXPORT_DLQ` (`evaluation_export.dlq`), both in
   `app/core/queue.py`. **Discovered while implementing:** the installed
   `faststream==0.7.5` subscriber has no declarative `retry=N` option (that
   API belongs to an older FastStream generation the earlier web research
   surfaced) — only a binary `AckPolicy` (`ACK` / `REJECT_ON_ERROR` /
   `NACK_ON_ERROR` / `MANUAL`). The subscriber uses
   `ack_policy=AckPolicy.REJECT_ON_ERROR`: **one attempt**, then straight to
   the DLQ on any unhandled exception — still strictly more visibility than
   arq gave us (a failed arq job retried silently up to its own default
   `max_tries` and then just vanished), but not the "3 retries then DLQ"
   originally sketched. A second subscriber
   (`log_dead_lettered_export`) on the DLQ logs what lands there — pure
   visibility, not a reprocessing path (the `EvaluationExportJob` row is
   already `status="failed"` with `error_message` by the time a message
   reaches the DLQ). If retries are wanted later, they'd need to be
   hand-rolled (a retry-count header, re-published by the same handler),
   not assumed from the decorator — noted in the worker module's own
   comment.
6. `main.py`'s lifespan: `close_arq_pool()` → `await rabbitmq_broker.stop()`,
   paired with a new `await rabbitmq_broker.start()` at startup (arq's pool
   was lazily created on first use; explicit `start()` is closer to how
   `redis_client` and the DB engines are already handled here). Also added
   a RabbitMQ check to `GET /health/ready` (`rabbitmq_broker.ping(timeout=5)`),
   matching the existing Postgres/Redis checks — not originally scoped in
   this phase, but a two-line addition once the broker object existed.
7. Tests: `tests/unit/evaluations/test_export_jobs.py`'s `enqueue` tests
   swap the mocked `arq_pool.enqueue_job` assertion for a mocked
   `broker.publish(str(job_id), EVALUATION_EXPORT_QUEUE)` assertion — unit
   level, mocked, still passing. **Real-broker verification now done too**,
   for real, not with `TestRabbitBroker`: started the actual worker process,
   created a real `EvaluationExportJob` + real `JobPost`/`User` rows via the
   integration test factories, published through the real `app/core/queue.py`
   broker, and watched the job reach `status="done"` with a real ZIP
   sitting in MinIO (readable back out, correct contents). Also separately
   verified the "job row not found" branch acks cleanly. `app.main`/
   `app.workers.evaluation_export` import clean, `ruff check`/
   `ruff format --check` clean, full suite green (272 unit + 31 integration,
   no skips). A formal `TestRabbitBroker`-based automated test for CI is
   still worth adding later, but the *behavior* itself is now proven, not
   assumed.

### Phase 3 — Airflow migration (replaces APScheduler) — **code done, DAG verified for real; cutover deliberately not flipped**
1. **Done.** `uv add typer`, plus `[build-system]`/`tool.hatch.build.targets.wheel`
   added to `pyproject.toml` (the project wasn't packaged before, so
   `[project.scripts]` entry points silently did nothing until this was
   added — discovered when `uv run ats-cli` first came back empty). New
   `app/cli.py` — a Typer `sweep` command group; `run()`/`main()` return
   values in each script were **changed from `None` to the counts they
   already computed** (`int` / `dict[str, int]`) — the smallest possible
   extension needed for real `--json` output, not the "leave them fully
   untouched" originally sketched. `sweep_advisory_lock` itself is
   untouched. Verified for real, including a successful run: with Postgres
   back up, `uv run ats-cli sweep expire-attempts` and
   `disqualify-applications` both ran clean against the real (now-seeded)
   database as part of this session's broader re-verification.
2. **Not done — this is infrastructure provisioning, not code**, and
   belongs to whoever actually deploys this (the app host, the SSH user,
   the Airflow Connection all need to exist somewhere real). Documented in
   `airflow/dags/assessment_sweep_dag.py`'s own module docstring as
   required setup instead. This is now the *actual* remaining gate — not
   Docker, not code (see "What's remaining" at the top).
3. **Done.** `docker-compose.airflow.yml`'s `airflow-init`/`airflow-scheduler`/
   `airflow-dag-processor` all started and ran for real once Docker
   recovered — see "What's remaining" for the full account, including the
   `entrypoint: /bin/bash` bug found and fixed.
4. **Done**, with corrections found while implementing (the earlier
   sketch used stale Airflow 2.x conventions), **and now import-verified
   against a real Airflow 3.2.0 install**:
   - `schedule="*/15 * * * *"` — **not** `schedule_interval=`, which
     Airflow 3 removed (merged into `schedule`, deprecated since 2.4).
   - DAG authoring imports from **`airflow.sdk`**, not `airflow.models.dag`
     — Airflow 3.0's Task SDK is now the documented public interface;
     the older import paths are deprecated.
   - `SSHOperator` from `airflow.providers.ssh.operators.ssh`
     (`apache-airflow-providers-ssh`, already wired into
     `docker-compose.airflow.yml`'s dev-time `_PIP_ADDITIONAL_REQUIREMENTS`).
   - The app-host directory the SSH command `cd`s into before
     `docker compose run` comes from an Airflow Variable
     (`{{ var.value.get('ats_app_dir', '/opt/ats-fastapi') }}`, Jinja,
     resolved at task-run time) — **not** a direct `Variable.get()` call at
     DAG-parse time, which has a known `airflow dags reserialize` import
     error in recent Airflow versions.
   - `catchup=False`, `max_active_runs=1` as planned; `retries=2`,
     `retry_delay=timedelta(minutes=2)` as the retry policy (alerting
     channel — Slack/email `on_failure_callback` — left as a real
     deployment's decision, not hardcoded here).
   - Three tasks, not two: `expire_attempts_task >> disqualify_applications_task`
     (ordering preserved) plus an independent `purge_expired_tokens_task`
     (decision 2f — its own task, no dependency edge to the other two,
     since it has nothing to do with their ordering).
   - **Verified for real, inside a running Airflow 3.2.0 container**: the
     module imports cleanly, `dag.dag_id == "assessment_sweep"`, all 3 tasks
     present with the correct ids, `expire_attempts.downstream_task_ids ==
     {"disqualify_applications"}` and `purge_expired_tokens` correctly has
     no edges either way. The real dag-processor separately parsed it with
     0 errors and computed the correct next scheduled run from the cron.
     Full detail in "What's remaining" at the top.
5. **Deliberately NOT done.** `app/core/scheduler.py` is untouched and
   still the live mechanism. The DAG mechanically works now (point 4), but
   deleting `scheduler.py` still needs the Phase 5 parallel-run business-
   outcome verification first — that's gated on point 2's real SSH/host
   provisioning, not on anything a coding session controls.
6. **Deliberately NOT done**, same reasoning as point 5 —
   `scheduler_enabled`/`scheduler_interval_minutes` stay in `Settings`/
   `.env.example`, still true and still load-bearing.
7. **Done** — untouched, as planned. (See point 1 — only the two sweep
   scripts' `run()`/`main()` return types changed, not their locking.)
8. **Deliberately NOT done** — `apscheduler` stays a dependency; see
   points 5–6.

### Phase 4 — Testing & CI
- **RabbitMQ:** integration test publishing/consuming against the real CI
  broker (Phase 1); FastStream's `TestRabbitBroker` for fast unit-level
  coverage of the publish call and the consumer's message handling.
- **Airflow — done ✅, automated in CI.** `airflow/validate_dags.py` runs
  the exact checks the manual verification did (zero import errors, the
  3-task count, the `expire_attempts_task >> disqualify_applications_task`
  edge independent of `purge_expired_tokens_task`), and is wired into
  `.github/workflows/ci.yml` as its own `airflow-dag-validation` job —
  `docker run` against the real `apache/airflow:3.2.0-python3.12` image
  (no dependency group added to this repo's own `pyproject.toml`; Airflow
  never becomes a dependency of the FastAPI app itself, per 2b/2d), no
  running scheduler/webserver needed, independent of the `lint`/`test`
  jobs' services. Verified locally with the exact command CI runs: passes
  cleanly against the real DAG (`DAG_VALIDATION_OK`), and — sanity-checked
  the checker itself — correctly fails (exit 1, itemized reasons) when the
  task dependency edge is deliberately reversed.
- **CLI — done.** `tests/unit/test_cli.py` (Typer's `CliRunner`, same shape
  as FastAPI's `TestClient`) — 6 tests covering all three `sweep` commands:
  `--json` output shape, exit 0 on a plain success, the "skipped" message
  and exit 0 when the advisory lock is already held, and exit != 0 when the
  wrapped script raises. Runs in the main suite already (`uv run pytest`),
  no SSH/Docker/Airflow needed — proves the Typer wiring itself, not the
  SSH → `docker compose run` path (that's still infrastructure to verify
  per-environment, not application code this repo's tests can reach).
- Re-run the full existing suite (`uv run pytest`) after each phase — same
  ritual as every batch in this session: `ruff check`, `ruff format
  --check`, `pytest -q`, `alembic check` (Airflow's own metadata DB has its
  own separate migration story per 2c, not `alembic check`'s concern).

### Phase 5 — Rollout / cutover
- **Queue (Phase 2): done.** This ended up being the clean cutover
  originally planned, not a staged parallel run — arq is fully removed
  (`uv remove arq`) and the real end-to-end verification (see "What's
  remaining" at the top) stood in for "verify one real export end-to-end"
  before retiring it. Nothing left to do here.
- **Scheduler (Phase 3): not started — this is the real remaining work.**
  This one changes production data (disqualifications, attempt expiry) on
  its own timer with no user in the loop, so it still gets the staged
  treatment the queue didn't need: once the real SSH/host provisioning
  (point 2 in "What's remaining") exists somewhere, run the Airflow DAG
  **and** leave `SCHEDULER_ENABLED` on (both active) for one full
  sweep-interval cycle in a non-prod environment, diff the outcomes (same
  applications disqualified, same attempts expired), then flip
  `SCHEDULER_ENABLED=false` and confirm only the DAG is now producing the
  effects, before deleting `scheduler.py`. Everything mechanical the DAG
  needs to pass this check is now verified (Phase 3 point 4); what's left
  is purely "does it produce the same real-world outcomes," which needs
  the real provisioning to even attempt.
- **Rollback:** keep the APScheduler code on a branch (or just don't merge
  the deletion commits) until the scheduler cutover has run cleanly in
  production for a defined bake period (e.g. one week) — cheap insurance
  given how contained the deletion is.

### Phase 6 — Documentation & cleanup
- **Mostly done, incrementally, per-phase rather than saved for the end:**
  CLAUDE.md has the `airflow/` top-level entry, the `app/cli.py` entry, the
  `app/scripts/` entry covering all three sweep scripts, and rewritten notes
  for `evaluation_export.py` (FastStream, not arq) and the disqualify/expire
  sweep (three-task DAG status, `scheduler.py` deletion explicitly gated on
  Phase 5). README's "Background jobs" and "Background sweep" sections
  describe the current (arq-free) reality and the Airflow cutover's
  not-yet-flipped status, with `ats-cli` commands documented.
- **Done:** [`docs/decisions/D10-queue-orchestration-technology.md`](../decisions/D10-queue-orchestration-technology.md)
  — one coherent ADR for the RabbitMQ-vs-alternatives, `AckPolicy` vs. the
  originally-assumed `retry=N`, and Airflow-executor/SSH-vs-Docker-socket
  calls, superseding the scattered per-phase "discovered while
  implementing" notes above as the durable record.
- **Still pending, correctly held until the actual cutover:**
  - Update D06 with a final "implemented" note — **not yet**, since the
    scheduler hasn't actually been replaced (Phase 3 points 5/6/8).
  - Remove `apscheduler` from `pyproject.toml` — blocked on Phase 3
    points 5/6/8 (the scheduler is still live). `arq`/`hiredis` are already
    gone (Phase 2).

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
