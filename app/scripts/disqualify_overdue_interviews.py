import asyncio
import logging
import selectors
from datetime import UTC, datetime

from app.core.database import AsyncSessionLocal
from app.core.sweep_lock import sweep_advisory_lock
from app.core.unit_of_work import UnitOfWork
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.service import ApplicationService
from app.domains.interviews.repository import InterviewRepository
from app.domains.job_posts.repository import JobPostRepository
from app.domains.rbac.repository import RolePermissionRepository

# Independent of the assessment sweep (expire-attempts / disqualify-
# applications) — this is the `interview`-stage equivalent, gated on
# Application.interview_booking_deadline rather than assessment_deadline, and
# on whether a slot has been picked rather than on assessment completion. See
# Application.interview_booking_deadline's docstring and the applications
# router's update_status handler, which sets that deadline.
#
# InterviewRepository.list_overdue_interview_ids() already excludes anyone
# who booked a slot (however long ago), so — unlike the assessment sweep,
# which rescans "fully assessed but still applied" rows until a human moves
# them — nobody sits here as a permanent, ever-rescanned backlog once handled.

logger = logging.getLogger(__name__)

_BATCH_SIZE = 200
_MAX_BATCHES_PER_TICK = 25  # hard cap: at most 5,000 applications per tick


async def run() -> dict[str, int]:
    """The sweep itself, with no lock — the scheduler composes this under its
    own shared advisory lock. Returns `{"checked": ..., "disqualified": ...}`
    (used by `app.cli`'s `--json` output; the standalone `__main__` entry
    point below still just prints and discards it)."""
    async with AsyncSessionLocal() as db:
        uow = UnitOfWork(db)
        applications = ApplicationRepository(db)
        interviews = InterviewRepository(db)
        application_service = ApplicationService(
            applications, JobPostRepository(db), RolePermissionRepository(db), uow
        )

        now = datetime.now(UTC)
        disqualified_count = 0
        for _ in range(_MAX_BATCHES_PER_TICK):
            batch = await interviews.list_overdue_interview_ids(now, limit=_BATCH_SIZE)
            if not batch:
                break
            for application_id in batch:
                await application_service.disqualify_interview_overdue(application_id)
                disqualified_count += 1
            if len(batch) < _BATCH_SIZE:
                break
        else:
            logger.warning(
                "interview disqualify sweep hit the %s-batch cap (%s "
                "applications) — there may still be a backlog; it will "
                "continue next tick",
                _MAX_BATCHES_PER_TICK,
                _MAX_BATCHES_PER_TICK * _BATCH_SIZE,
            )

        print(f"Disqualified {disqualified_count} overdue-interview application(s)")
        return {"disqualified": disqualified_count}


async def main() -> dict[str, int] | None:
    """CLI / task-runner entry point — takes the shared sweep lock so a manual
    run can't collide with a scheduler tick or the other sweep scripts.
    Returns `None` if another run already held the lock (skipped this tick)."""
    async with AsyncSessionLocal() as lock_db, sweep_advisory_lock(lock_db) as acquired:
        if not acquired:
            return None
        return await run()


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
