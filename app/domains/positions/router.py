import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.positions.dependencies import (
    get_position_repository,
    get_position_service,
)
from app.domains.positions.models import Position as PositionModel
from app.domains.positions.repository import PositionRepository
from app.domains.positions.schemas import PositionCreate, PositionOut, PositionUpdate
from app.domains.positions.service import PositionService
from app.domains.rbac.dependencies import require_permission

_manage_jobs = Depends(require_permission("manage_jobs"))

router = APIRouter(prefix="/positions", tags=["positions"])


@router.post(
    "",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage_jobs],
)
async def create_position(
    payload: PositionCreate,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return await service.create(**payload.model_dump())


@router.get("", response_model=Page[PositionOut])
async def list_positions(
    query=QueryBuilder(PositionModel),
    db: AsyncSession = Depends(get_db),
    repo: PositionRepository = Depends(get_position_repository),
) -> Page[PositionOut]:
    return await apaginate(db, query, transformer=repo.map_many)


@router.get("/{position_id}", response_model=PositionOut)
async def get_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return await service.get(position_id)


@router.put("/{position_id}", response_model=PositionOut, dependencies=[_manage_jobs])
async def update_position(
    position_id: uuid.UUID,
    payload: PositionUpdate,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return await service.update(position_id, **payload.model_dump())


@router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
async def delete_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
) -> None:
    await service.delete(position_id)
