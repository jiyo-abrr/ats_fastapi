import uuid

from sqlalchemy.exc import IntegrityError

from app.core.unit_of_work import UnitOfWork
from app.domains.tags import entities
from app.domains.tags.exceptions import TagInUseError, TagNotFoundError
from app.domains.tags.repository import TagRepository


class TagService:
    def __init__(self, tags: TagRepository, uow: UnitOfWork):
        self.tags = tags
        self.uow = uow

    def create(self, *, name: str, description: str | None) -> entities.Tag:
        tag_id = uuid.uuid4()
        self.tags.add(entities.Tag(id=tag_id, name=name, description=description))
        self.uow.commit()
        return self.tags.get_by_id(tag_id)

    def get(self, tag_id: uuid.UUID) -> entities.Tag:
        tag = self.tags.get_by_id(tag_id)
        if tag is None:
            raise TagNotFoundError(f"Tag '{tag_id}' not found")
        return tag

    def list(self) -> list[entities.Tag]:
        return self.tags.list_all()

    def update(
        self, tag_id: uuid.UUID, *, name: str, description: str | None
    ) -> entities.Tag:
        self.get(tag_id)
        self.tags.update(entities.Tag(id=tag_id, name=name, description=description))
        self.uow.commit()
        return self.tags.get_by_id(tag_id)

    def delete(self, tag_id: uuid.UUID) -> None:
        self.get(tag_id)
        self.tags.delete(tag_id)
        try:
            self.uow.commit()
        except IntegrityError:
            self.uow.rollback()
            raise TagInUseError(
                f"Tag '{tag_id}' is still referenced by one or more job posts"
            ) from None
