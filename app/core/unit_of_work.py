from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db


class UnitOfWork:
    def __init__(self, db: Session):
        self.db = db

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def refresh(self, obj: Any) -> None:
        self.db.refresh(obj)


def get_unit_of_work(db: Session = Depends(get_db)) -> UnitOfWork:
    return UnitOfWork(db)
