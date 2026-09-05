from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)
IdType = TypeVar("IdType")


class BaseRepository(Generic[ModelType, IdType]):
    model: type[ModelType]

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id: IdType) -> ModelType | None:
        return self.db.get(self.model, id)

    def add(self, obj: ModelType) -> None:
        self.db.add(obj)

    def delete(self, obj: ModelType) -> None:
        self.db.delete(obj)
