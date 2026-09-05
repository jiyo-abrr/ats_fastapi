from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.positions.repository import PositionRepository
from app.domains.positions.service import PositionService


def get_position_repository(db: AsyncSession = Depends(get_db)) -> PositionRepository:
    return PositionRepository(db)


def get_position_service(
    positions: PositionRepository = Depends(get_position_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PositionService:
    return PositionService(positions, uow)
