from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)
EntityType = TypeVar("EntityType")
IdType = TypeVar("IdType")


class BaseRepository(ABC, Generic[ModelType, EntityType, IdType]):
    model: type[ModelType]

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def _to_entity(self, obj: ModelType) -> EntityType: ...

    @abstractmethod
    def _to_model(self, entity: EntityType) -> ModelType: ...

    def get_by_id(self, id: IdType) -> EntityType | None:
        obj = self.db.get(self.model, id)
        return self._to_entity(obj) if obj is not None else None

    def list_all(self) -> list[EntityType]:
        return [self._to_entity(obj) for obj in self.db.query(self.model).all()]

    def add(self, entity: EntityType) -> None:
        self.db.add(self._to_model(entity))

    def delete(self, id: IdType) -> None:
        obj = self.db.get(self.model, id)
        if obj is not None:
            self.db.delete(obj)
