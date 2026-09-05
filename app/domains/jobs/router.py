import uuid

from fastapi import APIRouter, Depends, status

from app.domains.jobs.dependencies import (
    get_company_address_service,
    get_job_post_service,
    get_position_service,
    get_tag_service,
)
from app.domains.jobs.schemas import (
    CompanyAddressCreate,
    CompanyAddressOut,
    CompanyAddressUpdate,
    JobPostCreate,
    JobPostOut,
    JobPostUpdate,
    PositionCreate,
    PositionOut,
    PositionUpdate,
    TagCreate,
    TagOut,
    TagUpdate,
)
from app.domains.jobs.service import (
    CompanyAddressService,
    JobPostService,
    PositionService,
    TagService,
)
from app.domains.rbac.dependencies import require_permission

_manage_jobs = Depends(require_permission("manage_jobs"))

company_address_router = APIRouter(
    prefix="/company-addresses", tags=["company-addresses"]
)
position_router = APIRouter(prefix="/positions", tags=["positions"])
tag_router = APIRouter(prefix="/tags", tags=["tags"])
job_post_router = APIRouter(prefix="/job-posts", tags=["job-posts"])


# --- Company addresses --- (public read, manage_jobs write)


@company_address_router.post(
    "",
    response_model=CompanyAddressOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage_jobs],
)
def create_company_address(
    payload: CompanyAddressCreate,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return service.create(**payload.model_dump())


@company_address_router.get("", response_model=list[CompanyAddressOut])
def list_company_addresses(
    service: CompanyAddressService = Depends(get_company_address_service),
) -> list[CompanyAddressOut]:
    return service.list()


@company_address_router.get("/{address_id}", response_model=CompanyAddressOut)
def get_company_address(
    address_id: uuid.UUID,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return service.get(address_id)


@company_address_router.put(
    "/{address_id}", response_model=CompanyAddressOut, dependencies=[_manage_jobs]
)
def update_company_address(
    address_id: uuid.UUID,
    payload: CompanyAddressUpdate,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return service.update(address_id, **payload.model_dump())


@company_address_router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
def delete_company_address(
    address_id: uuid.UUID,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> None:
    service.delete(address_id)


# --- Positions --- (public read, manage_jobs write)


@position_router.post(
    "",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage_jobs],
)
def create_position(
    payload: PositionCreate,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return service.create(**payload.model_dump())


@position_router.get("", response_model=list[PositionOut])
def list_positions(
    service: PositionService = Depends(get_position_service),
) -> list[PositionOut]:
    return service.list()


@position_router.get("/{position_id}", response_model=PositionOut)
def get_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return service.get(position_id)


@position_router.put(
    "/{position_id}", response_model=PositionOut, dependencies=[_manage_jobs]
)
def update_position(
    position_id: uuid.UUID,
    payload: PositionUpdate,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return service.update(position_id, **payload.model_dump())


@position_router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
def delete_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
) -> None:
    service.delete(position_id)


# --- Tags --- (public read, manage_jobs write)


@tag_router.post(
    "",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage_jobs],
)
def create_tag(
    payload: TagCreate, service: TagService = Depends(get_tag_service)
) -> TagOut:
    return service.create(**payload.model_dump())


@tag_router.get("", response_model=list[TagOut])
def list_tags(service: TagService = Depends(get_tag_service)) -> list[TagOut]:
    return service.list()


@tag_router.get("/{tag_id}", response_model=TagOut)
def get_tag(
    tag_id: uuid.UUID, service: TagService = Depends(get_tag_service)
) -> TagOut:
    return service.get(tag_id)


@tag_router.put("/{tag_id}", response_model=TagOut, dependencies=[_manage_jobs])
def update_tag(
    tag_id: uuid.UUID,
    payload: TagUpdate,
    service: TagService = Depends(get_tag_service),
) -> TagOut:
    return service.update(tag_id, **payload.model_dump())


@tag_router.delete(
    "/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage_jobs]
)
def delete_tag(
    tag_id: uuid.UUID, service: TagService = Depends(get_tag_service)
) -> None:
    service.delete(tag_id)


# --- Job posts --- (public read, manage_jobs write)


@job_post_router.post(
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


@job_post_router.get("", response_model=list[JobPostOut])
def list_job_posts(
    service: JobPostService = Depends(get_job_post_service),
) -> list[JobPostOut]:
    return service.list()


@job_post_router.get("/{job_post_id}", response_model=JobPostOut)
def get_job_post(
    job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.get(job_post_id)


@job_post_router.put(
    "/{job_post_id}", response_model=JobPostOut, dependencies=[_manage_jobs]
)
def update_job_post(
    job_post_id: uuid.UUID,
    payload: JobPostUpdate,
    service: JobPostService = Depends(get_job_post_service),
) -> JobPostOut:
    return service.update(job_post_id, **payload.model_dump())


@job_post_router.delete(
    "/{job_post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
def delete_job_post(
    job_post_id: uuid.UUID,
    service: JobPostService = Depends(get_job_post_service),
) -> None:
    service.delete(job_post_id)


@job_post_router.post(
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


@job_post_router.delete(
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


@job_post_router.post(
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


@job_post_router.delete(
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


router = APIRouter()
router.include_router(company_address_router)
router.include_router(position_router)
router.include_router(tag_router)
router.include_router(job_post_router)
