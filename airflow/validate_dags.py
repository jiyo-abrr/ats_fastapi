"""Import-and-shape check for every DAG under `airflow/dags/` — the
automated version of the manual verification described in
`docs/plans/rabbitmq-airflow-migration.md`'s "What's remaining" section.

Deliberately **not** a pytest test in this repo's own suite: Airflow must
never become a dependency of the FastAPI app itself (decision 2b/2d in that
plan) — this only ever runs inside a real Airflow environment, e.g.:

    docker run --rm \\
      -v "$(pwd)/airflow/dags:/opt/airflow/dags:ro" \\
      -v "$(pwd)/airflow/validate_dags.py:/opt/airflow/validate_dags.py:ro" \\
      -e _PIP_ADDITIONAL_REQUIREMENTS=apache-airflow-providers-ssh \\
      apache/airflow:3.2.0-python3.12 \\
      bash -c "python /opt/airflow/validate_dags.py"

Wired into CI as its own job (`.github/workflows/ci.yml`'s
`airflow-dag-validation`) — independent of the `lint`/`test` jobs, no
running Airflow scheduler/webserver needed, matching the design this plan
always intended for this check.
"""

import sys

sys.path.insert(0, "/opt/airflow/dags")

import assessment_sweep_dag as m  # noqa: E402

errors: list[str] = []

dag = m.dag
if dag.dag_id != "assessment_sweep":
    errors.append(f"unexpected dag_id: {dag.dag_id!r}")

task_ids = {t.task_id for t in dag.tasks}
expected_task_ids = {
    "expire_attempts",
    "disqualify_applications",
    "purge_expired_tokens",
}
if task_ids != expected_task_ids:
    errors.append(f"unexpected task set: {task_ids!r} (expected {expected_task_ids!r})")
else:
    expire = dag.get_task("expire_attempts")
    disqualify = dag.get_task("disqualify_applications")
    purge = dag.get_task("purge_expired_tokens")

    if expire.downstream_task_ids != {"disqualify_applications"}:
        errors.append(
            f"expire_attempts.downstream_task_ids wrong: {expire.downstream_task_ids!r}"
        )
    if disqualify.upstream_task_ids != {"expire_attempts"}:
        errors.append(
            "disqualify_applications.upstream_task_ids wrong: "
            f"{disqualify.upstream_task_ids!r}"
        )
    if purge.upstream_task_ids or purge.downstream_task_ids:
        errors.append(
            "purge_expired_tokens should have no dependency edges (got "
            f"upstream={purge.upstream_task_ids!r} "
            f"downstream={purge.downstream_task_ids!r})"
        )

if errors:
    print("DAG VALIDATION FAILED:")
    for error in errors:
        print(" -", error)
    sys.exit(1)

print("DAG_VALIDATION_OK")
