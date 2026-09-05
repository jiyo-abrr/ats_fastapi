import uuid

from pydantic import BaseModel, ConfigDict


class TagCreate(BaseModel):
    name: str
    description: str | None = None


class TagUpdate(TagCreate):
    pass


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
