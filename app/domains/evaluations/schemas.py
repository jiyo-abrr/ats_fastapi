import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.applications.enums import allowed_transitions_for
from app.domains.evaluations.contracts import (
    ApplicationEvaluationIn as ApplicationEvaluationIn,
)
from app.domains.evaluations.contracts import (
    EvaluationImportIn as EvaluationImportIn,
)
from app.domains.evaluations.contracts import (
    EvaluationImportResultOut as EvaluationImportResultOut,
)
from app.domains.evaluations.contracts import (
    EvaluationScoreIn as EvaluationScoreIn,
)


class EvaluationScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    dimension: str
    rating: str
    reason: str | None


class ApplicationEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    recommendation: str | None
    fit_score: int | None
    seniority_assessed: str | None
    location: str | None
    summary: str | None
    model: str | None
    rubric_version: str | None
    created_at: datetime
    scores: list[EvaluationScoreOut] = Field(default_factory=list)


class JobEvaluationRowOut(BaseModel):
    """One applicant's latest AI evaluation, for the Compare tab's
    side-by-side evaluation matrix. Also carries pipeline status +
    allowed_status_transitions (same fields applications/schemas.py's
    _StatusCapabilitiesMixin computes) so the Compare tab's header row can
    offer a "move to next stage" action without a second round trip."""

    application_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str
    status: str
    allowed_status_transitions: list[str] = Field(default_factory=list)
    # HR explicitly bypassed AI evaluation for this application (see
    # Application.hr_assessed) — still listed here (unlike the export pack/
    # CSV, which exclude it), so the frontend can show a note in place of
    # the (nonexistent) evaluation instead of just omitting the applicant.
    hr_assessed: bool = False
    evaluation: ApplicationEvaluationOut | None = None

    @model_validator(mode="after")
    def _fill_allowed_transitions(self):
        self.allowed_status_transitions = allowed_transitions_for(self.status)
        return self


class EvaluationExportJobOut(BaseModel):
    """Status of a background evaluation-pack export (review F09/F26). Poll
    `GET /applications/export-jobs/{id}` until `status` is `done` or `failed`,
    then `GET .../download`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_post_id: uuid.UUID
    status: str
    status_filter: str | None
    error_message: str | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
