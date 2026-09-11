import asyncio
import logging
import selectors
from datetime import UTC, datetime

from app.core.database import AsyncSessionLocal
from app.core.sweep_lock import sweep_advisory_lock
from app.core.unit_of_work import UnitOfWork
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.service import ApplicationService
from app.domains.assessments.attempts.repository import AssessmentAttemptRepository
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)
from app.domains.job_posts.repository import JobPostRepository
from app.domains.rbac.repository import RolePermissionRepository

# Layer-1 sweep — see docs/plans/assessments-domain.md. Run *after*
# expire_overdue_assessment_attempts in the same tick so a just-expired
# attempt is already reflected here. This is the one place in the codebase
# that knows about both `assessments` and `applications` for this purpose —
# neither domain's service depends on the other (that would be a cycle,
# since assessments already depends on applications for application_id FKs).

logger = logging.getLogger(__name__)

# Bounds one tick's work (review F16) — a backlog bigger than this is worked
# off over several ticks (every 15 min by default) rather than in one very
# long-running sweep holding the advisory lock the whole time.
_BATCH_SIZE = 200
_MAX_BATCHES_PER_TICK = 25  # hard cap: at most 5,000 applications per tick


async def run() -> None:
    """The sweep itself, with no lock — the scheduler composes this under one
    shared advisory lock together with the expiry sweep."""
    async with AsyncSessionLocal() as db:
        uow = UnitOfWork(db)
        applications = ApplicationRepository(db)
        job_posts = JobPostRepository(db)

        assessment_service = AssessmentService(
            AssessmentAttemptRepository(db),
            PreAssessmentTemplateRepository(db),
            CultureFitTemplateRepository(db),
            TechnicalAssessmentTemplateRepository(db),
            job_posts,
            applications,
            uow,
        )
        application_service = ApplicationService(
            applications, job_posts, RolePermissionRepository(db), uow
        )

        now = datetime.now(UTC)
        checked = 0
        disqualified_count = 0
        for _ in range(_MAX_BATCHES_PER_TICK):
            batch = await applications.list_overdue_applied(now, limit=_BATCH_SIZE)
            if not batch:
                break
            for application in batch:
                checked += 1
                if not await assessment_service.is_application_fully_assessed(
                    application.id
                ):
                    await application_service.disqualify(application.id)
                    disqualified_count += 1
            if len(batch) < _BATCH_SIZE:
                break
        else:
            logger.warning(
                "disqualify sweep hit the %s-batch cap (%s applications) — "
                "there may still be a backlog; it will continue next tick",
                _MAX_BATCHES_PER_TICK,
                _MAX_BATCHES_PER_TICK * _BATCH_SIZE,
            )

        print(
            f"Checked {checked} overdue application(s), "
            f"disqualified {disqualified_count}"
        )


async def main() -> None:
    """CLI / task-runner entry point — takes the shared sweep lock so a manual
    run can't collide with a scheduler tick or the other script."""
    async with AsyncSessionLocal() as lock_db, sweep_advisory_lock(lock_db) as acquired:
        if not acquired:
            return
        await run()


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
