import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Position:
    id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
