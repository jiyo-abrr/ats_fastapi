import uuid

from app.core.repository import BaseRepository
from app.domains.positions import entities
from app.domains.positions.models import Position as PositionModel


class PositionRepository(BaseRepository[PositionModel, entities.Position, uuid.UUID]):
    model = PositionModel

    def _to_entity(self, obj: PositionModel) -> entities.Position:
        return entities.Position(
            id=obj.id,
            title=obj.title,
            description=obj.description,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    def _to_model(self, entity: entities.Position) -> PositionModel:
        return PositionModel(
            id=entity.id, title=entity.title, description=entity.description
        )

    def update(self, entity: entities.Position) -> None:
        obj = self.db.get(PositionModel, entity.id)
        if obj is None:
            return
        obj.title = entity.title
        obj.description = entity.description
