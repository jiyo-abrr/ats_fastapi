from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)
EntityType = TypeVar("EntityType")
IdType = TypeVar("IdType")


class BaseRepository(ABC, Generic[ModelType, EntityType, IdType]):
    model: type[ModelType]

    def __init__(self, db: AsyncSession):
        self.db = db

    @abstractmethod
    async def _to_entity(self, obj: ModelType) -> EntityType: ...

    @abstractmethod
    def _to_model(self, entity: EntityType) -> ModelType: ...

    async def get_by_id(self, id: IdType) -> EntityType | None:
        obj = await self.db.get(self.model, id)
        return await self._to_entity(obj) if obj is not None else None

    async def list_all(self) -> list[EntityType]:
        result = await self.db.execute(select(self.model))
        return [await self._to_entity(obj) for obj in result.scalars().all()]

    async def add(self, entity: EntityType) -> None:
        self.db.add(self._to_model(entity))

    async def delete(self, id: IdType) -> None:
        obj = await self.db.get(self.model, id)
        if obj is not None:
            await self.db.delete(obj)

    async def map_many(self, rows: Sequence[ModelType]) -> list[EntityType]:
        """Public hook for routers (e.g. the QueryBuilder/paginate transformer)
        to convert raw ORM rows into entities without reaching into _to_entity
        directly."""
        return [await self._to_entity(row) for row in rows]
