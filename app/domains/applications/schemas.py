import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.domains.applications.enums import ApplicationStatus
from app.domains.assessments.schemas import AssessmentAttemptOut


class ApplicationCreate(BaseModel):
    job_post_id: uuid.UUID


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ExtendAssessmentDeadlineRequest(BaseModel):
    reason: str
    new_deadline: datetime | None = None
    extend_by_days: int | None = None

    @model_validator(mode="after")
    def _exactly_one_of_new_deadline_or_extend_by_days(self):
        if (self.new_deadline is None) == (self.extend_by_days is None):
            raise ValueError(
                "Exactly one of 'new_deadline' or 'extend_by_days' is required"
            )
        return self


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_post_id: uuid.UUID
    applicant_id: uuid.UUID
    status: str
    resume_object_key: str
    assessment_deadline: datetime | None
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


class AssessmentDeadlineExtensionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    extended_by_user_id: uuid.UUID
    reason: str
    previous_deadline: datetime
    new_deadline: datetime
    extended_at: datetime


class ApplicationAssessmentsOut(BaseModel):
    """GET /applications/{id}/assessments — the 3 attempts (with their live
    answers + reopen history) plus the application's deadline-extension
    history. Both audit trails surfaced here, not just written and forgotten."""

    attempts: list[AssessmentAttemptOut]
    deadline_extensions: list[AssessmentDeadlineExtensionOut]
