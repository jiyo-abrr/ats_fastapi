import uuid

from fastapi import APIRouter, Depends, status

from app.domains.rbac.dependencies import require_permission
from app.domains.tags.dependencies import get_tag_service
from app.domains.tags.schemas import TagCreate, TagOut, TagUpdate
from app.domains.tags.service import TagService

_manage_jobs = Depends(require_permission("manage_jobs"))

router = APIRouter(prefix="/tags", tags=["tags"])


@router.post(
    "",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage_jobs],
)
def create_tag(
    payload: TagCreate, service: TagService = Depends(get_tag_service)
) -> TagOut:
    return service.create(**payload.model_dump())


@router.get("", response_model=list[TagOut])
def list_tags(service: TagService = Depends(get_tag_service)) -> list[TagOut]:
    return service.list()


@router.get("/{tag_id}", response_model=TagOut)
def get_tag(
    tag_id: uuid.UUID, service: TagService = Depends(get_tag_service)
) -> TagOut:
    return service.get(tag_id)


@router.put("/{tag_id}", response_model=TagOut, dependencies=[_manage_jobs])
def update_tag(
    tag_id: uuid.UUID,
    payload: TagUpdate,
    service: TagService = Depends(get_tag_service),
) -> TagOut:
    return service.update(tag_id, **payload.model_dump())


@router.delete(
    "/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage_jobs]
)
def delete_tag(
    tag_id: uuid.UUID, service: TagService = Depends(get_tag_service)
) -> None:
    service.delete(tag_id)
