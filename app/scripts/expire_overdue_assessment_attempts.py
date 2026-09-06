import asyncio
import selectors

from app.core.database import AsyncSessionLocal
from app.core.unit_of_work import UnitOfWork
from app.domains.applications.repository import ApplicationRepository
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

# Layer-2 sweep — see docs/plans/assessments-domain.md. Independently
# runnable (uv run python -m app.scripts.expire_overdue_assessment_attempts)
# so it maps 1:1 onto a future Airflow task; app/core/scheduler.py just calls
# main() on a timer for now.


async def main() -> None:
    async with AsyncSessionLocal() as db:
        uow = UnitOfWork(db)
        service = AssessmentService(
            AssessmentAttemptRepository(db),
            PreAssessmentTemplateRepository(db),
            CultureFitTemplateRepository(db),
            TechnicalAssessmentTemplateRepository(db),
            JobPostRepository(db),
            ApplicationRepository(db),
            uow,
        )
        expired_ids = await service.expire_overdue_attempts()
        print(f"Expired {len(expired_ids)} overdue assessment attempt(s)")


if __name__ == "__main__":
    # psycopg's async driver can't run under Windows' default ProactorEventLoop
    # (asyncio.run()'s default there) — force the selector-based loop instead.
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
