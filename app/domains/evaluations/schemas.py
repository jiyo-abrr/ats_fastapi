import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.evaluations.dimensions import Rating, Recommendation


class EvaluationScoreIn(BaseModel):
    dimension: str
    rating: Rating
    reason: str | None = None


def _drop_blank_scores(value: object) -> object:
    """Template stubs ship with rating="" — quietly drop unfilled rows rather
    than 422 the whole import."""
    if isinstance(value, list):
        return [
            v
            for v in value
            if not (isinstance(v, dict) and not str(v.get("rating") or "").strip())
        ]
    return value


class ApplicationEvaluationIn(BaseModel):
    application_id: uuid.UUID
    seniority_assessed: str | None = None
    fit_score: int | None = Field(default=None, ge=0, le=100)
    recommendation: Recommendation | None = None
    summary: str | None = None
    resume_scores: list[EvaluationScoreIn] = Field(default_factory=list)
    assessment_scores: list[EvaluationScoreIn] = Field(default_factory=list)

    @field_validator("seniority_assessed", "summary", "recommendation", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("resume_scores", "assessment_scores", mode="before")
    @classmethod
    def _prune_scores(cls, v: object) -> object:
        return _drop_blank_scores(v)


class EvaluationImportIn(BaseModel):
    job_post_id: uuid.UUID
    model: str | None = None
    rubric_version: str | None = None
    evaluations: list[ApplicationEvaluationIn]


class EvaluationImportResultOut(BaseModel):
    imported: int
    skipped: list[str] = Field(default_factory=list)


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
    summary: str | None
    model: str | None
    rubric_version: str | None
    created_at: datetime
    scores: list[EvaluationScoreOut] = Field(default_factory=list)


class JobEvaluationRowOut(BaseModel):
    """One applicant's latest AI evaluation, for the Compare tab's
    side-by-side evaluation matrix."""

    application_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str
    evaluation: ApplicationEvaluationOut | None = None
