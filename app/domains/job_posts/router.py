import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.domains.job_posts.dependencies import (
    get_job_post_repository,
    get_job_post_service,
)
from app.domains.job_posts.enums import JobPostStatus
from app.domains.job_posts.models import JobPost as JobPostModel
from app.domains.job_posts.repository import JobPostRepository
from app.domains.job_posts.schemas import (
    JobPostCreate,
    JobPostOut,
    JobPostStatsOut,
    JobPostUpdate,
)
from app.domains.job_posts.service import JobPostService
from app.domains.rbac.dependencies import require_permission
from app.use_cases.delete_job_post import DeleteJobPost
from app.use_cases.dependencies import get_delete_job_post

_manage_jobs = Depends(require_permission("manage_jobs"))

router = APIRouter(prefix="/job-posts", tags=["job-posts"])


@router.post(
    "",
    response_model=JobPostOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage_jobs],
)
async def create_job_post(
    payload: JobPostCreate,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.create(**payload.model_dump())


def _eager(query):
    # Eager-load company_address/position so repo.map_many's _to_entity call
    # doesn't trigger a MissingGreenlet lazy-load on the paginated rows.
    return query.options(
        selectinload(JobPostModel.company_address),
        selectinload(JobPostModel.position),
    )


@router.get("", response_model=Page[JobPostOut])
async def list_job_posts(
    query=QueryBuilder(JobPostModel),
    db: AsyncSession = Depends(get_db),
    repo: JobPostRepository = Depends(get_job_post_repository),
) -> Page[JobPostOut]:
    # Public listing — published only (docs/decisions/D01). Staff use
    # GET /job-posts/manage for drafts and closed posts.
    query = _eager(query).where(JobPostModel.status == JobPostStatus.PUBLISHED)
    return await apaginate(db, query, transformer=repo.map_many)


@router.get("/manage", response_model=Page[JobPostOut], dependencies=[_manage_jobs])
async def list_job_posts_for_management(
    query=QueryBuilder(JobPostModel),
    db: AsyncSession = Depends(get_db),
    repo: JobPostRepository = Depends(get_job_post_repository),
) -> Page[JobPostOut]:
    """Every job post regardless of status — for HR/admin."""
    return await apaginate(db, _eager(query), transformer=repo.map_many)


@router.get("/stats", response_model=JobPostStatsOut, dependencies=[_manage_jobs])
async def job_post_stats(
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostStatsOut:
    return JobPostStatsOut(**await service.stats())


@router.get(
    "/manage/{job_post_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def get_job_post_for_management(
    job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.get(job_post_id)


@router.get("/{job_post_id}", response_model=JobPostOut)
async def get_job_post(
    job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    # Public — a draft or closed post 404s (docs/decisions/D01).
    return await service.get_public(job_post_id)


@router.put("/{job_post_id}", response_model=JobPostOut, dependencies=[_manage_jobs])
async def update_job_post(
    job_post_id: uuid.UUID,
    payload: JobPostUpdate,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.update(job_post_id, **payload.model_dump())


@router.delete(
    "/{job_post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
async def delete_job_post(
    job_post_id: uuid.UUID,
    delete_use_case: DeleteJobPost = Depends(get_delete_job_post),
) -> None:
    # 409 if the post has applications — those records outlive the requisition
    # (docs/decisions/D04). Close the post instead to stop new applications.
    await delete_use_case.execute(job_post_id)


@router.post(
    "/{job_post_id}/tags/{tag_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def add_job_post_tag(
    job_post_id: uuid.UUID,
    tag_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.add_tag(job_post_id, tag_id)


@router.delete(
    "/{job_post_id}/tags/{tag_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def remove_job_post_tag(
    job_post_id: uuid.UUID,
    tag_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.remove_tag(job_post_id, tag_id)


@router.post(
    "/{job_post_id}/exclusions/{excluded_job_post_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def add_job_post_exclusion(
    job_post_id: uuid.UUID,
    excluded_job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.add_exclusion(job_post_id, excluded_job_post_id)


@router.delete(
    "/{job_post_id}/exclusions/{excluded_job_post_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def remove_job_post_exclusion(
    job_post_id: uuid.UUID,
    excluded_job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.remove_exclusion(job_post_id, excluded_job_post_id)


@router.post(
    "/{job_post_id}/pre-assessment-templates/{template_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def add_job_post_pre_assessment_template(
    job_post_id: uuid.UUID,
    template_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.add_pre_assessment_template(job_post_id, template_id)


@router.delete(
    "/{job_post_id}/pre-assessment-templates/{template_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def remove_job_post_pre_assessment_template(
    job_post_id: uuid.UUID,
    template_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.remove_pre_assessment_template(job_post_id)


@router.post(
    "/{job_post_id}/culture-fit-templates/{template_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def add_job_post_culture_fit_template(
    job_post_id: uuid.UUID,
    template_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.add_culture_fit_template(job_post_id, template_id)


@router.delete(
    "/{job_post_id}/culture-fit-templates/{template_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def remove_job_post_culture_fit_template(
    job_post_id: uuid.UUID,
    template_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.remove_culture_fit_template(job_post_id)


@router.post(
    "/{job_post_id}/technical-assessment-templates/{template_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def add_job_post_technical_assessment_template(
    job_post_id: uuid.UUID,
    template_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.add_technical_assessment_template(job_post_id, template_id)


@router.delete(
    "/{job_post_id}/technical-assessment-templates/{template_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
async def remove_job_post_technical_assessment_template(
    job_post_id: uuid.UUID,
    template_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.remove_technical_assessment_template(job_post_id)
