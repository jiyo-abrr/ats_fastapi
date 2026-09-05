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
from app.domains.job_posts.models import JobPost as JobPostModel
from app.domains.job_posts.repository import JobPostRepository
from app.domains.job_posts.schemas import JobPostCreate, JobPostOut, JobPostUpdate
from app.domains.job_posts.service import JobPostService
from app.domains.rbac.dependencies import require_permission

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


@router.get("", response_model=Page[JobPostOut])
async def list_job_posts(
    query=QueryBuilder(JobPostModel),
    db: AsyncSession = Depends(get_db),
    repo: JobPostRepository = Depends(get_job_post_repository),
) -> Page[JobPostOut]:
    # Eager-load company_address/position so repo.map_many's _to_entity call
    # doesn't trigger a MissingGreenlet lazy-load on the paginated rows.
    query = query.options(
        selectinload(JobPostModel.company_address),
        selectinload(JobPostModel.position),
    )
    return await apaginate(db, query, transformer=repo.map_many)


@router.get("/{job_post_id}", response_model=JobPostOut)
async def get_job_post(
    job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return await service.get(job_post_id)


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
    service: JobPostService = Depends(get_job_post_service),
) -> None:
    await service.delete(job_post_id)


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
