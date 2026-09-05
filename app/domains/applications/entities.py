import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Application:
    id: uuid.UUID
    job_post_id: uuid.UUID
    applicant_id: uuid.UUID
    status: str
    resume_object_key: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
