# D06 — Scheduler ownership

**Question (review F16):** every web-process lifespan started its own
APScheduler. With multiple workers/replicas each process runs the same sweep,
compounding the transition-race risk (F02). No enable/disable, no leader
election, no distributed lock.

**Decision:**

1. **Now (done):** the scheduler is opt-in via `SCHEDULER_ENABLED` (default
   `false`, so a multi-worker deploy is safe by default). Set it on exactly one
   process — a single dev run, or one designated worker.
2. **Now (done):** each tick takes a Postgres advisory lock
   (`pg_try_advisory_lock`); a second enabled process (rolling deploy overlap,
   misconfig) logs and skips rather than double-running.
3. **Follow-up:** when moving to Airflow, delete `app/core/scheduler.py`; the
   two `app/scripts/*` entry points become two Airflow tasks
   (`expire_attempts_task >> disqualify_applications_task`). The advisory lock
   stays relevant if any manual run overlaps a scheduled one.

**Why not full leader election now:** the flag + advisory lock covers the
realistic failure modes for a small deployment. Consul/etcd-style election is
disproportionate.

**Not provisional** for the flag + lock; the Airflow move is the known end
state.
