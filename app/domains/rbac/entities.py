import uuid
from dataclasses import dataclass


@dataclass
class Role:
    id: uuid.UUID
    name: str
    description: str | None


@dataclass
class Permission:
    id: uuid.UUID
    key: str
    description: str | None
