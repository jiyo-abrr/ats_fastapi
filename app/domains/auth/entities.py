import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    id: uuid.UUID
    first_name: str
    middle_initial: str | None
    last_name: str
    contact_number: str
    email: str
    password_hash: str
    role_id: uuid.UUID
    role: str
    resume_object_key: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class RevokedRefreshToken:
    jti: str
    expires_at: datetime
    revoked_at: datetime | None = None
