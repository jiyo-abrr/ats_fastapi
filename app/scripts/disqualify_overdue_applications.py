import asyncio
import selectors
from datetime import UTC, datetime

from app.core.database import AsyncSessionLocal
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


async def main() -> None:
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

        overdue = await applications.list_overdue_applied(datetime.now(UTC))
        disqualified_count = 0
        for application in overdue:
            if not await assessment_service.is_application_fully_assessed(
                application.id
            ):
                await application_service.disqualify(application.id)
                disqualified_count += 1

        print(
            f"Checked {len(overdue)} overdue application(s), "
            f"disqualified {disqualified_count}"
        )


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
