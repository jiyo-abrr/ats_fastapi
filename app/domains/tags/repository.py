import uuid

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domains.tags import entities
from app.domains.tags.models import Tag as TagModel


class TagRepository(BaseRepository[TagModel, entities.Tag, uuid.UUID]):
    model = TagModel

    async def _to_entity(self, obj: TagModel) -> entities.Tag:
        return entities.Tag(id=obj.id, name=obj.name, description=obj.description)

    def _to_model(self, entity: entities.Tag) -> TagModel:
        return TagModel(id=entity.id, name=entity.name, description=entity.description)

    async def get_by_name(self, name: str) -> entities.Tag | None:
        result = await self.db.execute(select(TagModel).where(TagModel.name == name))
        obj = result.scalar_one_or_none()
        return await self._to_entity(obj) if obj is not None else None

    async def update(self, entity: entities.Tag) -> None:
        obj = await self.db.get(TagModel, entity.id)
        if obj is None:
            return
        obj.name = entity.name
        obj.description = entity.description
