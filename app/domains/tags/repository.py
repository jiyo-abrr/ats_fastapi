import uuid

from app.core.repository import BaseRepository
from app.domains.tags import entities
from app.domains.tags.models import Tag as TagModel


class TagRepository(BaseRepository[TagModel, entities.Tag, uuid.UUID]):
    model = TagModel

    def _to_entity(self, obj: TagModel) -> entities.Tag:
        return entities.Tag(id=obj.id, name=obj.name, description=obj.description)

    def _to_model(self, entity: entities.Tag) -> TagModel:
        return TagModel(id=entity.id, name=entity.name, description=entity.description)

    def get_by_name(self, name: str) -> entities.Tag | None:
        obj = self.db.query(TagModel).filter(TagModel.name == name).first()
        return self._to_entity(obj) if obj is not None else None

    def update(self, entity: entities.Tag) -> None:
        obj = self.db.get(TagModel, entity.id)
        if obj is None:
            return
        obj.name = entity.name
        obj.description = entity.description
