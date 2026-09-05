import uuid

from fastapi import APIRouter, Depends, status

from app.domains.positions.dependencies import get_position_service
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
def create_position(
    payload: PositionCreate,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return service.create(**payload.model_dump())


@router.get("", response_model=list[PositionOut])
def list_positions(
    service: PositionService = Depends(get_position_service),
) -> list[PositionOut]:
    return service.list()


@router.get("/{position_id}", response_model=PositionOut)
def get_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return service.get(position_id)


@router.put("/{position_id}", response_model=PositionOut, dependencies=[_manage_jobs])
def update_position(
    position_id: uuid.UUID,
    payload: PositionUpdate,
    service: PositionService = Depends(get_position_service),
) -> PositionOut:
    return service.update(position_id, **payload.model_dump())


@router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
def delete_position(
    position_id: uuid.UUID,
    service: PositionService = Depends(get_position_service),
) -> None:
    service.delete(position_id)
