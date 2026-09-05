from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.tags.repository import TagRepository
from app.domains.tags.service import TagService


def get_tag_repository(db: Session = Depends(get_db)) -> TagRepository:
    return TagRepository(db)


def get_tag_service(
    tags: TagRepository = Depends(get_tag_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TagService:
    return TagService(tags, uow)
