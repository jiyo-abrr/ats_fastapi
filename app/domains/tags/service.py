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

    async def create(self, *, name: str, description: str | None) -> entities.Tag:
        tag_id = uuid.uuid4()
        await self.tags.add(
            entities.Tag(id=tag_id, name=name, description=description)
        )
        await self.uow.commit()
        return await self.tags.get_by_id(tag_id)

    async def get(self, tag_id: uuid.UUID) -> entities.Tag:
        tag = await self.tags.get_by_id(tag_id)
        if tag is None:
            raise TagNotFoundError(f"Tag '{tag_id}' not found")
        return tag

    async def list(self) -> list[entities.Tag]:
        return await self.tags.list_all()

    async def update(
        self, tag_id: uuid.UUID, *, name: str, description: str | None
    ) -> entities.Tag:
        await self.get(tag_id)
        await self.tags.update(
            entities.Tag(id=tag_id, name=name, description=description)
        )
        await self.uow.commit()
        return await self.tags.get_by_id(tag_id)

    async def delete(self, tag_id: uuid.UUID) -> None:
        await self.get(tag_id)
        await self.tags.delete(tag_id)
        try:
            await self.uow.commit()
        except IntegrityError:
            await self.uow.rollback()
            raise TagInUseError(
                f"Tag '{tag_id}' is still referenced by one or more job posts"
            ) from None
