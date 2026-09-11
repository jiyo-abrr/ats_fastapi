import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.applications.enums import (
    ApplicationStatus,
    allowed_transitions_for,
    can_withdraw,
)
from app.domains.assessments.attempts.schemas import (
    AssessmentAttemptOut,
    AttemptReviewOut,
)


class _StatusCapabilitiesMixin(BaseModel):
    """Fills `allowed_status_transitions` / `can_withdraw` from `status` so the
    frontend never has to encode the pipeline rules (they live in enums.py)."""

    status: str
    allowed_status_transitions: list[str] = Field(default_factory=list)
    can_withdraw: bool = False

    @model_validator(mode="after")
    def _fill_status_capabilities(self):
        self.allowed_status_transitions = allowed_transitions_for(self.status)
        self.can_withdraw = can_withdraw(self.status)
        return self


class ApplicationCreate(BaseModel):
    job_post_id: uuid.UUID


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ExtendAssessmentDeadlineRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    new_deadline: datetime | None = None
    extend_by_days: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def _exactly_one_of_new_deadline_or_extend_by_days(self):
        if (self.new_deadline is None) == (self.extend_by_days is None):
            raise ValueError(
                "Exactly one of 'new_deadline' or 'extend_by_days' is required"
            )
        return self


class ApplicationOut(_StatusCapabilitiesMixin):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_post_id: uuid.UUID
    applicant_id: uuid.UUID
    resume_object_key: str
    assessment_deadline: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationReviewOut(_StatusCapabilitiesMixin):
    """Projection for GET /applications (HR/admin review list) — joined
    columns from job_posts + users, not a full Application/JobPost/User."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    job_post_id: uuid.UUID
    job_title: str
    applicant_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str


class ApplicantSummaryOut(BaseModel):
    """Projection for GET /applications/applicants — one row per person who
    has applied at least once, grouped from applications + users."""

    model_config = ConfigDict(from_attributes=True)

    applicant_id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    application_count: int
    latest_applied_at: datetime


class JobAssessmentReviewRowOut(BaseModel):
    """One applicant's attempt at a single assessment, for the Compare tab's
    per-assessment view (GET /applications/assessment-review)."""

    application_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str
    attempt: AttemptReviewOut | None = None


class AttemptSummaryOut(BaseModel):
    template_type: str
    status: str
    answered_count: int
    total_questions: int
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EvaluationSummaryOut(BaseModel):
    recommendation: str | None = None
    fit_score: int | None = None


class ApplicationScorecardOut(BaseModel):
    """GET /applications/assessment-scorecard — one row per applicant to a job
    post with a compact per-assessment roll-up, for the Compare tab."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    status: str
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str
    assessments: list[AttemptSummaryOut] = Field(default_factory=list)
    evaluation: EvaluationSummaryOut | None = None


class ApplicationSummaryOut(BaseModel):
    """Projection for GET /applications/me — joined to job_posts only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    created_at: datetime
    job_post_id: uuid.UUID
    job_title: str
    # A domain-neutral "the applicant owes an action on this application" flag,
    # filled by whichever domain owns the pending step via the list route's
    # transformer (e.g. interviews sets "pick_interview_time"). None = nothing
    # outstanding.
    pending_applicant_action: str | None = None


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


class ApplicationStatsOut(BaseModel):
    """GET /applications/stats — status tally for the ATS dashboard."""

    by_status: dict[str, int]
    total: int
