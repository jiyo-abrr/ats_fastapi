import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domains.applications.enums import ApplicationStatus


class ApplicationCreate(BaseModel):
    job_post_id: uuid.UUID


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_post_id: uuid.UUID
    applicant_id: uuid.UUID
    status: str
    resume_object_key: str
    created_at: datetime
    updated_at: datetime


class ApplicationReviewOut(BaseModel):
    """Projection for GET /applications (HR/admin review list) — joined
    columns from job_posts + users, not a full Application/JobPost/User."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    created_at: datetime
    job_post_id: uuid.UUID
    job_title: str
    applicant_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str


class ApplicationSummaryOut(BaseModel):
    """Projection for GET /applications/me — joined to job_posts only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    created_at: datetime
    job_post_id: uuid.UUID
    job_title: str
