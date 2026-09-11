"""Layer-1/layer-2 assessment sweep DAG (review D06 / the RabbitMQ+Airflow
migration — see docs/plans/rabbitmq-airflow-migration.md, Phase 3).

Replaces `app/core/scheduler.py`'s in-process APScheduler timer. Each task
SSHes to the app host and runs the sweep through the app's own Docker
Compose stack — Airflow's Python environment never needs the app's
dependencies or even its Python version (decision 2b/2d in the plan above).

**Setup required before this DAG can run** (not done by this file):
1. An Airflow Connection named `APP_HOST_SSH_CONN_ID` below (type `ssh`),
   whose key is scoped to nothing but the `docker compose run --rm app ...`
   commands this DAG issues (`authorized_keys` `command=` pinning, or an
   equivalently locked-down deploy user) — see the plan's 2b.
2. An Airflow Variable `ats_app_dir` — the absolute path to this repo's
   checkout on the app host (defaults to `/opt/ats-fastapi` if unset).
3. `apache-airflow-providers-ssh` installed in Airflow's own environment
   (already wired into `docker-compose.airflow.yml`'s
   `_PIP_ADDITIONAL_REQUIREMENTS` for local dev).

This module has not yet been import-verified against a real Airflow
install — see the plan doc's Phase 3 notes for why (blocked on a host disk/
Docker problem at the time this was written) and re-check before relying on
it.
"""

from datetime import datetime, timedelta

from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.sdk import DAG

APP_HOST_SSH_CONN_ID = "app_host_ssh"

# `{{ var.value.get(...) }}` (Jinja, resolved at task-run time, not DAG-parse
# time) — the safe way to read an Airflow Variable from inside a templated
# field; calling Variable.get() directly at module import time has a known
# issue with `airflow dags reserialize` (see the plan doc's research notes).
# Deliberately a plain string, not an f-string/`.format()` template — Jinja's
# `{{ }}` and `str.format()`'s `{{ }}` escaping collide, so the two task
# commands below are written out in full rather than built from one shared
# template.
_APP_DIR = "{{ var.value.get('ats_app_dir', '/opt/ats-fastapi') }}"


def _sweep_command(task_name: str) -> str:
    return (
        f"cd {_APP_DIR} && "
        f"docker compose run --rm app uv run ats-cli sweep {task_name} --json"
    )


with DAG(
    dag_id="assessment_sweep",
    description=(
        "Expire overdue assessment attempts, then disqualify overdue "
        "applications that aren't fully assessed — see "
        "docs/decisions/D06-scheduler-ownership.md."
    ),
    schedule="*/15 * * * *",  # matches SCHEDULER_INTERVAL_MINUTES's old default
    start_date=datetime(2026, 1, 1),  # revisit before this DAG is actually enabled
    catchup=False,
    max_active_runs=1,  # belt-and-suspenders alongside sweep_advisory_lock
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["assessments", "sweep"],
) as dag:
    expire_attempts_task = SSHOperator(
        task_id="expire_attempts",
        ssh_conn_id=APP_HOST_SSH_CONN_ID,
        command=_sweep_command("expire-attempts"),
        cmd_timeout=300,
    )

    disqualify_applications_task = SSHOperator(
        task_id="disqualify_applications",
        ssh_conn_id=APP_HOST_SSH_CONN_ID,
        command=_sweep_command("disqualify-applications"),
        cmd_timeout=300,
    )

    # A just-expired attempt must be visible to the disqualification check
    # running right after it, in the same tick — same ordering
    # app/core/scheduler.py's docstring and
    # app/scripts/disqualify_overdue_applications.py's module comment
    # already document.
    expire_attempts_task >> disqualify_applications_task

    # Housekeeping, not part of the sweep ordering above — decision 2f in the
    # plan doc: it rode the same APScheduler timer purely by coincidence
    # before, so it gets its own independent task here rather than being
    # wedged into the expire/disqualify dependency chain it has nothing to
    # do with.
    purge_expired_tokens_task = SSHOperator(
        task_id="purge_expired_tokens",
        ssh_conn_id=APP_HOST_SSH_CONN_ID,
        command=_sweep_command("purge-expired-tokens"),
        cmd_timeout=120,
    )
