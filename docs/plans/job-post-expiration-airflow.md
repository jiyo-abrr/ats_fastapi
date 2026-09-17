# Plan — auto-close expired job posts via Airflow

Status: **not started — planning only.** Piggybacks on the sweep
infrastructure already built in
[docs/plans/rabbitmq-airflow-migration.md](rabbitmq-airflow-migration.md)
(the `assessment_sweep` DAG, `SSHOperator` → app host → `ats-cli`) rather
than introducing a new mechanism.

## 1. What this is

`job_posts.expires_at` (added for the recruitment analytics report —
`published_at`/`closed_at`/`expires_at`, migration `e5f6a7b8c9d0`) is
currently **informational only**: HR can set a target end date, but nothing
in the app enforces it. A published post past its `expires_at` stays
`published` until someone closes it by hand.

The decision (confirmed with the user): don't build in-app scheduling for
this. Add it as a periodic check in the same Airflow instance already
planned for the assessment sweep, not a new APScheduler/Celery/cron
mechanism inside `ats_fastapi`.

## 2. Shape of the change, following the existing sweep pattern exactly

1. **A new script**, `app/scripts/close_expired_job_posts.py`, matching the
   shape of `expire_overdue_assessment_attempts.py` /
   `disqualify_overdue_applications.py`: an async `main()` that queries
   `job_posts` for `status = 'published' AND expires_at IS NOT NULL AND
   expires_at <= now()`, and calls the existing `JobPostService.update(...)`
   (or the repository directly) per row with `status="closed"` — reusing
   `JobPostService`'s own `closed_at` stamping logic
   (`service.py`'s `update()` already sets `closed_at = existing.closed_at
   or datetime.now(UTC)` whenever status becomes `closed`), so this script
   doesn't duplicate that logic.
2. **A new Typer subcommand**, `ats-cli sweep close-expired-job-posts
   --json`, in `app/cli.py`, mirroring `expire-attempts` /
   `disqualify-applications` — same `_run_sync` wrapper, same `--json`
   output shape (`{"closed": N}`).
3. **A new task in the existing `assessment_sweep` DAG**
   (`airflow/dags/assessment_sweep_dag.py`), or a second small DAG if its
   schedule should differ from the assessment sweep's 15-minute interval
   (job-post expiration is date-only, so hourly or even daily is probably
   enough — no need to check every 15 minutes). Uses the same
   `_sweep_command()` helper and `SSHOperator` pattern; no dependency edge
   to the existing `expire_attempts`/`disqualify_applications` tasks, since
   it's unrelated business logic (same reasoning as the refresh-token-
   denylist cleanup task, decision 2f in the migration plan).
4. **No new Airflow infrastructure** — reuses `APP_HOST_SSH_CONN_ID`, the
   `ats_app_dir` Variable, and the already-planned self-hosted Airflow
   instance. This is purely "one more task," not a new provisioning
   surface.

## 3. Open questions to settle before implementing

- **Schedule:** same DAG/15-min cadence, or its own DAG with a coarser
  schedule (hourly/daily)? Leaning toward a separate, coarser schedule —
  there's no urgency to close a post within minutes of its target date.
- **Should closing be silent, or should it notify HR** (e.g. the post owner)
  that it auto-closed? Out of scope for the first cut — start with silent
  auto-close, matching how the assessment sweep's disqualifications are
  silent today; revisit if HR needs a heads-up.
- **Does an auto-closed post need to be distinguishable from a manually
  closed one** for the recruitment report's recommendation engine
  (`_recommend()` in `app/domains/analytics/repository.py`)? Not currently
  needed — `_recommend()` only looks at `published` posts, so a closed post
  (auto or manual) simply stops getting a recommendation either way.

## 4. Not started

This is deliberately just a plan. No script, CLI command, or DAG task exists
yet for this — do not assume `close-expired-job-posts` is wired up anywhere
until this doc is updated to say so.
