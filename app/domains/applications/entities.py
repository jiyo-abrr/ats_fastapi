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
    assessment_deadline: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class AssessmentDeadlineExtension:
    id: uuid.UUID
    application_id: uuid.UUID
    extended_by_user_id: uuid.UUID
    reason: str
    previous_deadline: datetime
    new_deadline: datetime
    extended_at: datetime | None = None
