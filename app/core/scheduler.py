from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.scripts.disqualify_overdue_applications import (
    main as disqualify_overdue_applications,
)
from app.scripts.expire_overdue_assessment_attempts import (
    main as expire_overdue_assessment_attempts,
)

# This file is the ONLY thing that gets deleted when the cron responsibility
# moves to Airflow — see docs/plans/assessments-domain.md. It contains zero
# business logic: both jobs' actual work lives in the standalone scripts
# under app/scripts/, which map 1:1 onto what will become two Airflow tasks
# (expire_attempts_task >> disqualify_applications_task). This is purely
# "call those same two things on a timer" for the pre-Airflow interim.
_scheduler = AsyncIOScheduler()


async def _run_periodic_jobs() -> None:
    # Order matters: a just-expired attempt must be visible to the
    # disqualification check running right after it, in the same tick.
    await expire_overdue_assessment_attempts()
    await disqualify_overdue_applications()


def start_scheduler() -> None:
    _scheduler.add_job(
        _run_periodic_jobs,
        "interval",
        minutes=15,
        id="assessment_periodic_jobs",
    )
    _scheduler.start()


def shutdown_scheduler() -> None:
    _scheduler.shutdown()
