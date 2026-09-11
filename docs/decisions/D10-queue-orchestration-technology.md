# D10 — Queue and orchestration technology (RabbitMQ + Airflow migration)

**Question:** replace arq/Redis (the evaluation-pack export queue, review
F09/F26) with RabbitMQ, and APScheduler (the assessment sweep, review D06)
with Airflow. Which specific libraries/patterns, and why — full detail and
phase-by-phase status lives in
[docs/plans/rabbitmq-airflow-migration.md](../plans/rabbitmq-airflow-migration.md);
this record is the durable *why*, independent of that plan document once the
migration itself is old news.

## Decisions

**RabbitMQ client: FastStream, not Celery or `rstream`.** Celery workers are
sync-first — every task would need `asyncio.run(...)` inside a sync function
to call this app's async services, exactly the bridge arq let us avoid; also
a much heavier dependency footprint (celery + kombu + billiard) for one job
type. `rstream` targets RabbitMQ **Streams** (an append-only, Kafka-shaped
log with multi-consumer-group replay) — a different subsystem from classic
queues; the evaluation-export workload is job-shaped (one job, one worker,
ack-and-gone), where classic-queue semantics (native dead-lettering,
per-message nack) fit better than something built on log-replay. FastStream
is async-native, matches this codebase's "fully async end to end" rule, and
is the smallest conceptual jump from arq's `@task` shape.

**Retry policy: one attempt, then dead-letter — not the "3 retries" first
assumed.** While implementing (Phase 2), the installed `faststream==0.7.5`
turned out to have no declarative `retry=N` subscriber option — that API
belongs to an older FastStream generation early research surfaced. The
actual surface is a binary `AckPolicy` (`ACK` / `REJECT_ON_ERROR` /
`NACK_ON_ERROR` / `MANUAL`). We use `REJECT_ON_ERROR`: one attempt, then the
message routes to `evaluation_export.dlq` via the queue's
`x-dead-letter-exchange`/`x-dead-letter-routing-key` arguments. This is
still strictly more operational visibility than arq gave us (a failed arq
job retried silently up to its own default `max_tries`, then just
vanished) — just not automatic multi-retry. If automatic retries are wanted
later, they need hand-rolling (a retry-count header, re-published by the
same handler), not a decorator flag.

**Airflow task invocation: `SSHOperator` to the app host, not
`BashOperator` or `DockerOperator`.** `BashOperator` only works if Airflow
and the app share a filesystem/venv — not a safe assumption once Airflow is
genuinely separate infrastructure. `DockerOperator` gives the same
throwaway-container isolation but requires exposing the Docker socket (or a
remote Docker API endpoint) to Airflow — real privilege-escalation surface,
since anything that can talk to that socket can effectively root the host.
`SSHOperator` needs only a restricted SSH key (`authorized_keys` `command=`
pinning, or an equivalently locked-down deploy user) scoped to exactly
`docker compose run --rm app uv run ats-cli sweep ...` — a much smaller,
better-understood credential than a Docker socket, and it still gets a
fresh, throwaway container per run via `--rm`. Rejected outright: running
`sshd` *inside* the app container so `SSHOperator` connects directly — bakes
a second long-lived service into an image whose whole job is one Python
process, and is ambiguous against N app replicas (which one do you SSH to?).

**A real CLI (Typer) in front of the sweep scripts, not raw
`python -m app.scripts.*` invocations from Airflow.** `app/cli.py`
(`ats-cli sweep ...`) wraps the existing scripts' `run()`/`main()`
unchanged in spirit (their return types changed from `None` to the counts
they already computed, for real `--json` output — the only concession made
to "leave them untouched"). Gives Airflow's `SSHOperator` a stable, scriptable
front door with proper exit codes and `--json` output instead of scraping
`print()` lines, without coupling Airflow to this app's Python environment.

**Airflow executor: LocalExecutor, not CeleryExecutor.** Two/three tasks,
one DAG — no need for `CeleryExecutor`'s distributed-worker model at this
scale. Revisit only if Airflow's own task volume grows enough to justify
it (and if so, it could reuse the same RabbitMQ broker from the queue
decision above, rather than adding a second broker).

**Airflow metadata DB: separate from the app's Postgres.** Airflow owns its
own migrations (`airflow db migrate`) and its schema has zero business
meaning — sharing the app's database would just create an unrelated
migration-ownership conflict.

**Airflow hosting: self-hosted, not a managed service (MWAA / Cloud
Composer / Astronomer) — for now.** Self-hosted is what makes the
`SSHOperator` plan above work without a separate VPC-peering/managed-
network-path project first (a managed Airflow's workers aren't guaranteed
network-reachable to the app host by default). If this ever moves to a
managed Airflow, revisit the `SSHOperator` decision — those workers may need
`DockerOperator`/`KubernetesPodOperator` instead.

**Housekeeping split out, not carried over coincidentally.** The
refresh-token-denylist cleanup rode the same APScheduler timer as the
assessment sweep purely by accident of how it was originally wired. It gets
its own script (`app/scripts/purge_expired_revoked_tokens.py`) and its own
independent Airflow task (`purge_expired_tokens_task`, no dependency edge to
the sweep's two tasks) rather than silently preserving that coupling.

## Not provisional

The technology choices above (FastStream, `SSHOperator`, LocalExecutor,
separate metadata DB, self-hosted-for-now) are settled. What's provisional
is the *cutover timing* — see the plan document's "What's remaining"
section: `app/core/scheduler.py`/APScheduler stays the live mechanism until
Airflow has actually been verified running (blocked, as of this writing, on
a host disk-space/Docker-storage problem, not on any of these decisions).
