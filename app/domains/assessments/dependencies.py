from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.applications.dependencies import get_application_repository
from app.domains.applications.repository import ApplicationRepository
from app.domains.assessments.repository import AssessmentAttemptRepository
from app.domains.assessments.service import AssessmentService
from app.domains.culture_fit_templates.dependencies import (
    get_culture_fit_template_repository,
)
from app.domains.culture_fit_templates.repository import CultureFitTemplateRepository
from app.domains.job_posts.dependencies import get_job_post_repository
from app.domains.job_posts.repository import JobPostRepository
from app.domains.pre_assessment_templates.dependencies import (
    get_pre_assessment_template_repository,
)
from app.domains.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.technical_assessment_templates.dependencies import (
    get_technical_assessment_template_repository,
)
from app.domains.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)


def get_assessment_attempt_repository(
    db: AsyncSession = Depends(get_db),
) -> AssessmentAttemptRepository:
    return AssessmentAttemptRepository(db)


def get_assessment_service(
    attempts: AssessmentAttemptRepository = Depends(get_assessment_attempt_repository),
    pre_assessment_templates: PreAssessmentTemplateRepository = Depends(
        get_pre_assessment_template_repository
    ),
    culture_fit_templates: CultureFitTemplateRepository = Depends(
        get_culture_fit_template_repository
    ),
    technical_assessment_templates: TechnicalAssessmentTemplateRepository = Depends(
        get_technical_assessment_template_repository
    ),
    job_posts: JobPostRepository = Depends(get_job_post_repository),
    applications: ApplicationRepository = Depends(get_application_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> AssessmentService:
    return AssessmentService(
        attempts,
        pre_assessment_templates,
        culture_fit_templates,
        technical_assessment_templates,
        job_posts,
        applications,
        uow,
    )
