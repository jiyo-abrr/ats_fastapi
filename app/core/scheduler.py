import logging
import time
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.sweep_lock import sweep_advisory_lock
from app.core.unit_of_work import UnitOfWork
from app.domains.auth.repository import RevokedRefreshTokenRepository
from app.scripts.disqualify_overdue_applications import (
    run as disqualify_overdue_applications,
)
from app.scripts.expire_overdue_assessment_attempts import (
    run as expire_overdue_assessment_attempts,
)

# This file is the ONLY thing that gets deleted when the cron responsibility
# moves to Airflow — see docs/plans/assessments-domain.md. It contains zero
# business logic: both jobs' actual work lives in the standalone scripts
# under app/scripts/, which map 1:1 onto what will become two Airflow tasks
# (expire_attempts_task >> disqualify_applications_task). This is purely
# "call those same two things on a timer" for the pre-Airflow interim.
logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def _run_periodic_jobs() -> None:
    started = time.monotonic()
    ran = False
    # One advisory lock covers both jobs — the standalone scripts take the same
    # lock (see app/core/sweep_lock.py), so a manual run and a scheduled tick
    # can't overlap.
    try:
        async with AsyncSessionLocal() as db, sweep_advisory_lock(db) as acquired:
            if not acquired:
                return
            ran = True
            # Order matters: a just-expired attempt must be visible to the
            # disqualification check running right after it, in the same tick.
            await expire_overdue_assessment_attempts()
            await disqualify_overdue_applications()

        # Housekeeping — drop denylist rows for refresh tokens that have already
        # expired (review F21). Cheap, no lock needed, its own session.
        async with AsyncSessionLocal() as db:
            uow = UnitOfWork(db)
            removed = await RevokedRefreshTokenRepository(db).delete_expired(
                datetime.now(UTC)
            )
            await uow.commit()
            if removed:
                logger.info("purged %s expired revoked-token row(s)", removed)
    except Exception:
        logger.exception(
            "periodic sweep FAILED after %.2fs", time.monotonic() - started
        )
        raise
    else:
        if ran:
            logger.info("periodic sweep ok in %.2fs", time.monotonic() - started)


def start_scheduler() -> None:
    if not settings.scheduler_enabled:
        logger.info("scheduler disabled (SCHEDULER_ENABLED is not set)")
        return
    _scheduler.add_job(
        _run_periodic_jobs,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id="assessment_periodic_jobs",
    )
    _scheduler.start()
    logger.info("scheduler started (every %s min)", settings.scheduler_interval_minutes)


def shutdown_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown()
