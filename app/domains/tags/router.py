import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.rbac.dependencies import require_permission
from app.domains.tags.dependencies import get_tag_repository, get_tag_service
from app.domains.tags.models import Tag as TagModel
from app.domains.tags.repository import TagRepository
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
async def create_tag(
    payload: TagCreate, service: TagService = Depends(get_tag_service)
) -> TagOut:
    return await service.create(**payload.model_dump())


@router.get("", response_model=Page[TagOut])
async def list_tags(
    query=QueryBuilder(TagModel),
    db: AsyncSession = Depends(get_db),
    repo: TagRepository = Depends(get_tag_repository),
) -> Page[TagOut]:
    return await apaginate(db, query, transformer=repo.map_many)


@router.get("/{tag_id}", response_model=TagOut)
async def get_tag(
    tag_id: uuid.UUID, service: TagService = Depends(get_tag_service)
) -> TagOut:
    return await service.get(tag_id)


@router.put("/{tag_id}", response_model=TagOut, dependencies=[_manage_jobs])
async def update_tag(
    tag_id: uuid.UUID,
    payload: TagUpdate,
    service: TagService = Depends(get_tag_service),
) -> TagOut:
    return await service.update(tag_id, **payload.model_dump())


@router.delete(
    "/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage_jobs]
)
async def delete_tag(
    tag_id: uuid.UUID, service: TagService = Depends(get_tag_service)
) -> None:
    await service.delete(tag_id)
