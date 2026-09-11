import uuid

from sqlalchemy.exc import IntegrityError

from app.core.unit_of_work import UnitOfWork
from app.domains.positions import entities
from app.domains.positions.exceptions import PositionInUseError, PositionNotFoundError
from app.domains.positions.repository import PositionRepository


class PositionService:
    def __init__(self, positions: PositionRepository, uow: UnitOfWork):
        self.positions = positions
        self.uow = uow

    async def create(self, *, title: str, description: str | None) -> entities.Position:
        position_id = uuid.uuid4()
        await self.positions.add(
            entities.Position(id=position_id, title=title, description=description)
        )
        await self.uow.commit()
        return await self.positions.get_by_id(position_id)

    async def get(self, position_id: uuid.UUID) -> entities.Position:
        position = await self.positions.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position '{position_id}' not found")
        return position

    async def list(self) -> list[entities.Position]:
        return await self.positions.list_all()

    async def update(
        self, position_id: uuid.UUID, *, title: str, description: str | None
    ) -> entities.Position:
        await self.get(position_id)
        await self.positions.update(
            entities.Position(id=position_id, title=title, description=description)
        )
        await self.uow.commit()
        return await self.positions.get_by_id(position_id)

    async def delete(self, position_id: uuid.UUID) -> None:
        await self.get(position_id)
        await self.positions.delete(position_id)
        try:
            await self.uow.commit()
        except IntegrityError:
            await self.uow.rollback()
            raise PositionInUseError(
                f"Position '{position_id}' is still referenced by one or more job posts"
            ) from None
