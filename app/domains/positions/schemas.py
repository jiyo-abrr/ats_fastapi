import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PositionCreate(BaseModel):
    title: str
    description: str | None = None


class PositionUpdate(PositionCreate):
    pass


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
