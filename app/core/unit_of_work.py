from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db


class UnitOfWork:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def flush(self) -> None:
        await self.db.flush()

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()


def get_unit_of_work(db: AsyncSession = Depends(get_db)) -> UnitOfWork:
    return UnitOfWork(db)
