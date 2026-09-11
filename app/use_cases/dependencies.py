from fastapi import Depends

from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.applications.dependencies import (
    get_application_repository,
    get_application_service,
)
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.service import ApplicationService
from app.domains.assessments.attempts.dependencies import get_assessment_service
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.job_posts.dependencies import get_job_post_service
from app.domains.job_posts.service import JobPostService
from app.use_cases.apply_to_job import ApplyToJob
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
