import uuid

from fastapi import APIRouter, Depends, status

from app.domains.job_posts.dependencies import get_job_post_service
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
def create_job_post(
    payload: JobPostCreate,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.create(**payload.model_dump())


@router.get("", response_model=list[JobPostOut])
def list_job_posts(
    service: JobPostService = Depends(get_job_post_service),
) -> list[JobPostOut]:
    return service.list()


@router.get("/{job_post_id}", response_model=JobPostOut)
def get_job_post(
    job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.get(job_post_id)


@router.put("/{job_post_id}", response_model=JobPostOut, dependencies=[_manage_jobs])
def update_job_post(
    job_post_id: uuid.UUID,
    payload: JobPostUpdate,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.update(job_post_id, **payload.model_dump())


@router.delete(
    "/{job_post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
def delete_job_post(
    job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> None:
    service.delete(job_post_id)


@router.post(
    "/{job_post_id}/tags/{tag_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
def add_job_post_tag(
    job_post_id: uuid.UUID,
    tag_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.add_tag(job_post_id, tag_id)


@router.delete(
    "/{job_post_id}/tags/{tag_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
def remove_job_post_tag(
    job_post_id: uuid.UUID,
    tag_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.remove_tag(job_post_id, tag_id)


@router.post(
    "/{job_post_id}/exclusions/{excluded_job_post_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
def add_job_post_exclusion(
    job_post_id: uuid.UUID,
    excluded_job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.add_exclusion(job_post_id, excluded_job_post_id)


@router.delete(
    "/{job_post_id}/exclusions/{excluded_job_post_id}",
    response_model=JobPostOut,
    dependencies=[_manage_jobs],
)
def remove_job_post_exclusion(
    job_post_id: uuid.UUID,
    excluded_job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.remove_exclusion(job_post_id, excluded_job_post_id)
