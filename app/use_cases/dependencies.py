from fastapi import Depends

from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.applications.dependencies import (
    get_application_repository,
    get_application_service,
)
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.service import ApplicationService
from app.domains.assessments.attempts.dependencies import (
    get_assessment_attempt_repository,
    get_assessment_service,
)
from app.domains.assessments.attempts.enums import TemplateType
from app.domains.assessments.attempts.repository import AssessmentAttemptRepository
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.assessments.culture_fit_templates.dependencies import (
    get_culture_fit_template_service,
)
from app.domains.assessments.culture_fit_templates.service import (
    CultureFitTemplateService,
)
from app.domains.assessments.pre_assessment_templates.dependencies import (
    get_pre_assessment_template_service,
)
from app.domains.assessments.pre_assessment_templates.service import (
    PreAssessmentTemplateService,
)
from app.domains.assessments.technical_assessment_templates.dependencies import (
    get_technical_assessment_template_service,
)
from app.domains.assessments.technical_assessment_templates.service import (
    TechnicalAssessmentTemplateService,
)
from app.domains.job_posts.dependencies import get_job_post_service
from app.domains.job_posts.service import JobPostService
from app.use_cases.apply_to_job import ApplyToJob
from app.use_cases.delete_assessment_template import DeleteAssessmentTemplate
from app.use_cases.delete_job_post import DeleteJobPost


def get_apply_to_job(
    applications: ApplicationService = Depends(get_application_service),
    assessments: AssessmentService = Depends(get_assessment_service),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ApplyToJob:
    return ApplyToJob(applications, assessments, uow)


def get_delete_job_post(
    job_posts: JobPostService = Depends(get_job_post_service),
    applications: ApplicationRepository = Depends(get_application_repository),
) -> DeleteJobPost:
    return DeleteJobPost(job_posts, applications)


def get_delete_pre_assessment_template(
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
    attempts: AssessmentAttemptRepository = Depends(get_assessment_attempt_repository),
) -> DeleteAssessmentTemplate:
    return DeleteAssessmentTemplate(TemplateType.PRE_ASSESSMENT, service, attempts)


def get_delete_culture_fit_template(
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
    attempts: AssessmentAttemptRepository = Depends(get_assessment_attempt_repository),
) -> DeleteAssessmentTemplate:
    return DeleteAssessmentTemplate(TemplateType.CULTURE_FIT, service, attempts)


def get_delete_technical_assessment_template(
    service: TechnicalAssessmentTemplateService = Depends(
        get_technical_assessment_template_service
    ),
    attempts: AssessmentAttemptRepository = Depends(get_assessment_attempt_repository),
) -> DeleteAssessmentTemplate:
    return DeleteAssessmentTemplate(TemplateType.TECHNICAL, service, attempts)
